# Answer evaluation

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 8 cases (dev), 3 runs each, at commit `d246848`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 24 | 23/24 | 24/24 | 24/24 | 24/24 | 23/24 | 23/24 | 24/24 | 23/24 | 23/24 |
| all, 95% interval | | 80%–99% | 86%–100% | 86%–100% | 86%–100% | 80%–99% | 80%–99% | 86%–100% | 80%–99% | 80%–99% |
| split=dev | 24 | 23/24 | 24/24 | 24/24 | 24/24 | 23/24 | 23/24 | 24/24 | 23/24 | 23/24 |
| split=dev, 95% interval | | 80%–99% | 86%–100% | 86%–100% | 86%–100% | 80%–99% | 80%–99% | 86%–100% | 80%–99% | 80%–99% |
| multi | 24 | 23/24 | 24/24 | 24/24 | 24/24 | 23/24 | 23/24 | 24/24 | 23/24 | 23/24 |

- Cases passing on every run: 7 of 8.
- Cases whose result changed between runs: m6.
- Cases failing on every run: none.
- Verifier, by outcome: {'ok': 19, 'revised': 5}.
- Time per case: median 19.1 s, 95th percentile 30.2 s.
- Estimated cost: $0.0483 per request (answering only; tokens at list price).

## Runs that did not pass

- `m6` run 2: failed facts, correct, complete, useful. The answer never says that R$ 523,13 (from yesterday's debit sale) was paid today. It discusses only today's sales, which leaves 'quanto recebi hoje' unanswered and implies nothing came in. The transfer limit of R$ 2.000,00 is correct and grounded.
