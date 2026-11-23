#!/usr/bin/env python3
"""Integration assertions for the locally pinned official Receita calculator."""
import argparse
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from demo import bulk, build, client, init, local_app, pdf, read_invoice


def verify(api, server, root, n):
    db = root / "bench.sqlite"
    init(db,n,100_000)
    send = client(api)
    bulk(db,send,100_000,1)
    with sqlite3.connect(db) as c:
        checkpoint = c.execute("SELECT calculated FROM state").fetchone()[0]
        assert checkpoint == min(n,100_000)
        assert c.execute("SELECT count(*) FROM tax_results").fetchone()[0] == checkpoint
    bulk(db,send,100_000,None)
    # A repeated execution must not access the API or insert duplicate rows.
    def unexpected(*_):
        raise AssertionError("API was called despite a complete run")
    bulk(db,unexpected,100_000,None)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT count(*),min(number),max(number) FROM invoices").fetchone() == (n,1,n)
        assert c.execute("SELECT count(*),min(number),max(number) FROM tax_results").fetchone() == (n,1,n)
        assert c.execute("SELECT count(*) FROM scenarios").fetchone()[0] == min(n,100)
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    note=read_invoice(db,1)
    assert (note["Base CBS/IBS"],note["CBS"],note["IBS total"]) == (114000,4013,46)
    sample=read_invoice(db,n)
    for portable in (False,True):
        path=root / ("snapshot.tay" if portable else "linked.tay")
        build(server,db,path,n,portable)
        with local_app(server) as post:
            post("workbook/open",path=str(path))
            explain=post("cells/explain",sheet_name="Consulta",row=10,col=1)
            expected=sample["CBS"]+sample["IBS total"]
            assert Decimal(explain["value"]["value"])*100==expected
            assert explain["can_review"]
            evidence=json.dumps(explain["nodes"])
            assert "Fonte SQL" in evidence
            if not portable:
                assert "service_cents" in evidence
                post("cells/set",sheet_name="Consulta",row=3,col=1,raw_input="1")
                first=post("cells/explain",sheet_name="Consulta",row=10,col=1)
                assert first["value"]["value"]=="40.59"
                assert first["snapshot"]!=explain["snapshot"] or n%100==1
    pdf(sample,root/"test.pdf")
    assert b"DANFSE DEMONSTRATIVO - SEM VALOR FISCAL" in (root/"test.pdf").read_bytes()
    print(f"PASS: {n:,} persisted rows, review trace, selection, resume, idempotency and demonstrative PDF")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api",default="http://127.0.0.1:18927")
    p.add_argument("--server",type=Path,required=True)
    p.add_argument("--directory",type=Path,required=True,help="New output directory")
    p.add_argument("--total",type=int,default=100_001)
    a=p.parse_args()
    if a.total < 2: p.error("total must be at least 2")
    a.directory.mkdir()
    verify(a.api,a.server,a.directory.resolve(),a.total)
