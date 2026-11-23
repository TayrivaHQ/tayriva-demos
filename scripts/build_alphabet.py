#!/usr/bin/env python3
"""Build Alphabet's educational, filed-data-anchored DCF in native Tayriva."""
import argparse, csv
from pathlib import Path
from build_dcf import ROOT, generate

FILENAME = "alphabet-fcff.tay"
Q = "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000084/goog-20260930.htm"
K = "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm"
INPUTS = [
    (4,"Base-year revenue", "=Reported!B7", "Reported trailing 12 months to September 30, 2026"),
    (5,"High-growth sales growth","0.14","Assumption · years 1–3"),
    (6,"High-growth EBIT margin","0.325","Assumption · compare with reported LTM margin"),
    (7,"Marginal tax rate","0.24","Assumption · marginal operating and debt rate, not effective filed rate"),
    (8,"High-growth sales / capital","0.55","Assumption · elevated AI-era incremental capital intensity"),
    (9,"Stable sales / capital","2.0","Assumption · reached in Year 6; terminal uses ROIC"),
    (10,"Stable growth","0.028","Assumption · nominal USD perpetual growth"),
    (11,"Stable EBIT margin","0.31","Assumption · mature blended margin"),
    (12,"Stable ROIC","0.16","Assumption · after-tax marginal return on new invested capital"),
    (13,"Risk-free rate","0.042","Illustrative USD scenario input; not a live Treasury quote"),
    (14,"Equity risk premium","0.05","Illustrative nominal USD scenario input, not market data"),
    (15,"High-growth levered beta","1.12","Assumption · not a regression estimate"),
    (16,"Stable levered beta","1.0","Assumption · reached in Year 6"),
    (17,"High-growth debt spread","0.012","Assumption · not an observed credit spread"),
    (18,"Stable debt spread","0.01","Assumption · reached in Year 6"),
    (19,"High-growth debt weight","0.05","Assumption · target market-value weight, not carrying leverage"),
    (20,"Stable debt weight","0.08","Assumption · target market-value weight"),
    (21,"Excess liquid financial assets","=Bridge!B8","Operating cash excluded; SpaceX stake separated below"),
    (22,"Other non-operating assets","=Bridge!B15","Haircut-adjusted restricted SpaceX and non-marketable investments"),
    (23,"Debt and finance leases","=Bridge!B19","Book debt proxy, current + long-term + finance lease liabilities"),
    (24,"Preferred, minority and other claims","=Bridge!B23","Preferred, NCI, separately modeled fines and broker payables"),
    (25,"Common shares (millions)","=Bridge!B29","Class A + Class B + Class C at quarter-end; equal economic value proxy"),
]

