#!/usr/bin/env python3
"""Build and verify a synthetic reconciliation fixture with a deliberate mapping swap."""
import argparse
from decimal import Decimal
from pathlib import Path
import shutil
import tempfile
from build_dcf import local_app, ROOT
from verify_dcf import mcp

FILENAME="the-total-still-ties.gridloom"

def build(binary, output):
    output=output.resolve()
    if output.exists(): raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with local_app(binary) as post:
        post("sheets/rename",old_name="Sheet1",new_name="Reconciliation")
        post("sheets",name="Ledger")
        def set_cell(sheet,r,c,val):
            post("cells/set",sheet_name=sheet,row=r-1,col=c-1,raw_input=str(val))
        for r,vs in {
          1:["THE TOTAL STILL TIES"],
          2:["Synthetic GL mapping exercise   ·   USD"],
          3:["Report category","Ledger tag (editable)","Mapped actual","Independent control","Variance","Control"],
          4:["Software","Rent","=SUMIF(Ledger!A4:A5,B4,Ledger!B4:B5)","40.10","=C4-D4",'=IF(E4=0,"PASS","FLAG")'],
          5:["Rent","Software","=SUMIF(Ledger!A4:A5,B5,Ledger!B4:B5)","60.15","=C5-D5",'=IF(E5=0,"PASS","FLAG")'],
          7:["Total","","=SUM(C4:C5)","=SUM(D4:D5)","=C7-D7",'=IF(E7=0,"TIES ONLY","FLAG")'],
          8:["Model status","","","","",'=IF(AND(E4=0,E5=0,E7=0),"PASS","INVESTIGATE")'],
          10:["WHAT HAPPENED?","The mappings are crossed. Trace C4 and C5 before fixing B4 and B5."],
          11:["TRY IT","With the mappings fixed, review C7. Then reallocate $1 between the two source tags."],
          12:["WATCH THE REVIEW","The total stays $100.25, but the review becomes stale."],
        }.items():
            for c,v in enumerate(vs,1):
                if v!="":set_cell("Reconciliation",r,c,v)
        for r,vs in {1:["SYNTHETIC GENERAL LEDGER"],2:["Category mapping input, not a real company ledger"],
                     3:["Tag","Signed amount","Reference"],4:["Software","40.10","GL-010"],5:["Rent","60.15","GL-011"]}.items():
            for c,v in enumerate(vs,1):set_cell("Ledger",r,c,v)
        def style(sheet,r,a,b,fill=None,bold=False,fmt=None):
            post("ranges/format",sheet_name=sheet,
                 range=dict(start_row=r-1,end_row=r-1,start_col=a-1,end_col=b-1),
                 style=dict(fill=fill,bold=bold,italic=False,number_format=fmt))
        for sheet,widths in [("Reconciliation",[220,215,155,185,125,155]),("Ledger",[290,180,190])]:
            for i,w in enumerate(widths):post("sheets/column-width",sheet_name=sheet,column=i,width=w)
            style(sheet,1,1,len(widths),"#bfdbfe",True)
            style(sheet,3,1,len(widths),"#e2e8f0",True)
        for r in [4,5]:
            style("Reconciliation",r,2,2,"#eff6ff")
            style("Reconciliation",r,3,5,fmt="0.00")
            style("Ledger",r,2,2,fmt="0.00")
        style("Reconciliation",7,1,6,"#e0e7ff",True)
        style("Reconciliation",7,3,5,"#e0e7ff",True,"0.00")
        post("sheets/select",name="Reconciliation")
        post("workbook/save",path=str(output))

def verify(binary, workbook):
    with tempfile.TemporaryDirectory(prefix="gridloom-verify-gl-") as d:
        dest=Path(d)
        shutil.copyfile(workbook,dest/FILENAME)
        with mcp(binary,dest) as call:
            rev=call("open_workbook",file=FILENAME)["revision"]
            def cell(sheet,key):return call("read_cells",sheet=sheet,range=key)["cells"][0]["value"]["value"]
            def report(*keys):return [cell("Reconciliation",k) for k in keys]
            def edit(sheet,field,inputs):
                nonlocal rev
                changes=[{"cell":k,"input":{"type":field,"value":v}} for k,v in inputs.items()]
                rev=call("edit_cells",sheet=sheet,revision=rev,edits=changes)["revision"]
            def review():
                return call("review_cell",sheet="Reconciliation",cell="C7")
            assert report("F4","F5","F7","F8")==["FLAG","FLAG","TIES ONLY","INVESTIGATE"]
            decimal=lambda xs:list(map(Decimal,xs))
            assert decimal(report("C4","C5","C7"))==decimal(["60.15","40.10","100.25"])
            edit("Reconciliation","text",{"B4":"Software","B5":"Rent"})
            assert report("F4","F5","F8")==["PASS","PASS","PASS"]
            assert decimal(report("C4","C5","C7"))==decimal(["40.10","60.15","100.25"])
            now=review()
            result=call("record_review",sheet="Reconciliation",cell="C7",revision=now["revision"],
                        expected_snapshot=now["snapshot"],decision="reviewed",agent_label="Synthetic ledger check",
                        note="Confirmed both label-level controls independently; total is not the only check.")
            rev=result["revision"]
            assert review()["status"]=="review_current"
            edit("Ledger","decimal",{"B4":"41.10","B5":"59.15"})
            assert decimal(report("E4","E5","E7","C7"))==decimal(["1.00","-1.00","0","100.25"])
            assert review()["status"]=="review_stale"
            changes=call("compare_review",review_id=result["record"]["review_id"])["changes"]
            changed={entry["cell"] for entry in changes if entry.get("category")=="input"}
            assert {"B4","B5"}<=changed,changes
            call("save_workbook",revision=rev)
        with mcp(binary,dest) as call:
            call("open_workbook",file=FILENAME)
            persisted=call("review_cell",sheet="Reconciliation",cell="C7")
            assert persisted["status"]=="review_stale"
    print("PASS total 100.25 ties before/after fixing intentional swap; ±1.00 reallocation leaves total unchanged, invalidates review, and survives reopen.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=["build","verify"])
    p.add_argument("binary",type=Path,help="Gridloom server or MCP launcher, respectively")
    p.add_argument("--workbook",type=Path,default=ROOT/"workbooks"/FILENAME)
    a=p.parse_args()
    (build if a.command=="build" else verify)(a.binary,a.workbook)
