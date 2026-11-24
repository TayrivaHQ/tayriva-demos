# Tayriva demos

<img src="docs/images/tayriva-mark.png" width="112" height="112" alt="Tayriva logo">

Open a real workbook, pick a result, and follow the inputs that produced it. The valuation and Treasury labs use cited public data; the OIS and reconciliation fixtures use synthetic inputs. None of these files is investment advice or audit assurance.

**648× faster than Receita Federal’s reference calculator.** Tayriva’s development build calculated and saved 10 million synthetic invoices in 34.30 seconds, versus 6 hours, 10 minutes, 28 seconds for the official Java engine. All amounts matched across four tax scenarios. [See the benchmark and method](receita/benchmark/matched-10m.md).

## Open a demo

1. [Download Tayriva](https://github.com/TayrivaHQ/tayriva/releases/tag/v0.14.0) for Windows x64 or Linux x64. Use **Tayriva 0.14.0 or later** for these native `.tay` workbooks.
2. Download a `.tay` file below. Launch Tayriva, then use **File → Open**. Enter the downloaded file's full path if prompted.
3. Select the suggested result and open **Review → Explain & Review**. Use **Save As** if you want to keep a clean original.

| Demo | Start here |
| --- | --- |
| [Brazil: NFS-e and the consumption tax reform](receita/README.md) | **Consulta!B11** traces a synthetic invoice through the packaged snapshot. Rebuild the linked workbook and process 10 million invoice rows across 100 distinct scenarios using the official local Receita Federal calculator. |
| [Alphabet (GOOGL / GOOG): FCFF valuation](workbooks/alphabet-fcff.tay) | **Valuation!B13** traces an illustrative equity value to Alphabet's SEC filings, forecast, cost of capital and share classes. **B22** shows the rounded value. [Walkthrough](docs/WALKTHROUGH.md#alphabet-googl--goog-a-multistage-fcff-valuation). |
| [From Treasury yields to cash flows and PV](derivatives/treasury-snapshot.tay) | Inspect the dated public par yields, modeled forward rates and illustrative trade PV. [Connect a fresh Treasury snapshot through SQLite](derivatives/README.md#real-data-lab-treasury-par-yields-via-sql). |
| [Build and price an OIS swap](derivatives/ois-swap.tay) | **Sheet1!B14** traces synthetic par quotes to discount factors, swap cash flows and pay-fixed PV. [Curve walkthrough](derivatives/README.md). |
| [The total still ties](workbooks/the-total-still-ties.tay) | **Reconciliation!C7** ties at **$100.25**, but **F4–F5** flag that software and rent were swapped. |

All bundled workbooks open offline. The optional Treasury SQL workflow uses a local SQLite database and an explicit download, never an automatic network call from a worksheet.

[Rebuild and verify the demos](docs/WALKTHROUGH.md#rebuild-and-verify-on-linux) · [Set up Tayriva's MCP server](https://github.com/TayrivaHQ/tayriva/blob/main/docs/MCP.md)
