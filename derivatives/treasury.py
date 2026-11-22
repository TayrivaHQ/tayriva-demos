#!/usr/bin/env python3
"""Stage public Treasury CMT quotes in SQLite and build a native Gridloom teaching curve."""
import argparse
from contextlib import contextmanager
import csv
from datetime import date, datetime
from decimal import Decimal as D, localcontext
from io import StringIO
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from urllib.request import Request, urlopen

from build import MCP, edit, table_row

BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
FALLBACK = Path(__file__).with_name("treasury-cmt-2026-11-20.csv")
SNAPSHOT = "2026-11-20"
FIELDS = {6: "6 Mo", 12: "1 Yr", 24: "2 Yr", 36: "3 Yr", 60: "5 Yr"}
SQL = "SELECT yield_bp FROM treasury_cmt WHERE observation_date = ? AND maturity_months = ?"
PUBLIC_TABLE = BASE + "TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month="


def get_csv(month):
    assert re.fullmatch(r"[0-9]{6}", month)
    url = BASE + f"daily-treasury-rates.csv/all/{month}?_format=csv&field_tdr_date_value_month={month}&page=&type=daily_treasury_yield_curve"
    req = Request(url, headers={"Accept": "text/csv", "User-Agent": "Gridloom-Demos/1.0"})
    with urlopen(req, timeout=15) as response:
        if not response.geturl().startswith(BASE):
            raise ValueError("Unexpected redirect from official feed")
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("Treasury CSV exceeds the expected monthly size")
    return data.decode("utf-8-sig"), url


def records(raw):
    reader = csv.DictReader(StringIO(raw))
    if not {"Date", *FIELDS.values()} <= set(reader.fieldnames or []):
        raise ValueError("Missing expected Treasury CSV fields")
    result = []
    for row in reader:
        values = [row[name] for name in FIELDS.values()]
        if any(x is None or x.strip().upper() in ("", "N/A", "NULL") for x in values):
            continue
        stamp = datetime.strptime(row["Date"], "%m/%d/%Y").date().isoformat()
        for month, raw_yield in zip(FIELDS, values):
            scaled = D(raw_yield) * 100
            if not scaled.is_finite() or not -10000 < scaled < 10000 or scaled != scaled.to_integral_value():
                raise ValueError("Invalid Treasury percentage quote")
            result.append((stamp, month, int(scaled)))
    if not result:
        raise ValueError("No complete quote observations in the CSV")
    return result


