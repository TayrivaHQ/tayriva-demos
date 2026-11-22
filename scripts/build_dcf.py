#!/usr/bin/env python3
"""Generate the native FCFF demo through a private local Gridloom process."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import json, os, re, subprocess, tempfile, time
from urllib.request import Request, urlopen

FILENAME = "sterling-harbor-fcff.gridloom"
ROOT = Path(__file__).resolve().parents[1]
# USD millions (except rates, ratios, and shares in millions). Entirely fictional.
INPUTS = [
    (4,"Base-year revenue", "120", "Reference-year net sales"),
    (5,"High-growth sales growth","0.14","Years 1–3"),
    (6,"High-growth EBIT margin","0.21","Years 1–3"),
    (7,"Marginal tax rate","0.25","Concurrent operating and debt tax rate"),
    (8,"High-growth sales / capital","2.1","Incremental revenue per net investment dollar"),
    (9,"Stable sales / capital","2.6","Sales / capital reached in Year 6; terminal uses ROIC instead"),
    (10,"Stable growth","0.0275","Nominal USD perpetual growth"),
    (11,"Stable EBIT margin","0.18","Reached in Year 6"),
    (12,"Stable ROIC","0.12","Marginal after-tax return on new invested capital"),
    (13,"Risk-free rate","0.04","Illustrative nominal USD input; not a market quote"),
    (14,"Equity risk premium","0.05","Illustrative, not a Damodaran dataset"),
    (15,"High-growth levered beta","1.25","Years 1–3"),
    (16,"Stable levered beta","0.95","Reached in Year 6"),
    (17,"High-growth debt spread","0.021","Years 1–3"),
    (18,"Stable debt spread","0.012","Reached in Year 6"),
    (19,"High-growth debt weight","0.20","Target market debt / (debt + equity)"),
    (20,"Stable debt weight","0.28","Target market debt / (debt + equity)"),
    (21,"Excess cash","18","Non-operating; added to the value of operations"),
    (22,"Other non-operating assets","5","Added to the value of operations"),
    (23,"Debt in equity bridge","37","Deducted from value of operations"),
    (24,"Other claims","2","Deducted from value of operations"),
    (25,"Diluted shares (millions)","10","Divide USD millions of equity by million shares"),
]
LAYOUT = {
    "Valuation": [330,190,490],
    "Inputs": [290,155,560],
    "Capital": [290,110,110,120,125,125,125,125],
    "Forecast": [335,107,107,115,115,120,120,120],
    "Sensitivity": [335,140,140,140,410],
}

@contextmanager
def local_app(binary):
    with tempfile.TemporaryDirectory(prefix="gridloom-dcf-") as temp:
        folder=Path(temp)
        log=folder/"server.log"
        with log.open("wb") as output, subprocess.Popen(
            [str(binary.resolve()), "--port", "0"], cwd=folder, stdout=output, stderr=subprocess.STDOUT,
            env={**os.environ, "GRIDLOOM_RECOVERY_DIR":str(folder/"recovery")},
        ) as proc:
            try:
                for _ in range(250):
                    match=re.search(rb"Server running at (http://127\.0\.0\.1:\d+)", log.read_bytes())
                    if match: break
                    if proc.poll() is not None: raise RuntimeError(log.read_text())
                    time.sleep(.05)
                else: raise RuntimeError(log.read_text())
                base=match[1].decode()
                def post(endpoint, **data):
                    r=Request(base+"/api/"+endpoint, json.dumps(data).encode(), {"Content-Type":"application/json"})
                    try:
                        with urlopen(r,timeout=15) as response:
                            return json.load(response)
                    except Exception as error:
                        if hasattr(error,"read"):
                            raise RuntimeError(f"{endpoint}: {error.read().decode()}") from error
                        raise
                yield post
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=8)

def generate(binary, output, *, profile=None):
    profile=profile or {}
    inputs=profile.get("inputs",INPUTS)
    layout=LAYOUT | profile.get("additional_layout",{})
    output = output.resolve()
    if output.exists(): raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with local_app(binary) as post:
        post("sheets/rename",old_name="Sheet1",new_name="Valuation")
        for sheet in list(layout)[1:]: post("sheets",name=sheet)
        def put(sheet,row,col,val):
            post("cells/set",sheet_name=sheet,row=row-1,col=col-1,raw_input=str(val))
        def row(sheet,index,*items):
            for column,val in enumerate(items,1):
                if val != "": put(sheet,index,column,val)
        def style(sheet,row,last,fill=None,bold=False,start=1,fmt=None):
            post("ranges/format",sheet_name=sheet,
                 range=dict(start_row=row-1,end_row=row-1,start_col=start-1,end_col=last-1),
                 style=dict(fill=fill,bold=bold,italic=False,number_format=fmt))
        for sheet,widths in layout.items():
            for i,width in enumerate(widths): post("sheets/column-width",sheet_name=sheet,column=i,width=width)
        row("Valuation",1,profile.get("title","STERLING HARBOR SYSTEMS  /  FCFF DCF"))
        row("Valuation",2,profile.get("subtitle","Fictional operating-asset valuation"))
        row("Valuation",3,"Metric","USD millions unless noted","Read the model")
        values=[
            (4,"Model control",'=IF(AND(B14>B15,Inputs!B12>Inputs!B10,Inputs!B25>0,Inputs!B8>0,Inputs!B9>0,Inputs!B10>=0,Inputs!B7>=0,Inputs!B7<1,Inputs!B19>=0,Inputs!B19<=1,Inputs!B20>=0,Inputs!B20<=1,Inputs!B13>-1),"OK","INVALID")',"Stable WACC and ROIC must both exceed g; see inputs"),
            (5,"PV of explicit FCFF","=SUM(Forecast!C17:H17)","Years 1–6, discounted at year-specific WACC"),
            (6,"PV of terminal value",'=IF(B4="OK",Forecast!H22,"INVALID")',"Terminal value discounted from the end of Year 6"),
            (7,"Enterprise value",'=IF(B4="OK",B5+B6,"INVALID")',"Value of operating assets before financing"),
            (8,"Excess cash","=Inputs!B21","Added"),
            (9,"Other non-operating assets","=Inputs!B22","Added"),
            (10,"Debt","=Inputs!B23","Deducted"),
            (11,"Other claims","=Inputs!B24","Deducted"),
            (12,"Equity value",'=IF(B4="OK",B7+B8+B9-B10-B11,"INVALID")',"Operating value plus non-operating assets less claims"),
            (13,profile.get("per_share_label","Value per diluted share (USD)"),'=IF(B4="OK",B12/Inputs!B25,"INVALID")',"Select B13 and open Review → Explain & Review"),
            (14,"Stable WACC","=Capital!H12","Risk-free rate, beta × ERP and after-tax debt costs"),
            (15,"Perpetual growth (g)","=Inputs!B10","Keep g below stable WACC"),
            (16,"Terminal reinvestment rate",'=IF(B4="OK",Forecast!H19,"INVALID")',"Stable growth / stable ROIC"),
            (17,"Terminal PV share of EV",'=IF(B4="OK",B6/B7,"INVALID")',"Share of enterprise value from the terminal period"),
            (18,"Terminal spread (WACC − g)","=B14-B15","Positive spread is required"),
        ]
        for index,*items in values: row("Valuation",index,*items)
        row("Valuation",19,"Capital weight checks",'=IF(AND(Capital!C14=1,Capital!D14=1,Capital!E14=1,Capital!F14=1,Capital!G14=1,Capital!H14=1),"OK","INVALID")',"Debt and equity weights sum to 100% in all six years")
        row("Valuation",20,"Sensitivity baseline tie",'=IF(B4="OK",IF(ABS(B13-Sensitivity!C7)<0.000001,"OK","CHECK"),"INVALID")',"Midpoint of the terminal sensitivity must equal base per share")
        if profile.get("explicit_per_share_rounding"):
            row("Valuation",22,"Scenario value per share (rounded)",'=IF(B4="OK",ROUND(B13,2),"INVALID")',
                "Display only, rounded to cents; review the exact result in B13.")
        row("Valuation",21,"TRACE IT","B13 → Forecast → Inputs","Change Inputs!B14, then revisit B13 to see a review go stale.")
        row("Inputs",1,"MODEL ASSUMPTIONS")
        row("Inputs",2,profile.get("inputs_subtitle","All inputs are original synthetic values."))
        row("Inputs",3,"Assumption","Value","Notes")
        for index,*items in inputs: row("Inputs",index,*items)
        for sheet, records in profile.get("additional_rows",{}).items():
            for index,*items in records: row(sheet,index,*items)
        for sheet, title in [("Capital","COST OF CAPITAL  /  CAPM & MARKET WEIGHTS"),("Forecast","OPERATING FORECAST  /  FREE CASH FLOW TO THE FIRM")]:
            row(sheet,1,title)
            row(sheet,2,"Nominal USD; year-end discounting")
            row(sheet,3,"Line item","Base","Year 1","Year 2","Year 3","Year 4","Year 5","Year 6")
        rows_cap={4:"Transition share",5:"Risk-free rate",6:"Equity risk premium",7:"Levered beta",8:"Cost of equity",9:"Debt spread",10:"After-tax cost of debt",11:"Market debt weight",12:"Weighted cost of capital",13:"Market equity weight",14:"Weight sum check"}
        rows_fc={4:"Sales growth",5:"Revenue",6:"Operating (EBIT) margin",7:"EBIT",8:"Tax rate",9:"After-tax operating profit",10:"Change in revenue",11:"Sales / capital",12:"Net reinvestment",13:"Free cash flow to firm",14:"WACC",15:"Year-end discount factor",17:"PV of FCFF",18:"Year 7 after-tax operating profit",19:"Terminal reinvestment rate",20:"Year 7 FCFF",21:"End-of-Year-6 terminal value",22:"PV of terminal value"}
        for index,label in rows_cap.items(): put("Capital",index,1,label)
        for index,label in rows_fc.items(): put("Forecast",index,1,label)
        put("Forecast",5,2,"=Inputs!B4")
        put("Forecast",15,2,"1")
        for n,x in enumerate("CDEFGH",1):
            prev=chr(ord(x)-1)
            cap={4:f"={max(0,n-3)}/3",5:"=Inputs!B13",6:"=Inputs!B14",
                 7:f"=Inputs!B15+(Inputs!B16-Inputs!B15)*{x}4",
                 8:f"={x}5+{x}6*{x}7",9:f"=Inputs!B17+(Inputs!B18-Inputs!B17)*{x}4",
                 10:f"=({x}5+{x}9)*(1-Inputs!B7)",11:f"=Inputs!B19+(Inputs!B20-Inputs!B19)*{x}4",
                 12:f"={x}8*{x}13+{x}10*{x}11",13:f"=1-{x}11",14:f"={x}11+{x}13"}
            fc={4:f"=Inputs!B5+(Inputs!B10-Inputs!B5)*Capital!{x}4",5:f"={prev}5*(1+{x}4)",
                6:f"=Inputs!B6+(Inputs!B11-Inputs!B6)*Capital!{x}4",7:f"={x}5*{x}6",8:"=Inputs!B7",
                9:f"={x}7*(1-{x}8)",10:f"={x}5-{prev}5",
                11:f"=Inputs!B8+(Inputs!B9-Inputs!B8)*Capital!{x}4",
                12:f"=IF({x}11>0,{x}10/{x}11,\"INVALID\")",13:f"={x}9-{x}12",14:f"=Capital!{x}12",
                15:f"={prev}15*(1+{x}14)",17:f"={x}13/{x}15"}
            for rr,v in cap.items(): put("Capital",rr,n+2,v)
            for rr,v in fc.items(): put("Forecast",rr,n+2,v)
        for rr,v in {18:"=H9*(1+Inputs!B10)",19:'=IF(Inputs!B12>Inputs!B10,Inputs!B10/Inputs!B12,"INVALID")',20:'=IF(Inputs!B12>Inputs!B10,H18*(1-H19),"INVALID")',21:'=IF(AND(H14>Inputs!B10,Inputs!B12>Inputs!B10),H20/(H14-Inputs!B10),"INVALID")',22:'=IF(AND(H14>Inputs!B10,Inputs!B12>Inputs!B10),H21/H15,"INVALID")'}.items(): put("Forecast",rr,8,v)
        row("Sensitivity",1,"TERMINAL VALUE SENSITIVITY  /  USD PER SHARE")
        row("Sensitivity",2,"Isolated terminal changes; explicit forecast and its discount factors are held fixed.")
        row("Sensitivity",3,"Shift size","0.005","","","Half a percentage point")
        row("Sensitivity",5,"Terminal WACC ↓ / perpetual growth →","=Inputs!B10-$B$3","=Inputs!B10","=Inputs!B10+$B$3")
        for rr, rate in [(6,"=Capital!H12-$B$3"),(7,"=Capital!H12"),(8,"=Capital!H12+$B$3")]:
            put("Sensitivity",rr,1,rate)
            for idx, col in enumerate("BCD",2):
                g=f"{col}$5"; w=f"$A{rr}"
                put("Sensitivity",rr,idx,f'=IF(AND({g}>=0,{w}>{g},Inputs!B12>{g},Inputs!B25>0),((Valuation!B5+Forecast!H9*(1+{g})*(1-{g}/Inputs!B12)/({w}-{g})/Forecast!H15)+Valuation!B8+Valuation!B9-Valuation!B10-Valuation!B11)/Inputs!B25,"INVALID")')
        row("Sensitivity",10,"CENTRAL CASE","C7 ties to Valuation!B13.")
        row("Sensitivity",11,"Do not treat the grid as a full scenario forecast.")
        style("Sensitivity",3,2,"#eff6ff",True,start=2,fmt="0.00%")
        style("Sensitivity",5,4,"#e2e8f0",True,start=2,fmt="0.00%")
        for rr in (6,7,8):
            style("Sensitivity",rr,1,"#e2e8f0",True,fmt="0.00%")
            style("Sensitivity",rr,4,None,False,start=2,fmt="0.00")
        style("Sensitivity",7,3,"#e0e7ff",True,start=3,fmt="0.00")
        for sheet,widths in layout.items():
            style(sheet,1,len(widths),"#bfdbfe",True)
            if sheet!="Sensitivity": style(sheet,3,len(widths),"#e2e8f0",True)
        for rr,*_ in values:
            special=rr in (7,12,13)
            if special: style("Valuation",rr,3,"#e0e7ff",True)
            if rr!=4: style("Valuation",rr,2,"#e0e7ff" if special else None,special,start=2,fmt="0.00%" if rr>=14 else (None if rr==13 and profile.get("explicit_per_share_rounding") else "0.00"))
        for rr,_,raw,_ in inputs: style("Inputs",rr,2,"#f1f5f9" if str(raw).startswith("=") else "#eff6ff",False,start=2,fmt="0.00%" if rr in [5,6,7,10,11,12,13,14,17,18,19,20] else "0.00")
        for sheet, rows, rates in [("Capital",rows_cap,{4,5,6,8,9,10,11,12,13,14}),("Forecast",rows_fc,{4,6,8,14,19})]:
            for rr in rows:
                special=(sheet=="Capital" and rr==12) or (sheet=="Forecast" and rr in (13,17,22))
                if special: style(sheet,rr,8,"#e0e7ff",True)
                style(sheet,rr,8,"#e0e7ff" if special else None,special,start=2,fmt="0.00%" if rr in rates else "0.00")
        for sheet, records in profile.get("additional_rows",{}).items():
            for index,_,value,*_ in records:
                if isinstance(value,str) and (value.startswith("=") or value.replace(".","",1).lstrip("-").isdigit()):
                    style(sheet,index,2,"#f1f5f9" if value.startswith("=") else ("#eff6ff" if sheet=="Bridge" else "#ecfdf5"),
                          False,start=2,fmt="0.00%" if (sheet,index) in profile.get("percentage_cells",()) else "0.00")
        post("sheets/select",name="Valuation")
        post("workbook/save",path=str(output))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gridloom_server",type=Path,help="Bundled Linux server launcher (gridloom)")
    parser.add_argument("--output",type=Path,default=ROOT/"workbooks"/FILENAME)
    a=parser.parse_args()
    generate(a.gridloom_server,a.output)
