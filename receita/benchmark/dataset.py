#!/usr/bin/env python3
"""Prepare deterministic synthetic inputs separately; verify persisted results and official REST parity."""
import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo import client

SCHEMA = """
CREATE TABLE bench_invoices (
 id INTEGER PRIMARY KEY, gross INTEGER NOT NULL, discount INTEGER NOT NULL, iss INTEGER NOT NULL,
 event TEXT NOT NULL, municipality INTEGER NOT NULL, uf TEXT NOT NULL,
 nbs TEXT NOT NULL, cst TEXT NOT NULL, class TEXT NOT NULL,
 cbs_rate INTEGER NOT NULL, state_rate INTEGER NOT NULL, city_rate INTEGER NOT NULL) STRICT;
CREATE TABLE bench_results (
 id INTEGER PRIMARY KEY REFERENCES bench_invoices(id), base INTEGER NOT NULL, cbs INTEGER NOT NULL,
 state INTEGER NOT NULL, city INTEGER NOT NULL, ibs INTEGER NOT NULL,
 CHECK (base>=0 AND cbs>=0 AND state>=0 AND city>=0 AND ibs=state+city)) STRICT;
CREATE TABLE bench_state (id INTEGER PRIMARY KEY CHECK(id=1), total INTEGER NOT NULL,
 committed INTEGER NOT NULL CHECK(committed<=total)) STRICT;
"""

def create(path, n):
    if path.exists(): raise FileExistsError(path)
    start=time.perf_counter()
    with closing(sqlite3.connect(path)) as c, c:
        c.executescript(SCHEMA)
        c.execute("""WITH RECURSIVE ids(i) AS (VALUES(1) UNION ALL SELECT i+1 FROM ids WHERE i<?)
            INSERT INTO bench_invoices SELECT i,
              100000 + (i*7919)%10000019,
              (i*233)%10000, (i*59)%5000,
              strftime('%Y-%m-%dT%H:%M:%S','2027-01-01',printf('+%d seconds',(i*104729)%31536000)) || '-03:00',
              CASE i%4 WHEN 0 THEN 4314902 WHEN 1 THEN 3550308 WHEN 2 THEN 3304557 ELSE 3106200 END,
              CASE i%4 WHEN 0 THEN 'RS' WHEN 1 THEN 'SP' WHEN 2 THEN 'RJ' ELSE 'MG' END,
              '122011200','200','200028',
              850+(i*31)%61,4+i%4,3+i%5
            FROM ids""",(n,))
        c.execute("INSERT INTO bench_state VALUES (1,?,0)", (n,))
    print(json.dumps(dict(generated=n,generation_s=time.perf_counter()-start,db_bytes=path.stat().st_size)))

def validate(path,n,api,*,worksheet=False):
    source=client(api)
    version=json.loads(source("dados-abertos/versao"))
    assert (version["versaoApp"],version["versaoDb"],version["ambiente"])==("1.7.2","V0073","offline"),version
    start=time.perf_counter()
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro",uri=True)) as c:
        if not worksheet:
            assert c.execute("SELECT total,committed FROM bench_state WHERE id=1").fetchone()==(n,n)
        assert c.execute("SELECT count(*),min(id),max(id) FROM bench_invoices").fetchone()==(n,1,n)
        stats=c.execute("SELECT count(*),min(id),max(id),sum(base),sum(cbs),sum(state),sum(city),sum(ibs) FROM bench_results").fetchone()
        assert stats[:3]==(n,1,n),stats
        assert not c.execute("PRAGMA foreign_key_check").fetchone()
        assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        checked=[]
        for i in sorted({1,n,*[min(n,j) for j in range(2,9)],*(1+(n-1)*j//24 for j in range(1,24))}):
            invoice=c.execute("SELECT * FROM bench_invoices WHERE id=?",(i,)).fetchone()
            _,gross,discount,iss,event,city,uf,nbs,cst,code,a,b,d=invoice
            base=json.loads(source("base-calculo/base-calculo-unificada-nfse",json.dumps(dict(
                anoFatoGerador=int(event[:4]),opSimpNac="1",situacao="comum",vServ=str(Decimal(gross)/100),
                vDescIncond=str(Decimal(discount)/100),vISSQN=str(Decimal(iss)/100)))),parse_float=Decimal)
            assert not base["erros"]
            payload=json.dumps(dict(id=f"rtc-bench-{i}",versao="1.0.0",dhFatoGerador=event,
                municipio=city,uf=uf,itens=[dict(numero=1,nbs=nbs,cst=cst,cClassTrib=code,baseCalculo="@@BASE@@",
                    aliquotasNominais=dict(cbs=a/100,ibsEstadual=b/100,ibsMunicipal=d/100))]))
            payload=payload.replace('"@@BASE@@"',format(Decimal(base["baseRG"]),"f"))
            obj=json.loads(source("observabilidade/regime-geral",payload))["objetos"][0]
            assert obj["estadoItem"]=="CALCULO_SIMULADO",obj
            g=obj["tribCalc"]["IBSCBS"]["gIBSCBS"]
            expected=tuple(int(Decimal(v)*100) for v in (g["vBC"],g["gCBS"]["vCBS"],
                g["gIBSUF"]["vIBSUF"],g["gIBSMun"]["vIBSMun"],g["vIBS"]))
            got=c.execute("SELECT base,cbs,state,city,ibs FROM bench_results WHERE id=?",(i,)).fetchone()
            assert expected==got,(i,expected,got)
            checked.append(i)
    print(json.dumps(dict(reference_samples=len(checked),sample_ids=checked,rows=n,db_bytes=path.stat().st_size,
         base_cents=stats[3],cbs_cents=stats[4],ibs_state_cents=stats[5],ibs_city_cents=stats[6],ibs_cents=stats[7],
         validation_s=time.perf_counter()-start)))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("prepare","verify"))
    p.add_argument("db",type=Path)
    p.add_argument("--rows",type=int,default=10_000_000)
    p.add_argument("--api",default="http://127.0.0.1:18927")
    p.add_argument("--worksheet",action="store_true",help="Check worksheet results without the Java runner checkpoint")
    a=p.parse_args()
    if not 1<=a.rows<=10_000_000:p.error("rows must be 1..10000000")
    if a.mode=="prepare": create(a.db,a.rows)
    else: validate(a.db,a.rows,a.api,worksheet=a.worksheet)
