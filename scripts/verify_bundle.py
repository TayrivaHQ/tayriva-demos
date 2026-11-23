#!/usr/bin/env python3
"""Check the shipped demo bytes, then open and recalculate using the package."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path

from build_dcf import ROOT, local_app
from verify_dcf import mcp

# Native v2 workbook header, demo footprint, and primary teaching result.
DEMOS = {
    "workbooks/alphabet-fcff.tay": (7, 625, "Valuation", "B22", "174.82", 0),
    "workbooks/the-total-still-ties.tay": (2, 52, "Reconciliation", "C7", "100.25", 0),
    "derivatives/ois-swap.tay": (3, 223, "Sheet1", "B14", "-41140.33", 1),
    "derivatives/treasury-snapshot.tay": (3, 205, "Sheet1", "B10", "13861.22", 0),
}


def verify(server, client):
    sums = dict(line.split("  ")[::-1] for line in (ROOT / "SHA256SUMS").read_text().splitlines())
    assert set(sums) == set(DEMOS), "The manifest must cover all four demos exactly"
    with tempfile.TemporaryDirectory(prefix="tayriva-verify-bundle-") as tmp:
        scratch = Path(tmp)
        for relative, (sheets, cells, sheet, addr, expected, reviews) in DEMOS.items():
            original = ROOT / relative
            assert hashlib.sha256(original.read_bytes()).hexdigest() == sums[relative], relative
            copy = Path(shutil.copy(original, scratch))
            with sqlite3.connect(f"{copy.as_uri()}?mode=ro", uri=True) as db:
                assert db.execute("pragma application_id").fetchone() == (0x54415957,)
                assert db.execute("pragma user_version").fetchone() == (2,)
                assert db.execute("pragma integrity_check").fetchall() == [("ok",)]
                assert db.execute("select count(*) from worksheet").fetchone() == (sheets,)
                assert db.execute("select count(*) from worksheet_cell").fetchone() == (cells,)
                metadata = json.loads(db.execute("select json from workbook").fetchone()[0])
                assert len(metadata["reviews"]) == reviews and not metadata["connection_configs"]
            with local_app(server) as post:
                post("workbook/open", path=str(copy))
                value = post("cells/explain", sheet_name=sheet, row=int(addr[1:])-1, col=ord(addr[0])-65)["value"]["value"]
                assert Decimal(value).quantize(Decimal(".01")) == Decimal(expected), (relative, value)
            with mcp(client, scratch) as call:
                call("open_workbook", file=copy.name)
                value = call("read_cells", sheet=sheet, range=addr)["cells"][0]["value"]["value"]
                assert Decimal(value).quantize(Decimal(".01")) == Decimal(expected)
                if reviews:
                    review = call("review_cell", sheet=sheet, cell=addr)
                    assert review["status"] == "review_current", review["status"]
            print(f"PASS {relative}: {sheet}!{addr} = {expected}; archived reviews: {reviews}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Extracted Linux server package directory")
    args = parser.parse_args()
    verify(args.package / "tayriva", args.package / "tayriva-mcp")
