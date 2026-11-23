#!/usr/bin/env python3
"""Synthetic NFS-e lab; does not issue fiscal documents."""
import argparse, json, sqlite3, sys
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_dcf import local_app

ENGINE = "Receita Federal RTC 1.7.2 / V0073 / f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4"
DAY = "2027-03-10T10:00:00-03:00"
LOOKUPS = {
 "Operação (data/hora)": "i.event", "Município (IBGE)": "i.municipality",
 "UF": "i.uf", "NBS": "i.nbs", "CST": "i.cst", "cClassTrib": "i.class",
 "Valor do serviço": "i.service_cents", "Desconto incondicional": "i.discount_cents",
 "ISSQN informado": "i.iss_cents", "Base CBS/IBS": "t.base_cents", "CBS": "t.cbs_cents",
 "IBS UF": "t.uf_cents", "IBS Município": "t.muni_cents", "IBS total": "t.ibs_cents",
 "Motor/regra": "r.engine",
}
JOIN = "invoices i LEFT JOIN tax_results t USING (number) LEFT JOIN scenarios r ON t.profile=r.profile"
SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
 number INTEGER PRIMARY KEY, profile INTEGER NOT NULL,
 service_cents INTEGER NOT NULL, discount_cents INTEGER NOT NULL, iss_cents INTEGER NOT NULL,
 event TEXT NOT NULL, municipality INTEGER NOT NULL, uf TEXT NOT NULL,
 nbs TEXT NOT NULL, cst TEXT NOT NULL, class TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS scenarios (
 profile INTEGER PRIMARY KEY, engine TEXT NOT NULL,
 base_cents INTEGER NOT NULL, cbs_cents INTEGER NOT NULL, uf_cents INTEGER NOT NULL,
 muni_cents INTEGER NOT NULL, ibs_cents INTEGER NOT NULL,
 base_request TEXT NOT NULL, base_response TEXT NOT NULL,
 tax_request TEXT NOT NULL, tax_response TEXT NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS tax_results (
 number INTEGER PRIMARY KEY REFERENCES invoices(number), profile INTEGER NOT NULL REFERENCES scenarios(profile),
 base_cents INTEGER NOT NULL, cbs_cents INTEGER NOT NULL, uf_cents INTEGER NOT NULL,
 muni_cents INTEGER NOT NULL, ibs_cents INTEGER NOT NULL) STRICT;
CREATE TABLE IF NOT EXISTS state (
 id INTEGER PRIMARY KEY CHECK (id=1), total INTEGER NOT NULL, generated INTEGER NOT NULL,
 calculated INTEGER NOT NULL, engine TEXT NOT NULL) STRICT;
"""

def connect(path):
    db=sqlite3.connect(path,timeout=30)
    db.execute("pragma foreign_keys=ON")
    return db

def init(path,total,chunk):
    with closing(connect(path)) as db:
        db.executescript(SCHEMA)
        with db:
            db.execute("INSERT OR IGNORE INTO state VALUES(1,?,0,0,?)",(total,ENGINE))
        while True:
            db.execute("BEGIN IMMEDIATE")
            wanted,start,engine=db.execute("SELECT total,generated,engine FROM state").fetchone()
            if (wanted,engine)!=(total,ENGINE):
                raise ValueError("Base existente tem outro total ou motor; escolha outro arquivo.")
            if start==total:
                db.commit()
                break
            end=min(start+chunk,total)
            db.execute("""WITH RECURSIVE seq(n) AS (VALUES(?) UNION ALL SELECT n+1 FROM seq WHERE n<?)
                INSERT INTO invoices SELECT n, (n-1)%100, 120000+257*((n-1)%100),
                1000+11*((n-1)%100), 5000+13*((n-1)%100), ?,4314902,'RS','122011200','200','200028'
                FROM seq""",(start+1,end,DAY))
            db.execute("UPDATE state SET generated=?",(end,))
            db.commit()
    print(f"{total:,} notas sintéticas disponíveis",flush=True)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def client(url):
    origin=urlparse(url)
    if not (origin.scheme=="http" and origin.hostname in ("127.0.0.1","::1")
            and not any((origin.username,origin.password,origin.path,origin.query,origin.fragment))):
        raise ValueError("A API deve estar no loopback: http://127.0.0.1:18927")
    opener=build_opener(ProxyHandler({}),NoRedirect())
    def send(path,body=None):
        req=Request(url+"/api/calculadora/"+path,None if body is None else body.encode(),{"Content-Type":"application/json"})
        with opener.open(req,timeout=30) as resp:
            return resp.read().decode()
    return send

def money(cents):
    return f"{Decimal(cents)/100:.2f}"

def cents(value):
    return int(Decimal(value).quantize(Decimal(".01"),rounding=ROUND_HALF_UP)*100)

def calculate(send, profile):
    _,service,discount,iss,date,municipality,uf,nbs,cst,code=profile
    base_req=json.dumps(dict(anoFatoGerador=2027,opSimpNac="1",situacao="comum",
        vServ=money(service),vDescIncond=money(discount),vISSQN=money(iss)))
    base_raw=send("base-calculo/base-calculo-unificada-nfse",base_req)
    base=json.loads(base_raw,parse_float=Decimal)
    if base.get("erros") or "baseRG" not in base:
        raise ValueError(f"Receita recusou base: {base_raw}")
    tax_req=json.dumps(dict(id="rtc-demo-educacao",versao="1.0.0",dhFatoGerador=date,
        municipio=municipality,uf=uf,itens=[dict(numero=1,nbs=nbs,cst=cst,cClassTrib=code,
        baseCalculo="__base__",aliquotasNominais=dict(cbs=8.8,ibsEstadual=0.05,ibsMunicipal=0.05))]))
    tax_req=tax_req.replace('"__base__"',format(Decimal(base["baseRG"]),"f"))
    tax_raw=send("observabilidade/regime-geral",tax_req)
    tax=json.loads(tax_raw,parse_float=Decimal)["objetos"]
    if len(tax)!=1 or tax[0]["estadoItem"]!="CALCULO_SIMULADO":
        raise ValueError(f"Receita não simulou item: {tax_raw}")
    a=tax[0]["tribCalc"]["IBSCBS"]["gIBSCBS"]
    return (ENGINE,cents(a["vBC"]),cents(a["gCBS"]["vCBS"]),cents(a["gIBSUF"]["vIBSUF"]),
            cents(a["gIBSMun"]["vIBSMun"]),cents(a["vIBS"]),base_req,base_raw,tax_req,tax_raw)

def bulk(path,send,chunk,max_chunks):
    with closing(connect(path)) as db:
        total,generated,owner=db.execute("SELECT total,generated,engine FROM state").fetchone()
        if total!=generated or owner!=ENGINE:
            raise ValueError("Gere a base inteira com o motor correto antes de calcular.")
        pending=db.execute("""SELECT profile,service_cents,discount_cents,iss_cents,event,municipality,uf,nbs,cst,class
            FROM invoices WHERE number<=100 AND profile NOT IN (SELECT profile FROM scenarios)""").fetchall()
        if pending:
            version=json.loads(send("dados-abertos/versao"))
            if (version.get("versaoApp"),version.get("versaoDb"),version.get("ambiente"))!=("1.7.2","V0073","offline"):
                raise ValueError(f"Motor oficial fixado incompatível: {version}")
        for profile in pending:
            result=calculate(send,profile)
            with db:
                db.execute("INSERT OR IGNORE INTO scenarios VALUES(?,?,?,?,?,?,?,?,?,?,?)",(profile[0],*result))
        for _ in range(max_chunks or sys.maxsize):
            db.execute("BEGIN IMMEDIATE")
            start=db.execute("SELECT calculated FROM state").fetchone()[0]
            if total==start:
                db.commit()
                break
            end=min(start+chunk,total)
            inserted=db.execute("""INSERT INTO tax_results SELECT i.number,i.profile,s.base_cents,s.cbs_cents,
                s.uf_cents,s.muni_cents,s.ibs_cents FROM invoices i JOIN scenarios s USING(profile)
                WHERE i.number>? AND i.number<=?""",(start,end))
            if inserted.rowcount!=end-start:
                raise ValueError("Lote incompleto; nenhuma linha do lote foi gravada.")
            db.execute("UPDATE state SET calculated=?",(end,))
            db.commit()
        print(f"{db.execute('SELECT calculated FROM state').fetchone()[0]:,}/{total:,} calculadas",flush=True)

def read_invoice(path,number):
    with closing(connect(path)) as db:
        row=db.execute(f"SELECT {','.join(LOOKUPS.values())},r.base_request,r.base_response,r.tax_request,r.tax_response "
                       f"FROM {JOIN} WHERE i.number=?",(number,)).fetchone()
    if row is None or row[-1] is None:
        raise ValueError("Nota inexistente ou não calculada")
    result=dict(zip(LOOKUPS,row))
    result["numero"]=number
    result["memoria_Receita"]=dict(zip(("base_entrada","base_resposta","tributos_entrada","tributos_resposta"),
                                      map(json.loads,row[-4:])))
    return result

def build(server, database, output, number, snapshot=False):
    database=Path(database).resolve()
    output=Path(output).resolve()
    if not database.is_file() or output.exists():
        raise ValueError("A base deve existir e o destino .tay deve ser novo.")
    result=read_invoice(database, number) if snapshot else None
    with local_app(Path(server)) as post:
        post("sheets/rename",old_name="Sheet1",new_name="Consulta")
        post("sheets",name="Fonte SQL")
        if not snapshot:
            post("connections",name="Notas",kind="sqlite",path=str(database))
        def cell(sheet,row,col,raw):
            post("cells/set",sheet_name=sheet,row=row-1,col=col-1,raw_input=str(raw))
        for row,text in {
            1:"REFORMA TRIBUTÁRIA | LABORATÓRIO NFS-e",
            2:"SIMULAÇÃO SINTÉTICA • NÃO É DOCUMENTO FISCAL",
            4:"Nota (snapshot fixo)" if snapshot else "Número de nota (edite B4)",6:"Base CBS/IBS (R$)",7:"CBS (R$)",8:"IBS UF (R$)",
            9:"IBS Município (R$)",10:"IBS total (R$)",11:"CBS + IBS (R$)",
            13:"Use Revisão → Explicar e revisar em B11 para seguir os dados e as consultas SQLite.",
            14:"Aba Fonte SQL: entradas originais e valores retornados pelo motor.",
            15:"Para gerar PDF ou ler a resposta oficial completa, use os comandos no README.",
            17:"Conferência deste cenário: serviço - desconto - ISSQN",
            18:"Conferência IBS: UF + município coincide com motor?",
        }.items():
            cell("Consulta",row,1,text)
        cell("Consulta",4,2,number)
        cell("Fonte SQL",1,1,"Snapshot portátil do SQLite • nota fixa" if snapshot else "SQLite local • notas e resultados por número")
        cell("Fonte SQL",2,1,"Os valores monetários nesta aba estão em centavos inteiros.")
        for row,(label,expr) in enumerate(LOOKUPS.items(),4):
            cell("Fonte SQL",row,1,label)
            query=f"SELECT {expr} FROM {JOIN} WHERE i.number=?"
            cell("Fonte SQL",row,2,result[label] if snapshot else f'=SQLVALUE("Notas","{query}",Consulta!$B$4)')
        for row,source in zip(range(6,11),range(13,18)):
            cell("Consulta",row,2,f"='Fonte SQL'!B{source}/100")
        cell("Consulta",17,2,"=('Fonte SQL'!B10-'Fonte SQL'!B11-'Fonte SQL'!B12)/100")
        cell("Consulta",18,2,'=IF(B8+B9=B10,"OK","DIVERGÊNCIA")')
        cell("Consulta",11,2,'=IF(AND(B6=B17,B18="OK"),B7+B10,"CONFIRA ENTRADAS")')
        for sheet,widths in (("Consulta",(405,180)),("Fonte SQL",(310,490))):
            for col,width in enumerate(widths):
                post("sheets/column-width",sheet_name=sheet,column=col,width=width)
            post("ranges/format",sheet_name=sheet,
                range=dict(start_row=0,end_row=0,start_col=0,end_col=1),
                style=dict(fill="#bfdbfe",bold=True,italic=False))
        post("ranges/format",sheet_name="Consulta",
            range=dict(start_row=5,end_row=10,start_col=1,end_col=1),
            style=dict(number_format="0.00",fill="#dbeafe",bold=True,italic=False))
        post("sheets/select",name="Consulta")
        post("workbook/save",path=str(output),create_only=True)

def pdf(result,path):
    # Minimal one-page PDF (WinAnsi/Helvetica, no runtime dependency).
    lines=[
        (20,"DANFSE DEMONSTRATIVO - SEM VALOR FISCAL"),
        (12,"Simulacao sintetica NFS-e - nao emitida nem autorizada"),
        (12,f"Nota simulada: {result['numero']}"),
        (12,f"Operacao: {result['Operação (data/hora)']} / RS / IBGE {result['Município (IBGE)']}"),
        (12,f"Educacao - NBS {result['NBS']} / CST {result['CST']} / cClassTrib {result['cClassTrib']}"),
    ]
    lines += [(12,f"{label}: R$ {money(result[label])}") for label in list(LOOKUPS)[6:14]]
    lines += [(10,"Motor local: Receita Federal RTC 1.7.2 / V0073"),
              (10,"Aliquotas nominais ilustrativas: CBS 8,80%, IBS UF 0,05%, IBS Mun. 0,05%."),
              (10,"Sem chave, QR, assinatura ou protocolo oficial. Proibido uso fiscal.")]
    def escaped(s):
        return s.replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
    stream="\n".join(f"BT /F1 {size} Tf 45 {776-i*28} Td ({escaped(text)}) Tj ET"
                     for i,(size,text) in enumerate(lines)).encode("cp1252")
    objects=[
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream",
    ]
    document=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    positions=[]
    for i,obj in enumerate(objects,1):
        positions.append(len(document))
        document.extend(f"{i} 0 obj\n".encode()+obj+b"\nendobj\n")
    xref=len(document)
    document.extend(b"xref\n0 6\n0000000000 65535 f \n")
    document.extend("".join(f"{p:010d} 00000 n \n" for p in positions).encode())
    document.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    with open(path,"xb") as f:
        f.write(document)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="mode",required=True)
    def positive(raw):
        n=int(raw)
        if n<=0: raise argparse.ArgumentTypeError("Inteiro positivo obrigatório")
        return n
    for cmd in ("init","bulk","invoice","workbook"):
        a=sub.add_parser(cmd)
        a.add_argument("--db",type=Path,required=True)
        if cmd in ("init","bulk"):
            a.add_argument("--chunk",type=positive,default=100_000)
        if cmd=="init":
            a.add_argument("--total",type=positive,default=10_000_000)
        if cmd=="bulk":
            a.add_argument("--api",default="http://127.0.0.1:18927")
            a.add_argument("--max-chunks",type=positive)
        if cmd in ("invoice","workbook"):
            a.add_argument("--number",type=positive,default=1)
        if cmd=="invoice":
            a.add_argument("--pdf",type=Path)
        if cmd=="workbook":
            a.add_argument("--server",type=Path,required=True)
            a.add_argument("--output",type=Path,required=True)
            a.add_argument("--snapshot",action="store_true",help="Guarde uma nota fixa sem conexão local.")
    a=p.parse_args()
    if a.mode!="init" and not a.db.is_file():
        p.error("Execute init primeiro.")
    if a.mode=="init": init(a.db,a.total,a.chunk)
    elif a.mode=="bulk": bulk(a.db,client(a.api),a.chunk,a.max_chunks)
    elif a.mode=="workbook": build(a.server,a.db,a.output,a.number,a.snapshot)
    else:
        result=read_invoice(a.db,a.number)
        if a.pdf: pdf(result,a.pdf)
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