def stage(db, raw, source):
    rows = records(raw)
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE treasury_cmt(
            observation_date TEXT NOT NULL, maturity_months INTEGER NOT NULL,
            yield_bp INTEGER NOT NULL, source_url TEXT NOT NULL,
            PRIMARY KEY(observation_date, maturity_months)) STRICT""")
        conn.executemany("INSERT INTO treasury_cmt VALUES(?,?,?,?)", [(*r, source) for r in rows])
    return sorted({r[0] for r in rows})


def quote_values(db, stamp):
    with sqlite3.connect(db) as conn:
        return {m: conn.execute(SQL, (stamp, m)).fetchone()[0] for m in FIELDS}


def cells(stamp, quote_bp, source_url, linked=False):
    desk = {"A1": "Treasury-based curve lab | three-year illustrative swap",
            "A2": "Treasury yields are par benchmarks, not OIS quotes or market forwards.",
            "A4": "Observation date", "B4": "=Quotes!B3",
            "A5": "Notional, USD", "B5": 10_000_000,
            "A6": "Contract fixed rate", "B6": D("0.046"),
            "A7": "Pay fixed +1 / receive fixed -1", "B7": 1,
            "A9": "Illustrative fair fixed rate", "B9": "=(1-C19)/SUM(D14:D19)",
            "A10": "Signed illustrative PV (USD)", "B10": "=SUM(J14:J19)",
            "A11": "Pricing identity residual (USD)", "B11": "=B10-B7*B5*(1-C19-B6*SUM(D14:D19))"}
    table_row(desk, 13, "Term, months", "Accrual", "Discount", "Fixed annuity", "Implied forward",
              "Fixed flow", "Float flow", "Fixed PV", "Float PV", "Signed net PV")
    for r in range(14,20):
        c = r - 7
        table_row(desk, r, f"=Curve!A{c}", D("0.5"), f"=Curve!F{c}", f"=B{r}*C{r}", f"=Curve!H{c}",
                  f"=$B$5*$B$6*B{r}", f"=$B$5*E{r}*B{r}", f"=C{r}*F{r}", f"=C{r}*G{r}", f"=$B$7*(I{r}-H{r})")
    quotes = {"A1": "U.S. Treasury daily par yield inputs", "A2": "Linked via SQLite and SQLVALUE" if linked else "Portable snapshot selected with the same SQLite query",
              "A3": "Observation date", "B3": stamp,
              "A4": "Source URL", "B4": source_url, "A5": "Selection SQL", "B5": SQL}
    table_row(quotes, 7, "Tenor (months)", "Quoted yield (bp)", "Par yield")
    for r, (m, amount) in enumerate(quote_bp.items(), 8):
        table_row(quotes, r, m, f'=SQLVALUE("Treasury","{SQL}",$B$3,A{r})' if linked else amount,
                  f"=B{r}/10000")
    curve = {"A1": "Treasury par inputs → discount factors → model-implied forwards",
             "A2": "Annualized semiannual par yields. Missing term points use simple linear interpolation.",
             "A3": "Computed forwards are not official Treasury forward rates or SOFR/OIS prices.",
             "A4": "Half-year accrual", "B4": D("0.5")}
    table_row(curve, 6, "Tenor months", "Node origin", "Annual par yield", "Prior annuity", "Accrual",
              "Discount factor", "Residual (bp)", "Implied simple forward")
    for r, m in enumerate(range(6,61,6),7):
        if m in FIELDS:
            y = f"=Quotes!C{8+list(FIELDS).index(m)}"
        else:
            lo = max(k for k in FIELDS if k < m)
            hi = min(k for k in FIELDS if k > m)
            ql, qh = (8+list(FIELDS).index(k) for k in (lo,hi))
            y = f"=Quotes!C{ql}+(Quotes!C{qh}-Quotes!C{ql})*(A{r}-Quotes!A{ql})/(Quotes!A{qh}-Quotes!A{ql})"
        dprev = "1" if r == 7 else f"F{r-1}"
        ann = "0" if r == 7 else f"D{r-1}+E{r-1}*F{r-1}"
        table_row(curve, r, m, "Published CMT" if m in FIELDS else "Interpolated", y, f"={ann}", "=$B$4",
                  f"=(1-C{r}*D{r})/(1+C{r}*E{r})", f"=((1-F{r})/(D{r}+F{r}*E{r})-C{r})*10000",
                  f"=({dprev}/F{r}-1)/E{r}")
    return {"Sheet1":desk,"Quotes":quotes,"Curve":curve}


def oracle(inputs):
    with localcontext() as ctx:
        ctx.prec = 45
        yields, discounts = [], []
        for m in range(6,61,6):
            l, u = max(k for k in inputs if k<=m), min(k for k in inputs if k>=m)
            bps = D(inputs[l]) if l==u else D(inputs[l])+D(m-l)*D(inputs[u]-inputs[l])/D(u-l)
            coupon = bps / 20_000
            yields.append(bps/10_000)
            discounts.append((1-coupon*sum(discounts))/(1+coupon))
        ann = sum(discounts[:6])/2
        return (1-discounts[5])/ann, 10_000_000*(1-discounts[5]-D("0.046")*ann), discounts


@contextmanager
def http_server(exe, temp):
    env = {**os.environ, "GRIDLOOM_RECOVERY_DIR": str(temp / "recovery"), "RUST_LOG": "error"}
    with subprocess.Popen([exe,"--port","0"],stdout=subprocess.PIPE,text=True,env=env) as p:
        try:
            line=p.stdout.readline()
            site=re.search(r"http://127[.]0[.]0[.]1:[0-9]+",line)
            assert site,line
            def post(endpoint,**v):
                q=Request(site[0]+"/api/"+endpoint, data=json.dumps(v).encode(),
                          headers={"Content-Type":"application/json"})
                with urlopen(q,timeout=5) as response:
                    return json.load(response)
            yield post
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)


def verify(got, expected, error=D("0.000001")):
    assert abs(D(got)-expected)<error, (got, expected)


def write_models(p, db, stamp, rates, source):
    fair,pv,discounts=oracle(rates)
    with tempfile.TemporaryDirectory(prefix="gridloom-cmt-") as tmp:
        tmp=Path(tmp)
        snap="treasury-snapshot.gridloom"
        with MCP(p.mcp,tmp) as mcp:
            rev=mcp.call("create_workbook",file=snap)["revision"]
            for n in ("Quotes","Curve"):
                rev=mcp.call("add_sheet",sheet=n,revision=rev)["revision"]
            data=cells(stamp,rates,source)
            for n in ("Quotes","Curve","Sheet1"):
                rev=mcp.call("edit_cells",sheet=n,revision=rev,edits=[edit(k,v) for k,v in data[n].items()])["revision"]
            vals=mcp.cells("Sheet1","B9:B11")
            for key,v in (("B9",fair),("B10",pv),("B11",D(0))):
                verify(vals[key],v)
            exact=mcp.cells("Curve","F7:G16")
            for index,factor in enumerate(discounts,7):
                verify(exact[f"F{index}"],factor)
                verify(exact[f"G{index}"],D(0))
            mcp.call("save_workbook",revision=rev)
        with MCP(p.mcp,tmp) as mcp:
            mcp.call("open_workbook",file=snap)
            verify(mcp.cells("Sheet1","B10")["B10"],pv)
            trace=mcp.call("review_cell",sheet="Sheet1",cell="B10",limit=24)
            found=trace["trace"]
            while (offset:=trace["trace_page"]["next_offset"]) is not None:
                trace=mcp.call("review_cell",sheet="Sheet1",cell="B10",limit=24,offset=offset)
                found.extend(trace["trace"])
            assert any(x["sheet"]=="Quotes" and x["cell"]=="B11" for x in found)
        with (p.directory/snap).open("xb") as dest:
            dest.write((tmp/snap).read_bytes())
        if p.server:
            with http_server(p.server,tmp) as request:
                request("workbook/open",path=str((p.directory/snap).resolve()))
                request("connections",name="Treasury",kind="sqlite",path=str(db.resolve()))
                data=cells(stamp,rates,source,linked=True)
                request("ranges/edit",sheet_name="Quotes",row=1,col=0,values=[[data["Quotes"]["A2"]]])
                for r in range(8,13):
                    request("ranges/edit",sheet_name="Quotes",row=r-1,col=1,values=[[data["Quotes"][f"B{r}"]]])
                def read(sheet,row,col):
                    return request("cells/explain",sheet_name=sheet,row=row-1,col=col-1)["value"]["value"]
                verify(read("Sheet1",10,2),pv)
                evidence=request("cells/explain",sheet_name="Quotes",row=10,col=1)
                assert "SQLVALUE" in json.dumps(evidence) and "treasury_cmt" in json.dumps(evidence)
                path=str((p.directory/"treasury-linked.gridloom").resolve())
                request("workbook/save",path=path,create_only=True)
                request("workbook/open",path=path)
                verify(read("Sheet1",10,2),pv)
                # Disposable isolated database test; restore source after query verification.
                with sqlite3.connect(db) as conn:
                    conn.execute("UPDATE treasury_cmt SET yield_bp=yield_bp+25 WHERE observation_date=? AND maturity_months=36",(stamp,))
                try:
                    request("workbook/open",path=path)
                    _,reprice,_=oracle({**rates,36:rates[36]+25})
                    verify(read("Sheet1",10,2),reprice)
                    print("Live SQL reprice test (+25 bp at 3Y, temporary):",reprice)
                finally:
                    with sqlite3.connect(db) as conn:
                        conn.execute("UPDATE treasury_cmt SET yield_bp=? WHERE observation_date=? AND maturity_months=36",(rates[36],stamp))
    return fair,pv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp",required=True,type=lambda p:str(Path(p).resolve()))
    parser.add_argument("--server",type=lambda p:str(Path(p).resolve()),help="Optional Gridloom Linux server launcher for a local SQL-linked workbook")
    parser.add_argument("--directory",required=True,type=Path,help="New output directory")
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline",action="store_true",help="Use shipped 2026-11-20 Treasury observation")
    mode.add_argument("--as-of",type=date.fromisoformat,help="Fetch official CSV for the requested cutoff's month; select latest complete observation on or before cutoff")
    p=parser.parse_args()
    if p.offline:
        source=PUBLIC_TABLE+"202611"
        raw,cutoff=FALLBACK.read_text(),SNAPSHOT
    else:
        cutoff=p.as_of.isoformat()
        raw,source=get_csv(cutoff[:7].replace("-",""))
    p.directory.mkdir()
    db=p.directory/"treasury.sqlite"
    dates=stage(db,raw,source)
    available=[d for d in dates if d<=cutoff]
    if not available:
        raise ValueError("No complete observation on/before cutoff in selected month; choose previous month or --offline")
    stamp=max(available)
    vals=quote_values(db,stamp)
    fair,pv=write_models(p,db,stamp,vals,source)
    print(f"Observation {stamp}; yields in bp {vals}; fair {fair:.6%}; illustrative PV USD {pv:.2f}.")


if __name__=="__main__":
    main()
