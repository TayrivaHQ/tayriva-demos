#!/usr/bin/env python3
"""Build and verify the synthetic OIS-style Gridloom example using Gridloom MCP."""
import argparse
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import shutil
import os
import re
from urllib.request import Request, urlopen
import subprocess
import tempfile

NAME = "ois-swap.gridloom"
QUOTES = tuple(map(D, ("0.0500", "0.0470", "0.0445", "0.0430", "0.0420")))
BUMP, FIXED, NOTIONAL = D("0.0001"), D("0.0460"), D("10000000")
EPS = D("0.000000002")


class MCP:
    def __init__(self, exe, directory):
        self.exe, self.dir, self.seq = exe, directory, 0

    def __enter__(self):
        self.p = subprocess.Popen([self.exe, "--workbook-root", str(self.dir)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                  encoding="utf-8")
        self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                "clientInfo": {"name": "ois-example-builder", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *args):
        self.p.stdin.close()
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait(timeout=5)
        self.p.stdout.close()

    def send(self, message):
        self.p.stdin.write(json.dumps(message) + "\n")
        self.p.stdin.flush()

    def rpc(self, method, params):
        self.seq += 1
        self.send({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params})
        result = json.loads(self.p.stdout.readline())
        assert result["id"] == self.seq and "error" not in result, result
        return result["result"]

    def call(self, name, **args):
        result = self.rpc("tools/call", {"name": name, "arguments": args})
        assert not result.get("isError"), (name, result)
        return result["structuredContent"]

    def cells(self, sheet, area):
        return {x["cell"]: x["value"].get("value")
                for x in self.call("read_cells", sheet=sheet, range=area)["cells"]}


def edit(address, value):
    if isinstance(value, D):
        return {"cell": address, "input": {"type": "decimal", "value": str(value)}}
    if isinstance(value, int):
        return {"cell": address, "input": {"type": "integer", "value": str(value)}}
    return {"cell": address, "input": {"type": "formula" if value.startswith("=") else "text",
                                      "value": value}}


def table_row(cells, row, *values):
    cells.update({f"{chr(65+i)}{row}": val for i, val in enumerate(values) if val is not None})


def model():
    desk = {"A1": "USD OIS-style swap | pricing desk", "A2": "Synthetic quotes. Values are USD unless noted. Rates are decimals.",
            "A4": "Trade inputs", "A5": "Notional (USD)", "B5": NOTIONAL,
            "A6": "Contract fixed rate", "B6": FIXED, "A7": "Pay fixed +1 / receive fixed -1", "B7": 1,
            "A8": "Fixed and floating pay annually on a 1.0 accrual grid. This trade ends at year 3.",
            "A10": "Trade valuation", "A11": "Fair fixed rate", "B11": "=(1-C25)/SUM(D23:D25)",
            "A12": "Fixed leg PV", "B12": "=SUM(H23:H25)", "A13": "Floating leg PV", "B13": "=SUM(I23:I25)",
            "A14": "Signed trade PV", "B14": "=B7*(B13-B12)", "A15": "Signed PV after quotes +1 bp", "B15": "=Risk!B11",
            "A16": "Signed PV after quotes -1 bp", "B16": "=Risk!B12",
            "A17": "Signed quote DV01 (USD per bp)", "B17": "=(B15-B16)*0.0001/(2*Curve!B3)",
            "A18": "PV of 1 bp fixed-coupon change (absolute USD)", "B18": "=B5*SUM(D23:D25)*0.0001",
            "A19": "Floating-leg identity residual (USD)", "B19": "=B13-B5*(1-C25)",
            "A20": "Pricing controls", "B20": '=IF(ABS(B19)<0.000001,IF(ABS(B14-SUM(J23:J25))<0.000001,IF(ABS(B7)=1,IF(B5>0,"PASS","CHECK NOTIONAL"),"CHECK SIDE"),"CHECK PV"),"CHECK FLOAT")',
            "A27": "Open Curve to edit the quotes. Open Explain & Review on B14 or B17 to follow the drivers."}
    table_row(desk, 22, "Year", "Accrual", "Discount", "Fixed annuity", "Float forward", "Fixed cash flow",
              "Float cash flow", "Fixed PV", "Float PV", "Signed net PV")
    for r in range(23, 26):
        c = r - 16
        table_row(desk, r, f"=Curve!A{c}", f"=Curve!C{c}", f"=Curve!E{c}", f"=B{r}*C{r}",
                  f"=Curve!H{c}", f"=$B$5*$B$6*B{r}", f"=$B$5*E{r}*B{r}", f"=C{r}*F{r}", f"=C{r}*G{r}",
                  f"=$B$7*(I{r}-H{r})")
    curve = {"A1": "USD OIS-style curve | par bootstrapping",
             "A2": "Edit the synthetic annual par quotes in B7:B11. Each node solves one swap.",
             "A3": "Parallel quote shock (0.0001 = 1 bp)", "B3": BUMP,
             "A4": "On-node pricing only. No holiday calendars, historical fixings, payment lags, stubs, or curve interpolation.",
             "A13": "Curve controls", "B13": '=IF(B3>0,IF(COUNTIF(I7:I11,"PASS")=5,"PASS","CHECK NODES"),"CHECK BUMP")',
             "A14": "Residuals are in bp. Positive discount and declining factors are checks for this positive-rate fixture."}
    table_row(curve, 6, "Year", "Quote", "Accrual", "Prior annuity", "Discount", "Repriced par", "Residual bp",
              "Period forward", "Control")
    for r, strike in enumerate(QUOTES, 7):
        prior = "0" if r == 7 else f"D{r-1}+C{r-1}*E{r-1}"
        discount_prev = "1" if r == 7 else f"E{r-1}"
        table_row(curve, r, r - 6, strike, D(1), f"={prior}", f"=(1-B{r}*D{r})/(1+B{r}*C{r})",
                  f"=(1-E{r})/(D{r}+C{r}*E{r})", f"=(F{r}-B{r})*10000", f"=({discount_prev}/E{r}-1)/C{r}",
                  f'=IF(E{r}>0,IF(E{r}<{discount_prev},IF(ABS(G{r})<0.000001,"PASS","CHECK REPRICE"),"CHECK ORDER"),"CHECK DISCOUNT")')
    risk = {"A1": "Parallel quote risk | rebootstrap, not zero-curve shock",
            "A2": "Rebuild every node independently after shifting all par swap quotes in either direction.",
            "A10": "3Y Revaluation", "A11": "Signed price after + quote shock",
            "B11": "=Sheet1!B7*Sheet1!B5*(1-D7-Sheet1!B6*(C7+Curve!C9*D7))",
            "A12": "Signed price after - quote shock",
            "B12": "=Sheet1!B7*Sheet1!B5*(1-G7-Sheet1!B6*(F7+Curve!C9*G7))",
            "A14": "Central difference in Sheet1 is normalized to USD per 1 bp even if you change the shock size."}
    table_row(risk, 4, "Year", "+ quote", "+ prior annuity", "+ discount", "- quote", "- prior annuity", "- discount",
              "+ residual bp", "- residual bp")
    for r in range(5, 10):
        c = r + 2
        cp = "0" if r == 5 else f"C{r-1}+Curve!C{c-1}*D{r-1}"
        fp = "0" if r == 5 else f"F{r-1}+Curve!C{c-1}*G{r-1}"
        table_row(risk, r, f"=Curve!A{c}", f"=Curve!B{c}+Curve!$B$3", f"={cp}",
                  f"=(1-B{r}*C{r})/(1+B{r}*Curve!C{c})", f"=Curve!B{c}-Curve!$B$3",
                  f"={fp}", f"=(1-E{r}*F{r})/(1+E{r}*Curve!C{c})",
                  f"=((1-D{r})/(C{r}+D{r}*Curve!C{c})-B{r})*10000",
                  f"=((1-G{r})/(F{r}+G{r}*Curve!C{c})-E{r})*10000")
    return {"Sheet1": desk, "Curve": curve, "Risk": risk}


def oracle(quotes, shock=BUMP, face=NOTIONAL, fixed=FIXED, side=1):
    """Independent backward substitution on the par-instrument linear system."""
    def solve(qs):
        discount = []
        for k, q in enumerate(qs):
            row = [q] * k + [1 + q]
            discount.append((1 - sum(map(lambda v: v[0] * v[1], zip(row, discount)))) / row[-1])
        return discount

    def price(ds):
        accrual_cash = [face * (lead / tail - 1) for lead, tail in zip([D(1)] + ds, ds)]
        floatleg = sum(c * d for c, d in zip(accrual_cash[:3], ds))
        fixedleg = sum(face * fixed * d for d in ds[:3])
        return side * (floatleg - fixedleg), fixedleg, floatleg

    with localcontext() as ctx:
        ctx.prec = 48
        ds = solve(quotes)
        pv, fp, fl = price(ds)
        up = price(solve([q + shock for q in quotes]))[0]
        dn = price(solve([q - shock for q in quotes]))[0]
        return ds, {"B11": (1-ds[2])/sum(ds[:3]), "B12": fp, "B13": fl, "B14": pv, "B15": up,
                    "B16": dn, "B17": (up-dn)*BUMP/(2*shock), "B18": face * sum(ds[:3]) * BUMP,
                    "B19": D(0)}


def close(actual, expected, label):
    assert actual is not None, label
    assert abs(D(actual) - expected) < EPS, (label, actual, expected)


def verify(mcp, quotes=QUOTES, shock=BUMP, side=1):
    discount, values = oracle(quotes, shock=shock, side=side)
    desk = mcp.cells("Sheet1", "B11:B20")
    for key, value in values.items():
        close(desk[key], value, key)
    assert desk["B20"] == "PASS", desk
    for i, expected in enumerate(discount, 7):
        curve = mcp.cells("Curve", f"E{i}:I{i}")
        close(curve[f"E{i}"], expected, f"discount({i-6})")
        close(curve[f"G{i}"], D(0), f"base residual({i-6})")
        assert curve[f"I{i}"] == "PASS", curve
    for i in range(5, 10):
        row = mcp.cells("Risk", f"H{i}:I{i}")
        for key in (f"H{i}", f"I{i}"):
            close(row[key], D(0), key)
    for sheet, area in (("Sheet1", "A10:J25"), ("Curve", "A6:I13"), ("Risk", "A4:I14")):
        res = mcp.call("validate_cells", sheet=sheet, range=area)
        assert res["valid"], res
    return desk


def format_book(executable, path):
    """Use the optional packaged Gridloom server for native view formatting."""
    env = {**os.environ, "GRIDLOOM_RECOVERY_DIR": str(path.parent / "recovery"), "RUST_LOG": "error"}
    with subprocess.Popen([executable, "--port", "0"], stdout=subprocess.PIPE, text=True, env=env) as server:
        try:
            line = server.stdout.readline()
            match = re.search(r"http://127[.]0[.]0[.]1:[0-9]+", line)
            assert match, line
            origin = match[0]

            def post(route, **params):
                request = Request(origin + "/api/" + route, data=json.dumps(params).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=5) as response:
                    return json.load(response)

            def paint(sheet, start, end, fill=None, fmt=None, bold=False):
                sr, sc = start
                er, ec = end
                post("ranges/format", sheet_name=sheet,
                     range={"start_row": sr-1, "start_col": sc-1, "end_row": er-1, "end_col": ec-1},
                     style={"bold": bold, "italic": False, "fill": fill, "number_format": fmt})

            post("workbook/open", path=str(path))
            for sheet, widths, header, columns in (
                ("Sheet1", [380, 130, 100, 125, 120, 136, 136, 125, 125, 125], 22, 10),
                ("Curve", [265, 130, 100, 176, 174, 130, 130, 130, 150], 6, 9),
                ("Risk", [275, 130, 155, 174, 130, 155, 174, 135, 135], 4, 9),
            ):
                for i, width in enumerate(widths):
                    post("sheets/column-width", sheet_name=sheet, column=i, width=width)
                paint(sheet, (1, 1), (1, columns), "#D7ECD9", bold=True)
                paint(sheet, (header, 1), (header, columns), "#DEE8F5", bold=True)
            for row in (4, 10):
                paint("Sheet1", (row, 1), (row, 2), "#DEE8F5", bold=True)
            paint("Sheet1", (5, 2), (5, 2), "#FFF2CC", "currency")
            paint("Sheet1", (6, 2), (6, 2), "#FFF2CC", "percent")
            paint("Sheet1", (7, 2), (7, 2), "#FFF2CC")
            paint("Sheet1", (11, 2), (11, 2), fmt="percent")
            paint("Sheet1", (12, 2), (19, 2), fmt="currency")
            for row in (14, 17):
                paint("Sheet1", (row, 1), (row, 1), "#D7ECD9", bold=True)
                paint("Sheet1", (row, 2), (row, 2), "#D7ECD9", "currency", bold=True)
            paint("Sheet1", (23, 5), (25, 5), fmt="percent")
            paint("Sheet1", (23, 6), (25, 10), fmt="currency")
            paint("Curve", (3, 2), (3, 2), "#FFF2CC")
            paint("Curve", (7, 2), (11, 2), "#FFF2CC", "percent")
            for col in (6, 8):
                paint("Curve", (7, col), (11, col), fmt="percent")
            paint("Curve", (7, 7), (11, 7), fmt="number")
            for col in (2, 5):
                paint("Risk", (5, col), (9, col), fmt="percent")
            paint("Risk", (5, 8), (9, 9), fmt="number")
            paint("Risk", (11, 2), (12, 2), fmt="currency")
            post("sheets/select", name="Sheet1")
            post("workbook/save", path=str(path))
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def build(executable, output, server=None):
    with tempfile.TemporaryDirectory(prefix="gridloom-ois-") as staging:
        staging = Path(staging)
        with MCP(executable, staging) as mcp:
            rev = mcp.call("create_workbook", file=NAME)["revision"]
            for sheet in ("Curve", "Risk"):
                rev = mcp.call("add_sheet", sheet=sheet, revision=rev)["revision"]
            sheets = model()
            for sheet in ("Curve", "Risk", "Sheet1"):
                rev = mcp.call("edit_cells", sheet=sheet, revision=rev,
                               edits=[edit(key, val) for key, val in sheets[sheet].items()])["revision"]
            desk = verify(mcp)
            traced = mcp.call("explain_cell", sheet="Sheet1", cell="B14")
            assert {x["range"] for x in traced["upstream"]} == {"B7", "B12", "B13"}, traced
            inspection = mcp.call("review_cell", sheet="Sheet1", cell="B14", limit=24)
            assert inspection["can_mark_reviewed"], inspection
            trace = list(inspection["trace"])
            offset = inspection["trace_page"]["next_offset"]
            while offset is not None:
                page = mcp.call("review_cell", sheet="Sheet1", cell="B14", limit=24, offset=offset)
                trace.extend(page["trace"])
                offset = page["trace_page"]["next_offset"]
            assert {("Curve", f"B{r}") for r in (7, 8, 9)} <= {(x["sheet"], x["cell"]) for x in trace}
            record = mcp.call("record_review", revision=rev, sheet="Sheet1", cell="B14",
                     decision="reviewed", expected_snapshot=inspection["snapshot"], agent_label="OIS example validation",
                     note="Compared base PV, fair rate, discount nodes, calibration residuals, and parallel quote DV01 to an independent Python Decimal calculation. Synthetic inputs only.",
                     evidence=[{"label": "Reproducible independent check", "reference": "derivatives/build.py"}])
            rev = mcp.call("workbook_info")["revision"]
            mcp.call("save_workbook", revision=rev)
        if server:
            format_book(server, staging / NAME)
        with MCP(executable, staging) as mcp:
            rev = mcp.call("open_workbook", file=NAME)["revision"]
            assert verify(mcp)["B14"] == desk["B14"]
            inspect = mcp.call("review_cell", sheet="Sheet1", cell="B14")
            assert inspect["status"] == "review_current", inspect["status"]
            assert inspect["snapshot"] == inspection["snapshot"]
            scenario = QUOTES[:2] + (QUOTES[2] + D("0.0025"),) + QUOTES[3:]
            rev = mcp.call("edit_cells", sheet="Curve", revision=rev, edits=[edit("B9", scenario[2])])["revision"]
            restated = verify(mcp, scenario)
            assert D(restated["B14"]) > D(desk["B14"])
            after = mcp.call("review_cell", sheet="Sheet1", cell="B14")
            assert after["status"] == "review_stale", after["status"]
            differences = mcp.call("compare_review", review_id=record["record"]["review_id"], limit=24)
            assert any(x["category"] == "input" and x["sheet"] == "Curve" and x["cell"] == "B9"
                       for x in differences["changes"]), differences
            print("Archived review staled after 3Y quote change; PV:", restated["B14"])
            rev = mcp.call("edit_cells", sheet="Curve", revision=rev, edits=[edit("B3", D("0.0002"))])["revision"]
            rev = mcp.call("edit_cells", sheet="Sheet1", revision=rev, edits=[edit("B7", -1)])["revision"]
            flipped = verify(mcp, scenario, shock=D("0.0002"), side=-1)
            assert D(flipped["B14"]) == -D(restated["B14"])
        # Scenario changes were deliberately left unsaved.
        if output.exists():
            raise FileExistsError(f"Refusing to replace {output}; choose a new output file")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as dest, (staging / NAME).open("rb") as src:
            shutil.copyfileobj(src, dest)
        print("Created", output, "Base valuation:", desk)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp", required=True, type=lambda p: str(Path(p).resolve()))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name(NAME))
    parser.add_argument("--server", type=lambda p: str(Path(p).resolve()),
                        help="Optional Gridloom server launcher to apply native display formatting")
    p = parser.parse_args()
    build(p.mcp, p.output, p.server)
