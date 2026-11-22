#!/usr/bin/env python3
"""Check reported inputs, independent Decimal valuation, shocks and native review."""
import argparse, shutil, tempfile
from decimal import Decimal as D
from pathlib import Path
from build_alphabet import FILENAME, INPUTS
from build_dcf import ROOT
from verify_dcf import control, mcp, compare_decimal

def verify(binary, source):
    # This independent check transcribes core inputs separately from the builder's CSV.
    facts = {4:402836,5:289007,6:357269,8:129039,9:93105,10:121042,
             12:56334,13:208764,14:75200,15:135230,16:125102,17:1016,
             18:3705,19:385,20:50,21:6900,22:5888,23:828,24:5578,
             26:91447,27:63596,28:131953,30:21136,31:15096,32:21955,38:13807,39:3886}
    a={r:D(v) for r,_,v,_ in INPUTS if not v.startswith("=")}
    a.update({
        4:D(facts[4])+facts[6]-facts[5],
        21:D(facts[12])+facts[13]-facts[14]-15000,
        22:D(facts[14])*D(".70")+D(facts[15])*D(".80"),
        23:D(facts[16])+facts[17]+facts[18],
        24:D(facts[19])*facts[20]+facts[21]+facts[38]+facts[39],
        25:D(facts[22])+facts[23]+facts[24],
    })
    calc=control(a)
    with tempfile.TemporaryDirectory(prefix="alphabet-gridloom-qa-") as tmp:
        folder=Path(tmp)
        shutil.copyfile(source,folder/FILENAME)
        def verify_numbers(call):
            def val(sheet,addr):
                return call("read_cells",sheet=sheet,range=addr)["cells"][0]["value"]["value"]
            return val
        def review(call, **args):
            return call("review_cell",sheet="Valuation",cell="B13",**args)
        with mcp(binary,folder) as call:
            rev=call("open_workbook",file=FILENAME)["revision"]
            v=verify_numbers(call)
            for sheet,ran in {"Valuation":"A1:C21","Inputs":"A1:C25","Reported":"A1:C39",
                              "Bridge":"A1:C29","Forecast":"A1:H22","Capital":"A1:H14",
                              "Sensitivity":"A1:E11"}.items():
                assert call("validate_cells",sheet=sheet,range=ran)["errors"]==[],sheet
            for row, fact in facts.items():
                assert D(v("Reported",f"B{row}"))==fact,row
            compare_decimal(v("Reported","B7"),a[4]); assert D(v("Reported","B11"))==156976
            assert D(v("Reported","B29"))==159804 and D(v("Reported","B33"))==27995
            for row in range(21,26): compare_decimal(v("Inputs",f"B{row}"),a[row])
            compare_decimal(v("Valuation","B13"),calc["value"])
            compare_decimal(v("Valuation","B7"),calc["ev"])
            for i,col in enumerate("CDEFGH"):
                for row,expected in zip((5,9,12,13,14,17),calc["details"][i]):
                    compare_decimal(v("Forecast",f"{col}{row}"),expected)
            for i,col in enumerate("BCD",-1):
                for j,row in enumerate(range(6,9),-1):
                    compare_decimal(v("Sensitivity",f"{col}{row}"),
                                    calc["sensitivity"](a[10]+D(i)*D(".005"),calc["wacc"]+D(j)*D(".005")))
            for addr in ("B4","B19","B20"):assert v("Valuation",addr)=="OK",addr
            r=review(call,limit=24); assert r["can_mark_reviewed"] and r["trace_page"]["total"]>40,r
            def edit(sheet, addr, value):
                nonlocal rev
                rev=call("edit_cells",sheet=sheet,revision=rev,
                    edits=[{"cell":addr,"input":{"type":"decimal","value":value}}])["revision"]
            # ERP and regulated-asset haircut are independent shocks, not projections.
            edit("Inputs","B14","0.06")
            erp=control({**a,14:D(".06")})["value"]
            compare_decimal(v("Valuation","B13"),erp); assert erp<calc["value"]
            edit("Inputs","B14","0.05")
            edit("Inputs","B10","0.10")
            assert v("Valuation","B13")=="INVALID" and v("Forecast","H21")=="INVALID"
            edit("Inputs","B10","0.028")
            r=review(call)
            rr=call("record_review",sheet="Valuation",cell="B13",revision=r["revision"],
                expected_snapshot=r["snapshot"],decision="reviewed",agent_label="Alphabet arithmetic check",
                note="Recomputed the filed-data bridge, explicit FCFF, WACC and sensitivity independently.",
                evidence=[{"label":"Alphabet Q3 SEC filing","reference":"10-Q accession 0001652044-26-000084"}])
            rev=rr["revision"]; assert review(call)["status"]=="review_current"
            edit("Bridge","B11","0.60")
            shock=calc["value"]-D("7520")/a[25]
            compare_decimal(v("Valuation","B13"),shock)
            assert review(call)["status"]=="review_stale"
            comparison=call("compare_review",review_id=rr["record"]["review_id"])
            assert any(x.get("sheet")=="Bridge" and x.get("cell")=="B11" for x in comparison["changes"]),comparison
            saved=call("save_workbook",revision=rev)
        with mcp(binary,folder) as call:
            rev=call("open_workbook",file=FILENAME)["revision"]
            compare_decimal(verify_numbers(call)("Valuation","B13"),shock)
            assert review(call)["status"]=="review_stale"
            call("edit_cells",sheet="Bridge",revision=rev,
                edits=[{"cell":"B11","input":{"type":"decimal","value":"0.70"}}])
            compare_decimal(verify_numbers(call)("Valuation","B13"),calc["value"])
            assert review(call)["status"]=="review_stale"
    print(f"PASS Alphabet: LTM revenue ${a[4]}m; EV ${calc['ev']:.6f}m; scenario ${calc['value']:.8f} per common-equivalent share; stable WACC {calc['wacc']:.5%}.")
    print(f"PASS: ERP +100 bp ${erp:.8f}; lower SpaceX retention ${shock:.8f}; invalid growth blocked; stale review and exact values survived reopen and input restoration.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("gridloom_mcp",type=Path)
    p.add_argument("--workbook",type=Path,default=ROOT/"workbooks"/FILENAME)
    a=p.parse_args()
    verify(a.gridloom_mcp,a.workbook)
