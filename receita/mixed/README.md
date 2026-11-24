# One workbook, four tax treatments, ten million invoices

This is a synthetic NFS-e benchmark, not software for tax filing. Open **Cálculo** and change **B4** to pick an invoice. **B13** shows the treatment and **B9 → Review → Explain & Review** traces the result through the class key, the rule table, the input values, effective rates, and rounding. **Data → Run formula batch** calculates and commits all rows. **Lote** shows stored results.

| Synthetic 2027 case | NBS | CST / cClassTrib | Reduction on CBS/state IBS/municipal IBS |
|---|---:|---|---:|
| Regular service | 114011100 | 000 / 000001 | 0% |
| Eligible intellectual profession | 114011100 | 200 / 200052 | 30% |
| Eligible education service | 122011200 | 200 / 200028 | 60% |
| Eligible research institution | 114011100 | 200 / 200016 | 100% |

The cases model qualifying operations with illustrative nominal rates, not a legal determination of eligibility or future tax rates. The codes and rates of reduction were checked with Receita RTC 1.7.2 / V0073. The worksheet joins the three invoice fields into an exact integer key and uses exact `VLOOKUP` against **Regras**; an unknown key aborts rather than defaulting to zero. Each of the three effective rate formulas uses `IF` for the zero treatment and otherwise applies the selected reduction and four-place rate rounding. Each fiscal amount is rounded to the nearest cent, ties to even. Municipal and state IBS are rounded separately before summing.

## Reproduce the matched comparison

Requirements: [Tayriva 0.15.0 or later](https://github.com/TayrivaHQ/tayriva/releases), with batch lookup and IF support, Python 3, JDK 25, pinned [Receita RTC checkout](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular/tree/f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4) at commit `f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4` with Maven dependencies cached and the [offline database migrated to V0073](../benchmark/README.md), Linux `taskset`, and about 4 GB free disk space. Pick an available logical CPU. Use a new directory for every measured pair.

```sh
export RTC_RESULTS="$PWD/matched-10m"
export RTC_TAYRIVA_SERVER=/absolute/path/to/tayriva
export RTC_OFFICIAL_CHECKOUT=/absolute/path/to/receita
export RTC_CPU=2
export JAVA_HOME=/absolute/path/to/jdk-25
mkdir -p "$RTC_RESULTS"
python3 receita/mixed/dataset.py prepare "$RTC_RESULTS/mixed-native-10m.sqlite"
cp --reflink=auto "$RTC_RESULTS/mixed-native-10m.sqlite" "$RTC_RESULTS/mixed-official-10m.sqlite"
bash receita/mixed/run-pair.sh
```

For a small acceptance run, set `RTC_ROWS=1200` **and** pass `--rows 1200` when creating the database.

### What is held constant

- Same machine, single identical logical CPU pin and one calculation worker each; runs never overlap. Neither uses GPU, HTTP per row, or reuse of an already calculated invoice.
- Identical SQLite files before calculation, deterministic IDs, gross values, discount and ISS, operation date and jurisdiction, classification and illustrative nominal rates. The default run has exactly 2.5 million of each treatment, distributed over four municipalities.
- Same five integer result fields, persisted to the same table schema. Each run replaces the result snapshot in an atomic transaction, with SQLite rollback journal and `synchronous=FULL`. Each timer includes lookup/read, independent calculation, row writes and final commit. The Java adapter also maintains one final progress checkpoint row in the same transaction.
- Exclude data generation, copy, app startup, workbook preparation, follow-up inspection, and post-run parity checks from timed phases. Record each phase, source version, CPU and output logs.
- Compare all 10 million inputs and all 10 million result rows by ID, checking all five amounts, foreign keys and SQLite integrity. Confirm the comparison completed before dividing the two measured times.

### What is not identical

Tayriva computes four preselected cases with visible worksheet rules, operating on its exact integer/decimal inputs. The official implementation redoes the full base calculation, the complete service checks/classification and observability generation for each invoice. Both produce the same monetary outputs within the tested scope, but the benchmark is **a comparison of two ways to solve this defined batch task**, not a claim that Tayriva implements all of Receita's policy, API, legal eligibility checks, or fiscal documentation. Linux affinity bounds resource use but does not reserve the physical core from unrelated system jobs. Run repeat pairs on an idle machine and alternate order before quoting a general speed claim. The prior fixed-class demo and GitHub Actions Java timing are not comparable runs.
