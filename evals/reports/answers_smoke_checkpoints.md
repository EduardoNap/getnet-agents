# Answer evaluation

Run on 2026-11-27 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 12 cases (dev), 1 runs each, at commit `da0e7e3+changes`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 10/10 | 10/10 | 10/10 | 10/10 |
| all, 95% interval | | 76%–100% | 76%–100% | 76%–100% | 76%–100% | 76%–100% | 72%–100% | 72%–100% | 72%–100% | 72%–100% |
| split=dev | 12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 10/10 | 10/10 | 10/10 | 10/10 |
| split=dev, 95% interval | | 76%–100% | 76%–100% | 76%–100% | 76%–100% | 76%–100% | 72%–100% | 72%–100% | 72%–100% | 72%–100% |
| abstain | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| blocked | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | - | - | - | - |
| followup | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| general | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| handoff | 1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | - | - | - | - |
| knowledge | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| multi | 2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| support | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

- Cases passing on every run: 12 of 12.
- Cases whose result changed between runs: none.
- Cases failing on every run: none.
- Verifier, by outcome: {'ok': 8, 'revised': 2}.
- Time per case: median 11.5 s, 95th percentile 21.0 s.
- Estimated cost: $0.0264 per request (answering only; tokens at list price).

## Runs that did not pass

None.
