# Receita RTC: calculation in a Tayriva worksheet

This version calculates inside Tayriva. It executes the worksheet's edited formulas on every input row, then commits the results to SQLite. It does not invoke a Java or external calculator when preparing the workbook or running the batch. The pinned Receita engine is a separate reference used to validate the outputs.

## Measured result

On a workstation with an Intel Core i7-8700K, a release candidate run initiated in Chromium from the worksheet processed 10,000,000 synthetic invoices in **29.70 seconds**, or roughly 337,000 invoices/second, including the final SQLite commit. The UI displayed confirmation **30.00 seconds** after clicking the command. The engine reported 4.42 s reading, 15.08 s in the worksheet evaluator and 9.63 s writing and committing. Creating the synthetic input database, building/opening the workbook, and post-run reference verification are outside the batch timing.

All 32 selected cases matched the pinned official REST API to the cent. All five aggregate totals matched the earlier 10-million-invoice Receita-engine benchmark, and the 131,072 rows retained from that benchmark's earlier local attempt matched exactly. This is a bound scenario, not proof that the worksheet replaces or outperforms the general official calculator. It applies a preselected rule to synthetic rows, and the older measurement used different hardware and covered the original service's broader per-operation path.

## Try it

Use a Tayriva build with **Data → Run formula batch**. Use a new SQLite file and allow at least 2 GB of free disk space. Set `--rows 10000` for a quick smoke test; the default is 10 million.

```sh
server=/absolute/path/to/gridloom-server
python3 receita/benchmark/dataset.py prepare rtc-native.sqlite
python3 receita/native/workbook.py build --server "$server" --db rtc-native.sqlite --workbook rtc-native.tay
```

1. Open `rtc-native.tay` in Tayriva. In **Cálculo**, edit **B4** to select an invoice number. Inputs are read directly from SQLite; CBS and IBS are computed by the formulas in row 6 even if the results table is empty.
2. In **B9**, use **Review → Explain & Review**. Follow the result through the effective rates, 60% rate reduction, base and parameterized SQL inputs. To try a one-invoice scenario, temporarily replace an input in row 6 with a numeric value and undo it afterward. This does not change SQLite. To change a persisted input inside Tayriva, edit an input in **Notas** and commit the staged edit. The single-invoice view recalculates from the database. The batch always uses the source table rather than the what-if preview values.
3. Choose **Data → Run formula batch**. Confirm that `bench_results` will be replaced. The app applies each formula independently and commits atomically; an error leaves the prior results intact. The status bar reports total, read, calculation and write/commit times. **Lote** shows the committed count and the selected invoice’s persisted amounts. There is no GPU and no memoization across invoices.

To run the same Tayriva API action headlessly and print a machine-readable timing report:

```sh
python3 receita/native/workbook.py run --server "$server" --db rtc-native.sqlite --workbook rtc-native.tay
python3 receita/native/workbook.py review --server "$server" --db rtc-native.sqlite --workbook rtc-native.tay
# Once the pinned Receita REST API is running locally, verify persisted rows and sample parity:
python3 receita/benchmark/dataset.py verify rtc-native.sqlite --worksheet
```

This workbook models only the synthetic educational NFS-e case documented in the parent demo. It uses the exact-decimal `ROUND` behavior (half-even), two decimal places for fiscal monetary values, four decimal places for effective rates, and independently rounded state and municipal amounts. It is not a general-purpose tax engine and must not be used for filing, issuing fiscal documents, or making tax decisions. The prior demo includes a demonstrative PDF and the official calculation response; PDF generation is not timed or performed by the worksheet batch.
