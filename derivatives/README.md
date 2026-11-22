# From swap quotes to price and risk

Open [ois-swap.gridloom](ois-swap.gridloom) in [Gridloom 0.13.1 or later](https://github.com/lhemerly/gridloom/releases). This self-contained example bootstraps a five-node USD overnight-index-swap-style discount curve and values a three-year fixed-versus-floating swap. All quotes are synthetic. No data connections are required.

Dollar amounts in this guide are rounded to the nearest cent. Gridloom 0.13.1 can truncate the grid display for some number formats; use **Explain & Review** for the full calculated value.

## Try it

1. On **Sheet1**, the demo pays **4.60% fixed** and receives floating on **USD 10 million**. The fair fixed rate is **4.45%** and the payer PV is **−USD 41,140.33**. Open **Explain & Review** on **B14**: its saved review traces the two legs to the assumptions, cash flows, and underlying curve quotes.
2. On **Curve**, change **B9** (the 3-year quote) from 4.45% to **4.70%**. The signed PV becomes **+USD 27,361.40**, and the saved AI-assisted review becomes stale. This is a single-node change, not the parallel risk scenario. Edit a copy if you want to keep the original review.
3. On **Risk**, compare the base curve with the two independently rebuilt curves after shifting every input quote by ±1 bp. Base signed quote DV01 is **+USD 2,750.43 per bp**: a rise in input quotes increases the value of this payer trade. On **Sheet1**, set **B7** to `-1` to switch the trade to receive fixed; signed price and quote DV01 reverse. The distinct fixed-coupon 1 bp PV magnitude is **USD 2,742.69**.

Yellow cells are scenario inputs. The **PASS** cells test pricing identities, node ordering for this positive-rate example, and calibration, not whether the quotes are sensible market inputs. The recorded review is an educational self-check, not independent approval.

## How the curve is built

Use one discount-and-projection curve with year 0 discount factor 1 and annual payments at years 1 through 5. With par quote `K[n]`, fixed accrual fractions `a[i]`, and discounts `P[i]`, the par condition is:

```text
K[n] × sum(i=1..n, a[i] × P[i]) = 1 − P[n]
P[n] = (1 − K[n] × sum(i=1..n-1, a[i] × P[i])) / (1 + K[n] × a[n])
```

Every node is solved directly and repriced back to its input. The worksheet uses `a[i] = 1`, and the projected floating coupon for period `i` is `(P[i-1] / P[i] − 1) / a[i]`. Discounting each period’s coupon makes the floating PV telescope to `notional × (1 − P[n])`. The valuation shows both leg cash flows and proves that identity independently. Quote DV01 is the central PV difference, normalized to a 1 bp change in the underlying swap quotes.

This is a regular, spot-starting, on-node educational model, not market-ready pricing. No calendars, day-count date generation, stubs, historical fixings, payment or observation lags, interpolation, multi-curve basis, credit/collateral adjustments, or transaction costs. Real SOFR compounds business-day observations using actual calendar-day weights and a 360-day denominator. No live rate or trading recommendation is supplied.

- [Bank of England: OIS and zero-coupon curve terminology](https://www.bankofengland.co.uk/statistics/yield-curves/terminology-and-concepts)
- [New York Fed: SOFR compounding and Index conventions](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates)

## Rebuild and verify

With Python 3 and the packaged Gridloom executables:

```sh
python3 derivatives/build.py --mcp /path/to/gridloom-mcp \
  --server /path/to/gridloom --output /tmp/ois-swap-check.gridloom
```

`--server` is optional and applies native presentation styling with the Linux server package; remove it to verify/regenerate the same formulas and review through MCP alone. Both routes validate against independent Decimal arithmetic, reopen the saved native workbook, trace the downstream PV to its quote inputs, test a 25 bp quote change, detect stale review, and check side and bump-size changes. Verification scenarios are not saved in the demo. The builder refuses to overwrite an existing output; review identifiers and timestamps may differ between builds.

## Real-data lab: Treasury par yields via SQL

Open [treasury-snapshot.gridloom](treasury-snapshot.gridloom) for an offline example calibrated to the U.S. Treasury's published **November 20, 2026** observation. The five published nodes (6M, 1Y, 2Y, 3Y, 5Y) are separated from the interpolated semiannual nodes. The workbook bootstraps discounts and period forwards in cells, then uses them in a separate illustrative three-year swap. For this observation, the simplified model gives a **4.65%** fair fixed rate and a **+$13,861.22** pay-fixed PV at 4.60%. The [Treasury daily table](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month=202611) is the snapshot source. See [Treasury's convention FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions) and [official curve methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology).

These are **Treasury par yields**, not traded SOFR/OIS, futures forwards, or Treasury's official forward curve. The derived forwards are predictions of neither future rates nor swap prices. Treasury uses a monotone-convex curve; this workbook deliberately interpolates missing par yields linearly and bootstraps the semiannual grid for teachability. The offline workbook stores quote provenance and SQL selection but has no runtime data connection.

Generate the genuinely SQL-linked version with the unpacked Linux Gridloom server package:

```sh
python3 derivatives/treasury.py --as-of 2026-11-20 --directory ./treasury-live \
  --mcp /path/to/gridloom-mcp --server /path/to/gridloom
```

The script requests Treasury's official monthly **Download CSV** endpoint, selects the latest complete observation on or before the explicit date in that month, and loads it into local SQLite as integer basis points. Open the generated `treasury-linked.gridloom` in Gridloom, not in MCP. `Quotes!B8:B12` queries the SQLite table with Gridloom's native parameterized `SQLVALUE`; follow any quote cell in **Explain & Review**. Rates flow through the modeled semiannual discounts and period forwards to trade PV. Use a new directory for a new observation. This is an explicit refresh, not an automatic network call from a worksheet. Do not relocate the linked workbook/SQLite without recreating the connection: the local output records its absolute database path.

If the network is unavailable, replace `--as-of 2026-11-20` with `--offline` to build using the included one-observation Treasury extract, or open the bundled snapshot without rebuilding anything. Verification uses an independent Decimal solver and the exact packaged Gridloom engine. The SQL-linked check reopens the workbook and validates that a temporary +25 bp change in the **local demo database** flows through SQL to a **+$83,024.11** model PV, then restores the original quote. It does not represent a published market observation. MCP intentionally rejects linked external workbooks; the snapshot remains fully usable in MCP.

**Validation status:** The bundled Treasury observation was checked against the official daily table. The offline-to-SQL import, workbook reopen, local SQL refresh, and repricing were tested end to end. The direct live CSV fetch could not be tested from the verification environment; use the bundled offline input if the endpoint is unavailable.
