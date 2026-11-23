#!/usr/bin/env python3
"""Compare native workbook values with an independent, exact Decimal FCFF control."""
from contextlib import contextmanager
from decimal import Decimal as D, getcontext
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import tempfile

from build_dcf import INPUTS, FILENAME, ROOT
getcontext().prec = 44
TOL = D("0.000000001")

@contextmanager
def mcp(binary, folder):
    with subprocess.Popen([str(binary.resolve()),"--workbook-root",str(folder)],
                          stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding="utf-8") as proc:
        counter=0
        def send(msg):
            proc.stdin.write(json.dumps({"jsonrpc":"2.0", **msg})+"\n")
            proc.stdin.flush()
        def rpc(method, params=None):
            nonlocal counter
            counter+=1
            send({"method":method,"id":counter,"params":params or {}})
            data=json.loads(proc.stdout.readline())
            assert data.get("id")==counter and "error" not in data,data
            return data["result"]
        def call(name, **args):
            result=rpc("tools/call",{"name":name,"arguments":args})
            assert not result.get("isError"),result
            return result["structuredContent"]
        try:
            assert rpc("initialize", {"protocolVersion":"2025-11-25","capabilities":{},
                    "clientInfo":{"name":"tayriva-fixture-check","version":"1"}})["protocolVersion"]=="2025-11-25"
            send({"method":"notifications/initialized"})
            yield call
        finally:
            proc.stdin.close()
            proc.wait(timeout=15)

def control(a):
    revenue=a[4]; total=D(0); df=D(1); details=[]
    for year in range(1,7):
        t=D(max(0,year-3))/3
        fade=lambda first,last: (1-t)*a[first]+t*a[last]
        rate=fade(5,10)
        delta=revenue*rate
        revenue+=delta
        np=revenue*fade(6,11)*(1-a[7])
        capital=delta/fade(8,9)
        beta=fade(15,16)
        spread=fade(17,18)
        debt=fade(19,20)
        cost=(1-debt)*(a[13]+beta*a[14])+debt*(a[13]+spread)*(1-a[7])
        fcff=np-capital
        df*=1+cost
        pv=fcff/df
        total+=pv
        details.append((revenue,np,capital,fcff,cost,pv))
    adjustments=a[21]+a[22]-a[23]-a[24]
    def per_share(g,wacc):
        if not (D(0)<=g<min(wacc,a[12])):return None
        return (total+(np*(1+g)*(1-g/a[12]))/((wacc-g)*df)+adjustments)/a[25]
    s=per_share(a[10],cost)
    ev=None if s is None else s*a[25]-adjustments
    return dict(value=s, ev=ev, pv=total, wacc=cost, details=details, sensitivity=per_share)

def compare_decimal(got,want):
    assert isinstance(want,D) and abs(D(got)-want)<TOL,(got,want)

def verify(binary, workbook):
    with tempfile.TemporaryDirectory(prefix="tayriva-verify-dcf-") as d:
        path=Path(d)
        shutil.copyfile(workbook,path/FILENAME)
        values={r:D(v) for r,_,v,_ in INPUTS}
        baseline=control(values)
        with mcp(binary,path) as call:
            rev=call("open_workbook",file=FILENAME)["revision"]
            def data(sheet,range):
                return call("read_cells",sheet=sheet,range=range)["cells"]
            def result(sheet,cell): return data(sheet,cell)[0]["value"]["value"]
            def review(): return call("review_cell",sheet="Valuation",cell="B13",limit=15)
            def shock(row,value):
                nonlocal rev
                rev=call("edit_cells",sheet="Inputs",revision=rev,edits=[{"cell":f"B{row}","input":{"type":"decimal","value":str(value)}}])["revision"]
                return control({**values,row:D(value)})
            for sheet,rng in {"Valuation":"A1:C21","Inputs":"A1:C25","Capital":"A1:H14","Forecast":"A1:H22","Sensitivity":"A1:E11"}.items():
                assert call("validate_cells",sheet=sheet,range=rng)["errors"]==[],sheet
            compare_decimal(result("Valuation","B13"),baseline["value"])
            compare_decimal(result("Valuation","B7"),baseline["ev"])
            compare_decimal(result("Valuation","B5"),baseline["pv"])
            compare_decimal(result("Valuation","B14"),baseline["wacc"])
            for addr in ("B4","B19","B20"):
                assert result("Valuation",addr)=="OK",addr
            for i,col in enumerate("CDEFGH"):
                for row,expected in zip((5,9,12,13,14,17),baseline["details"][i]):
                    compare_decimal(result("Forecast",f"{col}{row}"),expected)
            for i,col in enumerate("BCD",-1):
                for j,row in enumerate(range(6,9),-1):
                    compare_decimal(result("Sensitivity",f"{col}{row}"),
                                    baseline["sensitivity"](values[10]+D(i)*D(".005"),baseline["wacc"]+D(j)*D(".005")))
            found=review()
            assert found["can_mark_reviewed"] and found["trace_page"]["total"]>20,found
            r=call("record_review",sheet="Valuation",cell="B13",revision=found["revision"],
                   expected_snapshot=found["snapshot"],decision="reviewed",
                   agent_label="Synthetic DCF independent control",
                   note="Exact Decimal control agrees within 1e-9 USD per share; all forecast periods and the sensitivity grid checked.")
            rev=r["revision"]
            assert review()["status"]=="review_current"
            erp=shock(14,"0.06")
            compare_decimal(result("Valuation","B13"),erp["value"])
            assert erp["value"]<baseline["value"] and review()["status"]=="review_stale"
            saved=call("save_workbook",revision=rev)
            rev=saved["revision"]
        with mcp(binary,path) as call:
            rev=call("open_workbook",file=FILENAME)["revision"]
            compare_decimal(result("Valuation","B13"),erp["value"])
            assert review()["status"]=="review_stale"
            shock(14,values[14])
            stronger=shock(10,"0.0325")
            compare_decimal(result("Valuation","B13"),stronger["value"])
            assert stronger["value"]>baseline["value"]
            invalid=shock(10,"0.10")
            assert invalid["value"] is None and result("Valuation","B13")=="INVALID"
            assert result("Valuation","B4")=="INVALID" and result("Forecast","H21")=="INVALID"
            shock(10,values[10])
            compare_decimal(result("Valuation","B13"),baseline["value"])
            assert review()["status"]=="review_stale"
        print(f"PASS baseline: ${baseline['value']:.8f}/share, EV ${baseline['ev']:.8f}m, stable WACC {baseline['wacc']:.5%}; six forecast periods and all nine sensitivity cells match.")
        print(f"PASS ERP shock: ${erp['value']:.8f}/share; higher g: ${stronger['value']:.8f}/share; WACC <= g blocked; review stale after transitive edit, persisted on reopen and remained stale after restoration.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("tayriva_mcp",type=Path)
    p.add_argument("--workbook", type=Path,default=ROOT/"workbooks"/FILENAME)
    a=p.parse_args()
    verify(a.tayriva_mcp,a.workbook)