def profile():
    with (ROOT/"data/alphabet-reported.csv").open(newline="") as f:
        facts=tuple(csv.DictReader(f))
    reported=[
        (1,"ALPHABET INC. / FILED INPUTS","",""),
        (2,"USD millions unless indicated","","Blue header; green = transcribed filing value; gray = calculated"),
        (3,"Reported inputs / historical check","Value","Period / location"),
        *[(int(r["Row"]),r["Metric"],r["USDm_or_million_shares"],f"{r['Period']} · {r['Source']} · {r['Location']}") for r in facts],
        (7,"LTM revenue","=B4+B6-B5","FY25 + 9M26 − 9M25"),
        (11,"LTM EBIT","=B8+B10-B9","Uses operating income; excludes gains from equity investments"),
        (25,"LTM EBIT margin","=B11/B7","Ratio before formatting; used as a comparison for assumptions"),
        (29,"LTM cash purchases of PPE","=B26+B28-B27","Reported positive cash-outflow magnitude"),
        (33,"LTM depreciation of PP&E","=B30+B32-B31","Historical PP&E depreciation; not total D&A"),
        (34,"LTM cash PPE less PP&E depreciation","=B29-B33","Historical calibration only; excludes net working capital and noncash PPE"),
        (36,"SEC 10-Q (filed 2026-10-29)","",Q),
        (37,"SEC 10-K (filed 2026-02-05)","",K),
    ]
    bridge=[
        (1,"ALPHABET INC. / COMMON EQUITY BRIDGE","",""),
        (2,"Reported components as of September 30, 2026","","Blue = model assumptions; gray = calculated"),
        (3,"Component","USD millions","Treatment"),
        (4,"Cash and cash equivalents","=Reported!B12","Reported"),
        (5,"Marketable securities","=Reported!B13","Includes the reported SpaceX stake"),
        (6,"Less: restricted SpaceX stake","=Reported!B14","Remove before adding back once at scenario carrying amount"),
        (7,"Less: cash reserve","15000","Assumption · operating cash not included in excess assets"),
        (8,"Excess liquid assets","=B4+B5-B6-B7","Used as an add-back"),
        (10,"Restricted SpaceX stake","=Reported!B14","Reported at quarter-end, not a current quote"),
        (11,"SpaceX value retained","0.70","Assumption · 70% of reported value, not a market or tax appraisal"),
        (12,"Non-marketable securities","=Reported!B15","Reported carrying value"),
        (13,"Non-marketable value retained","0.80","Assumption · 80% of reported carrying value"),
        (14,"Investment mark adjustments","=B10*(1-B11)+B12*(1-B13)","Haircuts are illustrative and not a line-by-line tax calculation"),
        (15,"Adjusted non-operating securities","=B10*B11+B12*B13","SpaceX counted once"),
        (16,"Noncurrent debt","=Reported!B16","Carrying value proxy, not full market replacement value"),
        (17,"Current portion of long-term notes","=Reported!B17","Added to noncurrent debt; no commercial paper drawn"),
        (18,"Finance lease liabilities","=Reported!B18","Operating leases treated as operating, not deducted again"),
        (19,"Debt and finance leases","=B16+B17+B18","Deduction from enterprise value"),
        (20,"Preferred claim proxy","=Reported!B19*Reported!B20","Depositary shares × liquidation preference; no conversion modeled"),
        (21,"Noncontrolling interests","=Reported!B21","Carrying value proxy; includes redeemable interests"),
        (22,"Accrued fines and settlements","=Reported!B38","Dedicated deduction; forecast excludes runoff of this accrued liability"),
        (23,"Other claims","=SUM(B20:B22)+B24","Deduct those claims once"),
        (24,"Unsettled investment payables","=Reported!B39","Deduct separately with financial assets counted gross"),
        (25,"Common share count","Millions","Point-in-time issued and outstanding, not weighted-average diluted shares"),
        (26,"Class A (GOOGL)","=Reported!B22","Public voting class"),
        (27,"Class B","=Reported!B23","Super-voting class"),
        (28,"Class C (GOOG)","=Reported!B24","Public non-voting class"),
        (29,"Total common shares","=SUM(B26:B28)","Same per-share economic value assumed; voting/listing premiums not modeled"),
    ]
    return {"title":"ALPHABET INC. (GOOGL / GOOG)  /  FCFF DCF",
            "subtitle":"Illustrative common-equity scenario · input date: 2026-09-30",
            "per_share_label":"Exact value / common share (USD)",
            "explicit_per_share_rounding":True,
            "inputs_subtitle":"Blue = editable scenario input; gray = filed-data formula or explicit bridge",
            "inputs":INPUTS,
            "percentage_cells":{("Reported",25),("Bridge",11),("Bridge",13)},
            "additional_layout":{"Reported":[410,165,600],"Bridge":[350,165,600]},
            "additional_rows":{"Reported":reported,"Bridge":bridge}}

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tayriva_server",type=Path,help="Bundled Linux server launcher")
    ap.add_argument("--output",type=Path,default=ROOT/"workbooks"/FILENAME)
    a=ap.parse_args()
    generate(a.tayriva_server,a.output,profile=profile())
