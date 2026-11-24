#!/usr/bin/env python3
"""Create identical 2027 NFS-e input pairs for the mixed-rule benchmark."""
from contextlib import closing
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark.dataset import SCHEMA

RULES = (
    # NBS, CST, cClassTrib, reduction percent, synthetic treatment label
    (114011100,   0,      1,   0, "Tributação integral • LC 214/2025"),
    (114011100, 200, 200052,  30, "Profissões intelectuais • Art. 127"),
    (122011200, 200, 200028,  60, "Educação • Art. 129"),
    (114011100, 200, 200016, 100, "Pesquisa (ICT elegível) • Art. 156"),
)
SCHEMA_MIXED = SCHEMA.replace("nbs TEXT NOT NULL, cst TEXT NOT NULL, class TEXT NOT NULL",
    "nbs INTEGER NOT NULL, cst INTEGER NOT NULL, class INTEGER NOT NULL")
ALLOWED = " OR ".join(f"(nbs={nbs} AND cst={cst} AND class={code})" for nbs,cst,code,_,_ in RULES)
INPUT_CHECK = f"""
  CHECK ({ALLOWED}),
  CHECK (date(substr(event,1,10)) IS NOT NULL AND substr(event,1,4)='2027'),
  CHECK ((municipality=4314902 AND uf='RS') OR (municipality=3550308 AND uf='SP') OR
         (municipality=3304557 AND uf='RJ') OR (municipality=3106200 AND uf='MG')),
  CHECK (gross>=0 AND discount>=0 AND iss>=0 AND gross-discount>=iss),
  CHECK (cbs_rate BETWEEN 0 AND 10000 AND state_rate BETWEEN 0 AND 10000 AND city_rate BETWEEN 0 AND 10000)
"""
SCHEMA_MIXED = SCHEMA_MIXED.replace("city_rate INTEGER NOT NULL)",f"city_rate INTEGER NOT NULL, {INPUT_CHECK})")

def create(path, n):
    if path.exists(): raise FileExistsError(path)
    start=time.perf_counter()
    with closing(sqlite3.connect(path)) as c, c:
        c.executescript(SCHEMA_MIXED)
        rule_values=",".join(f"({i},{nbs},{cst},{code})" for i,(nbs,cst,code,_,_) in enumerate(RULES))
        c.execute(f"""WITH RECURSIVE ids(i) AS (VALUES(1) UNION ALL SELECT i+1 FROM ids WHERE i<?),
            rules(rule_n,nbs,cst,class) AS (VALUES {rule_values})
            INSERT INTO bench_invoices SELECT i,
              100000 + (i*7919)%10000019, (i*233)%10000, (i*59)%5000,
              strftime('%Y-%m-%dT%H:%M:%S','2027-01-01',printf('+%d seconds',(i*104729)%31536000)) || '-03:00',
              CASE i%4 WHEN 0 THEN 4314902 WHEN 1 THEN 3550308 WHEN 2 THEN 3304557 ELSE 3106200 END,
              CASE i%4 WHEN 0 THEN 'RS' WHEN 1 THEN 'SP' WHEN 2 THEN 'RJ' ELSE 'MG' END,
              r.nbs,r.cst,r.class,850+(i*31)%61,4+i%4,3+i%5
            FROM ids JOIN rules r ON r.rule_n = ((i-1)+(i-1)/4)%4
            ORDER BY ids.i""",(n,))
        c.execute("INSERT INTO bench_state VALUES (1,?,0)",(n,))
        counts=dict(c.execute("SELECT class,count(*) FROM bench_invoices GROUP BY class"))
    print(json.dumps(dict(rows=n, input_seconds=time.perf_counter()-start,classification_counts=counts)))

def compare(native,official,n):
    with closing(sqlite3.connect(native.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.execute("ATTACH ? AS reference", (official.resolve().as_uri()+'?mode=ro',))
        committed=c.execute("SELECT total,committed FROM reference.bench_state").fetchone()
        assert committed==(n,n),f"Official runner has not finished: {committed}"
        for side in ("main","reference"):
            for table in ("bench_invoices","bench_results"):
                assert c.execute(f"SELECT count(*),min(id),max(id) FROM {side}.{table}").fetchone()==(n,1,n)
            assert c.execute(f"PRAGMA {side}.integrity_check").fetchone()==("ok",)
            assert not c.execute(f"PRAGMA {side}.foreign_key_check").fetchone()
        for table in ("bench_invoices","bench_results"):
            cols=[r[1] for r in c.execute(f"PRAGMA main.table_info({table})")]
            comparisons=" OR ".join(f"native.{col} IS NOT official.{col}" for col in cols if col!="id")
            difference=c.execute(f"""SELECT native.id FROM main.{table} native
                LEFT JOIN reference.{table} official USING(id) WHERE official.id IS NULL OR {comparisons} LIMIT 1""").fetchone()
            assert not difference,(table,difference)
        groups=list(c.execute("""SELECT i.class,count(*),sum(r.cbs),sum(r.ibs) FROM bench_invoices i
                       JOIN bench_results r USING(id) GROUP BY i.class ORDER BY i.class"""))
    print(json.dumps(dict(rows=n, input_and_output_rows_compared_by_primary_key=True, mismatches=0,
                          classifications=groups,integrity_and_foreign_keys="ok")))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("prepare","compare"))
    p.add_argument("db",type=Path)
    p.add_argument("--official",type=Path)
    p.add_argument("--rows",type=int,default=10_000_000)
    a=p.parse_args()
    if not 1<=a.rows<=10_000_000:p.error("rows must be 1..10000000")
    if a.action=="prepare":create(a.db,a.rows)
    elif a.official is None:p.error("compare requires --official")
    else:compare(a.db,a.official,a.rows)
