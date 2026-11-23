# Valuation and reconciliation walkthroughs

## Alphabet (GOOGL / GOOG): a multistage FCFF valuation

Open **Valuation!B13** and choose **Review → Explain & Review**. **B13** retains full calculation precision; **B22** explicitly rounds it to **$174.82 per common-equivalent share**. This output is an illustrative result conditional on the workbook inputs, not a target price, live stock quote, or recommendation.

1. **Reported** uses Alphabet's [FY 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm) and [September 2026 Form 10-Q](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000084/goog-20260930.htm) (filed October 29, 2026). FY25 + 9M26 − 9M25 gives **$471.098bn revenue** and **$156.976bn operating income** for the twelve months ended September 30, 2026. Historical cash purchases of PP&E and PP&E depreciation are separately traceable. The forecast starts from a trailing-year base; Year 1 represents the next rolling year, not fiscal 2027.
2. **Forecast** builds six years of net reinvestment and cash flow. Years 1–3 use **14%** sales growth and a **32.5%** operating margin. They fade to **2.8%** growth and **31%** margin by Year 6. Higher near-term capital intensity is represented by **0.55** dollars of extra sales per dollar of net investment; forecast reinvestment represents net capex and noncash working-capital investment together. These are model inputs, not guidance. Historical EBIT, unlike net income, excludes gains from the investment portfolio.
3. **Capital** derives cost of equity as risk-free rate + levered beta × equity risk premium. It adds a borrowing spread to risk-free for cost of debt, then applies the assumed marginal tax rate. Target debt/equity weights are illustrative; no current beta, yield or credit quote is claimed. The workbook uses successive annual WACC factors and ends at **8.78016%** stable WACC.
4. **Forecast!H18:H22** builds the terminal value from Year 7 FCFF and reinvestment equal to stable growth divided by stable ROIC. The model blocks the valuation if stable WACC or stable ROIC does not exceed growth. **Sensitivity** varies only terminal WACC and growth by 0.5 percentage points while holding the explicit forecast and its discount factors fixed.
5. **Bridge** starts with September 30 balances. It separates the **$75.2bn** restricted SpaceX stake from reported marketable securities before adding back a scenario-adjusted value once, and treats non-marketable investments separately. The model assumes a $15bn operating cash reserve; 70% and 80% investment value retention are editable scenario haircuts, not tax calculations or market valuations. It deducts current and noncurrent debt, finance leases, preferred liquidation preference (a proxy, not a conversion model), reported NCI, accrued fines, and unsettled investment payables. Operating leases are treated as operating and are not deducted again. Purchase commitments and future lease commitments are not added as funded debt; the forecast uses blended investment assumptions, not a schedule of those commitments. No distinct value is assigned to uncertain contingencies outside the modeled claims. Future stock issuance, buybacks, and changes after the as-of date are not forecast separately.
6. The common-equivalent denominator uses **5,888m Class A + 828m Class B + 5,578m Class C = 12,294m** common shares outstanding on the balance-sheet date. This assigns equal economic value per common share; it does not model voting or listing premiums. The preferred claim is deducted once and the shares are not also assumed converted. This denominator is not a period-average diluted EPS count.

Record a review on **Valuation!B13**, then raise the equity risk premium in **Inputs!B14** from 5% to 6%. The illustrative output drops from **$174.82** to **$149.40** and the review becomes stale. Or reduce the percentage of reported SpaceX stake retained in **Bridge!B11** from 70% to 60% to see a traceable bridge-specific change.

The model follows Aswath Damodaran’s [Spring 2026 NYU Stern FCFF course material](https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/valpacket1spr26.pdf) and his discussion of [terminal value and stable-period reinvestment](https://pages.stern.nyu.edu/~adamodar/pdfiles/acf3E/ch12.pdf). [Reported input facts](../data/alphabet-reported.csv) are key numeric values with source locations; no original company/lecture documents, vendor quotes, or vendor workbooks are redistributed.

## The total still ties

1. Open **Reconciliation!C7** and observe that mapped expenses and the independent control both total **$100.25**. Read **F4–F5**: neither category agrees.
2. Trace **C4–C5** to their tags and source amounts. Correct **B4** to `Software` and **B5** to `Rent`. The total still ties, but the two exact category checks now pass.
3. Review **C7** with a note on the two individual checks. In the **Ledger** sheet, move $1.00 from Rent to Software by setting **B4** to `41.10` and **B5** to `59.15`.
4. The total is unchanged. The review is stale. **Compare captured inputs** shows the changed provenance, and the two category checks flag the $1.00 variances.

## Rebuild and verify on Linux

Use Python 3.11+ and the launchers from the [Gridloom v0.13.1 Linux server package](https://github.com/GridloomHQ/tayriva/releases/tag/v0.13.1). The source scripts start an isolated process on a loopback port; the verifiers use headless MCP and alter only scratch copies. The generated calculation and layout are reproducible; SQLite revision and file metadata need not be byte-identical across builds.

```sh
app=/absolute/path/to/extracted/gridloom-server
python3 scripts/build_alphabet.py "$app/gridloom" --output /tmp/rebuilt-alphabet.gridloom
python3 scripts/verify_alphabet.py "$app/gridloom-mcp" --workbook /tmp/rebuilt-alphabet.gridloom

python3 scripts/build_reconciliation.py build "$app/gridloom" --workbook /tmp/rebuilt-gl.gridloom
python3 scripts/build_reconciliation.py verify "$app/gridloom-mcp" --workbook /tmp/rebuilt-gl.gridloom
```

The DCF verifier uses independent Decimal arithmetic for all six years and all nine sensitivity values. It checks the base value, equity-risk-premium and perpetual-growth shocks, the WACC-versus-growth guard, and stale review through save and reopen. The reconciliation test confirms that swapping the categories, or later reallocating an equal amount, cannot be caught by the aggregate total alone.

See the [derivatives walkthrough](../derivatives/README.md) for the separate OIS calibration fixture and the Treasury snapshot and local SQL refresh.
