# 10 million invoices: Tayriva was 648× faster than Receita Federal’s reference calculator

In a matched local benchmark on November 24, 2026, Tayriva calculated and committed the taxes for 10 million synthetic invoices in **34.30 seconds**. The [Brazilian federal tax authority’s own Java implementation](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular/tree/f1eebd7ce3157423b1a6aaca7dc1d6c3395452c4) took **6 hours, 10 minutes, 28 seconds**. All amounts matched **to the cent on all 10 million invoices**.

| Timed phase | Tayriva worksheet engine | Receita Federal RTC 1.7.2 / V0073 |
| --- | ---: | ---: |
| Read | 5.957 s | 28.144 s |
| Calculate | 18.665 s | 22,187.387 s |
| Write and commit | 9.105 s | 12.579 s |
| **Total elapsed** | **34.298726765 s** | **22,228.126987 s** |

Speedup is the ratio of measured elapsed times: **648.07×**. Phase timers do not capture every part of total elapsed time.

## What was tested

- Same Linux PC (Intel Core i7-8700K), both runs pinned to the same single logical CPU, one calculation worker each, no GPU and no per-invoice HTTP.
- Identical synthetic 2027 NFS-e inputs across four municipalities. The four CBS/IBS cases each had 2.5 million invoices: regular treatment (`000001`), 30% reduction (`200052`), 60% reduction (`200028`), and 100% reduction (`200016`). Nominal rates were illustrative.
- Every invoice was calculated individually, without reusing any previously calculated invoice result. Each timed run read from SQLite, calculated, and committed all results back to SQLite. Data generation, application startup, and post-run verification were excluded.
- Both databases were reopened and compared by invoice ID. All input fields and the five stored output fields (tax base, CBS, state IBS, municipal IBS, and total IBS) matched for all 10 million invoices.

## Scope

This measured one matched pair using a Tayriva development build, source commit `3265cf18b128ddae5b3736bc5f34ee2fb17238b9`. It does not benchmark the current downloadable release. Tayriva evaluated the four defined scenarios through worksheet formulas; the official code also performs broader validation and generates observability data. The comparison is for the same batch outputs, not equivalent feature coverage or a claim to implement the full tax rulebook.

The [downloadable NFS-e demo](../README.md) and [earlier single-scenario benchmark](README.md) are separate. Their instructions do not reproduce the four-case comparison.
