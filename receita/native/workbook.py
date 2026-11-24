#!/usr/bin/env python3
"""Generate and exercise a Tayriva formula workbook; no external tax solver is invoked."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo import local_app

SHEET = "Cálculo"
INPUTS = ("gross", "discount", "iss", "cbs_rate", "state_rate", "city_rate")
CALC = (
    ("calc:reduction_pct", "=60"),
    ("out:base", "=A6-B6-C6"),
    ("calc:cbs_effective_pp", "=ROUND(D6*(100-G6)/10000,4)"),
    ("calc:state_effective_pp", "=ROUND(E6*(100-G6)/10000,4)"),
    ("calc:city_effective_pp", "=ROUND(F6*(100-G6)/10000,4)"),
    ("out:cbs", "=ROUND(H6*I6/100,0)"),
    ("out:state", "=ROUND(H6*J6/100,0)"),
    ("out:city", "=ROUND(H6*K6/100,0)"),
    ("out:ibs", "=M6+N6"),
)
TITLES = ("Serviço (centavos)", "Desconto (centavos)", "ISSQN (centavos)",
          "CBS nominal (p.b.)", "IBS UF nominal (p.b.)", "IBS Mun. nominal (p.b.)",
          "Redução (%)", "Base (centavos)", "CBS efetiva (%)", "IBS UF efetiva (%)",
          "IBS Mun. efetiva (%)", "CBS (centavos)", "IBS UF (centavos)",
          "IBS Mun. (centavos)", "IBS total (centavos)")

def build(post, database, output, *, profile=None):
    def edit(row, values):
        post("ranges/edit",sheet_name=SHEET,row=row-1,col=0,values=[values])
    post("sheets/rename",old_name="Sheet1",new_name=SHEET)
    post("connections",name="Notas",kind="sqlite",path=str(database))
    profile = profile or {}
    inputs, calc, titles = profile.get("inputs", INPUTS), profile.get("calc", CALC), profile.get("titles", TITLES)
    if rules := profile.get("rules"):
        post("sheets",name="Regras")
        post("ranges/edit",sheet_name="Regras",row=0,col=0,values=rules)
        for col,width in enumerate((222,132,320,120,96,120)):
            post("sheets/column-width",sheet_name="Regras",column=col,width=width)
        post("ranges/format",sheet_name="Regras",range=dict(start_row=0,end_row=0,start_col=0,end_col=5),
             style=dict(fill="#F2BD45",bold=True,italic=False))
    edit(1,["TAYRIVA FORMULA BATCH 1"])
    edit(2,["Notas","bench_invoices","bench_results","id"])
    edit(3,list(titles))
    edit(4,["Nota Nº", "1"])
    edit(5,[f"in:{c}" for c in inputs]+[field for field,_ in calc])
    edit(6,[f'=SQLVALUE("Notas","SELECT {c} FROM bench_invoices WHERE id=?",$B$4)' for c in inputs]
         +[formula for _,formula in calc])
    labels = {
        8:["Simulação sintética • NFS-e • operação comum • 2027 • NBS 122011200 • CST 200 / cClassTrib 200028"],
        9:["Total CBS + IBS (R$)","=(L6+O6)/100"],
        10:["CBS (R$)","=L6/100"],
        11:["IBS total (R$)","=O6/100"],
        12:["Base (R$)","=H6/100"],
        14:["Edite B4 para escolher uma nota real da base simulada. Use Review → Explain & Review em B9."],
        15:["Use Data → Run formula batch para aplicar as fórmulas da linha 6 a todas as notas."],
        16:["Para simular uma mudança pontual, edite uma entrada da linha 6. O lote usa os valores da base SQLite."],
        17:["As alíquotas nominais são ilustrativas. O recorte não constitui apuração fiscal."],
        18:["Redução de 60%: Art. 129 da LC 214/2025, conforme classificação do cenário no motor RTC 1.7.2/V0073."],
        19:["Base = serviço − desconto incondicional − ISSQN. Alíquota efetiva: 4 casas; centavos: 0 casas; ambos meio-par."],
    }
    for row, values in (labels | profile.get("labels", {})).items():
        edit(row, values)
    for c in range(len(titles)):
        post("sheets/column-width",sheet_name=SHEET,column=c,width=218 if c==0 else 156)
    for row, color in ((3,"#F2BD45"),(5,"#F5E8C5"),(6,"#FFF4D6")):
        post("ranges/format",sheet_name=SHEET,
             range=dict(start_row=row-1,end_row=row-1,start_col=0,end_col=len(titles)-1),
             style=dict(fill=color,bold=True,italic=False))
    post("ranges/format",sheet_name=SHEET,range=dict(start_row=8,end_row=11,start_col=1,end_col=1),
         style=dict(fill="#F2BD45",bold=True,italic=False,number_format="0.00"))
    post("sheets",name="Notas")
    post("tables/insert-live",sheet_name="Notas",table_name="Notas de entrada",connection_name="Notas",
         sql="SELECT * FROM bench_invoices",row=2,col=0)
    post("cells/set",sheet_name="Notas",row=0,col=0,
         raw_input="Notas sintéticas • edite os valores e confirme em Review → Staged edits")
    post("sheets",name="Lote")
    post("ranges/edit",sheet_name="Lote",row=0,col=0,values=[
        ["RESULTADOS GRAVADOS NO SQLITE", ""],
        ["Valores da tabela bench_results. O lote é executado pela aba Cálculo.", ""],
        ["Notas gravadas",'=SQLVALUE("Notas","SELECT COUNT(*) FROM bench_results")'],
        ["Nota selecionada","='Cálculo'!B4"],
        ["Base gravada (centavos)",'=IF(B3=0,"Ainda não calculado",SQLVALUE("Notas","SELECT base FROM bench_results WHERE id=?",B4))'],
        ["CBS gravada (centavos)",'=IF(B3=0,"Ainda não calculado",SQLVALUE("Notas","SELECT cbs FROM bench_results WHERE id=?",B4))'],
        ["IBS gravado (centavos)",'=IF(B3=0,"Ainda não calculado",SQLVALUE("Notas","SELECT ibs FROM bench_results WHERE id=?",B4))'],
    ])
    post("sheets/column-width",sheet_name="Lote",column=0,width=240)
    post("sheets/column-width",sheet_name="Lote",column=1,width=180)
    post("sheets/select",name=SHEET)
    post("workbook/save",path=str(output),create_only=True)

def run(post, workbook):
    post("workbook/open",path=str(workbook))
    url=post.base_url+"/api/formula-batch?"+urlencode(dict(sheet_name=SHEET))
    with urlopen(url,timeout=15) as resp:
        plan=json.load(resp)
    return post("formula-batch",sheet_name=SHEET,expected_revision=plan["revision"])

def check_review(post, workbook, database, *, extra_evidence=()):
    def number(result):
        return Decimal(result["value"]["value"])
    post("workbook/open",path=str(workbook))
    first=post("cells/explain",sheet_name=SHEET,row=8,col=1)
    evidence=json.dumps(first["nodes"])
    assert first["can_review"] and all(s in evidence for s in (
        "bench_invoices", "cbs_rate", "discount", "state_rate", "city_rate", "ROUND", *extra_evidence)), evidence
    with sqlite3.connect(database) as con:
        n=con.execute("SELECT max(id) FROM bench_invoices").fetchone()[0]
        a,b=con.execute("SELECT cbs,ibs FROM bench_results WHERE id=1").fetchone()
        assert number(first)*100==a+b
        a,b=con.execute("SELECT cbs,ibs FROM bench_results WHERE id=?",(n,)).fetchone()
    # Choose the last taxable invoice so an input edit changes the tax, even
    # when the highest invoice ID belongs to the zero-rated group.
    with sqlite3.connect(database) as con:
        taxable=con.execute("SELECT max(id) FROM bench_results WHERE cbs+ibs>0").fetchone()[0]
    post("cells/set",sheet_name=SHEET,row=3,col=1,raw_input=str(taxable))
    with sqlite3.connect(database) as con:
        a,b=con.execute("SELECT cbs,ibs FROM bench_results WHERE id=?",(taxable,)).fetchone()
    end=post("cells/explain",sheet_name=SHEET,row=8,col=1)
    assert number(end)*100==a+b and (taxable==1 or end["snapshot"]!=first["snapshot"])
    post("cells/set",sheet_name=SHEET,row=5,col=0,raw_input="99999999")
    edited=post("cells/explain",sheet_name=SHEET,row=8,col=1)
    assert number(edited) > number(end) and edited["snapshot"]!=end["snapshot"]
    return dict(validated_total_cents=a+b,invoice=taxable,review_nodes=len(first["nodes"]),
                changed_input_total_reais=str(number(edited)),updated_review=True)

def main(*, profile=None, extra_evidence=("=60",)):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("build","run","review"))
    p.add_argument("--server",required=True,type=Path)
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--workbook",required=True,type=Path)
    a=p.parse_args()
    a.db=a.db.resolve()
    a.workbook=a.workbook.resolve()
    if not a.db.is_file(): p.error("Prepare the SQLite database first.")
    with local_app(a.server,timeout=1800) as post:
        if a.action=="build":
            if a.workbook.exists(): p.error("Choose a new workbook path.")
            build(post,a.db,a.workbook,profile=profile)
            print(a.workbook)
        elif a.action=="run":
            print(json.dumps(run(post,a.workbook)))
        else:
            print(json.dumps(check_review(post,a.workbook,a.db,extra_evidence=extra_evidence)))

if __name__=="__main__":
    main()
