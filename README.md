# Gridloom demos

Open a real workbook, pick a result, and follow the inputs that produced it. The valuation and Treasury labs use cited public data; the OIS and reconciliation fixtures use synthetic inputs. None of these files is investment advice or audit assurance.

## Open a demo

1. [Download Gridloom](https://github.com/lhemerly/gridloom/releases/latest) for Windows x64 or Linux x64. The examples were built on **0.13.1**.
2. Download a `.gridloom` file below. Launch Gridloom, then use **File → Open**. Enter the downloaded file's full path if prompted.
3. Select the suggested result and open **Review → Explain & Review**. Use **Save As** if you want to keep a clean original.

| Demo | Start here |
| --- | --- |
| [Alphabet (GOOGL / GOOG): FCFF valuation](workbooks/alphabet-fcff.gridloom) | **Valuation!B13** traces an illustrative equity value to Alphabet's SEC filings, forecast, cost of capital and share classes. **B22** shows the rounded value. [Walkthrough](docs/WALKTHROUGH.md#alphabet-googl--goog-a-multistage-fcff-valuation). |
| [From Treasury yields to cash flows and PV](derivatives/treasury-snapshot.gridloom) | Inspect the dated public par yields, modeled forward rates and illustrative trade PV. [Connect a fresh Treasury snapshot through SQLite](derivatives/README.md#real-data-lab-treasury-par-yields-via-sql). |
| [Build and price an OIS swap](derivatives/ois-swap.gridloom) | **Sheet1!B14** traces synthetic par quotes to discount factors, swap cash flows and pay-fixed PV. [Curve walkthrough](derivatives/README.md). |
| [The total still ties](workbooks/the-total-still-ties.gridloom) | **Reconciliation!C7** ties at **$100.25**, but **F4–F5** flag that software and rent were swapped. |

All bundled workbooks open offline. The optional Treasury SQL workflow uses a local SQLite database and an explicit download, never an automatic network call from a worksheet.

[Rebuild and verify the demos](docs/WALKTHROUGH.md#rebuild-and-verify-on-linux) · [Set up Gridloom's MCP server](https://github.com/lhemerly/gridloom/blob/main/docs/MCP.md)
