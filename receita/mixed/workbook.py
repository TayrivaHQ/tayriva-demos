#!/usr/bin/env python3
"""Build a mixed-rule Tayriva worksheet; Excel-like formulas do all calculations."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mixed.dataset import RULES
from native.workbook import INPUTS, TITLES, main

RULE_TABLE=[["Chave da classificação", "Redução (%)", "Tratamento sintético", "NBS", "CST", "cClassTrib"]]
for nbs,cst,code,red,description in RULES:
    RULE_TABLE.append([str((nbs*1_000+cst)*1_000_000+code),str(red),description,
                       str(nbs),str(cst).zfill(3),str(code).zfill(6)])

profile=dict(
    inputs=INPUTS+("nbs","cst","class"),
    titles=TITLES[:6]+("NBS","CST (numérico)","cClassTrib (numérico)","Chave da regra")+
           ("Redução (%)",)+TITLES[7:],
    rules=RULE_TABLE,
    calc=(
       ("calc:rule_key","=(G6*1000+H6)*1000000+I6"),
       ("calc:reduction_pct","=VLOOKUP(J6,Regras!$A$2:$B$5,2,FALSE)"),
       ("out:base","=A6-B6-C6"),
       ("calc:cbs_effective_pp","=IF(K6=100,0,ROUND(D6*(100-K6)/10000,4))"),
       ("calc:state_effective_pp","=IF(K6=100,0,ROUND(E6*(100-K6)/10000,4))"),
       ("calc:city_effective_pp","=IF(K6=100,0,ROUND(F6*(100-K6)/10000,4))"),
       ("out:cbs","=ROUND(L6*M6/100,0)"),
       ("out:state","=ROUND(L6*N6/100,0)"),
       ("out:city","=ROUND(L6*O6/100,0)"),
       ("out:ibs","=Q6+R6"),
    ),
    labels={
        8:["Simulação NFS-e • quatro tratamentos • 2027 • valores e enquadramentos sintéticos"],
        9:["Total CBS + IBS (R$)","=(P6+S6)/100"],
        10:["CBS (R$)","=P6/100"], 11:["IBS total (R$)","=S6/100"], 12:["Base (R$)","=L6/100"],
        13:["Tratamento selecionado","=VLOOKUP(J6,Regras!$A$2:$C$5,3,FALSE)"],
        18:["A aba Regras mapeia NBS + CST + cClassTrib para a redução; classes sem correspondência não calculam."],
    }
)
if __name__=="__main__":
    main(profile=profile,extra_evidence=("VLOOKUP","Regras","IF"))
