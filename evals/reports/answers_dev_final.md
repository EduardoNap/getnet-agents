# Answer evaluation

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 37 cases (dev), 3 runs each, at commit `030386a+changes`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 111 | 84/111 | 109/111 | 111/111 | 111/111 | 111/111 | 97/99 | 97/99 | 96/99 | 74/99 |
| all, 95% interval | | 67%–83% | 94%–100% | 97%–100% | 97%–100% | 97%–100% | 93%–99% | 93%–99% | 91%–99% | 65%–82% |
| split=dev | 111 | 84/111 | 109/111 | 111/111 | 111/111 | 111/111 | 97/99 | 97/99 | 96/99 | 74/99 |
| split=dev, 95% interval | | 67%–83% | 94%–100% | 97%–100% | 97%–100% | 97%–100% | 93%–99% | 93%–99% | 91%–99% | 65%–82% |
| abstain | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| blocked | 6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | - | - | - | - |
| followup | 6 | 5/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 5/6 |
| general | 6 | 4/6 | 4/6 | 6/6 | 6/6 | 6/6 | 4/6 | 6/6 | 4/6 | 4/6 |
| handoff | 6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | - | - | - | - |
| knowledge | 33 | 28/33 | 33/33 | 33/33 | 33/33 | 33/33 | 33/33 | 33/33 | 33/33 | 28/33 |
| multi | 24 | 10/24 | 24/24 | 24/24 | 24/24 | 24/24 | 24/24 | 23/24 | 23/24 | 11/24 |
| support | 27 | 22/27 | 27/27 | 27/27 | 27/27 | 27/27 | 27/27 | 26/27 | 27/27 | 23/27 |

- Cases passing on every run: 21 of 37.
- Cases whose result changed between runs: f1, g2, k11, k5, k9, m1, m2, m5, m8, s1, s4, s6, s9.
- Cases failing on every run: m3, m4, m7.
- Verifier, by outcome: {'ok': 85, 'revised': 11, 'skipped': 1}.
- Time per case: median 9.9 s, 95th percentile 21.4 s.
- Estimated cost: $0.027 per request (answering only; tokens at list price).

## Runs that did not pass

- `s1` run 2: failed useful. The facts are right and supported by the evidence: R$ 523.13 net (R$ 530.50 gross, R$ 7.37 fees) for the 2026-11-25 debit sale, to Santander ****4321. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `s4` run 1: failed useful. The facts match the reference and the evidence: GS-48213 on firmware 3.8.1 is not up to date, and GM-10377 on firmware 2.4.0 is up to date. The answer is not useful because it is written in Portuguese while the merchant wrote in English.
- `s6` run 1: failed useful. The fee (R$ 44.41), gross (R$ 1,310.00), net (R$ 1,265.59) and payout date all match the reference and evidence. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `s6` run 3: failed grounded. Fees R$ 44.41, gross R$ 1,310.00 and net R$ 1,265.59 match the reference and evidence. However, the '3,39%' fee rate does not appear in the evidence; it is the assistant's own calculation, which fails a literal grounding check even though the arithmetic is accurate.
- `s9` run 3: failed useful. The facts all match the reference and the evidence: R$ 180.00 gross, R$ 5.40 in fees, R$ 174.60 net, payout on 2026-12-26 (30 days) to Santander ****9988. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `k5` run 1: failed useful. The facts match the reference and the evidence: smartphone card machine, no monthly fee, Android with NFC, and the Android 11 vs 12 discrepancy. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `k5` run 3: failed useful. The facts match the reference and the evidence: smartphone card machine, no monthly fee, NFC Android, and the 11 vs 12 discrepancy. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `k9` run 1: failed useful. The answer correctly says a 'desfeita' sale was not approved within the processing time, and every fact is in the evidence. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `k9` run 3: failed useful. The content matches the reference and the evidence: a sale is 'desfeita' when it is not approved within the processing time. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `k11` run 2: failed useful. The steps match the reference and the evidence. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `g2` run 1: failed outcome, correct, complete, useful. The assistant gave no rate and escalated to a ticket, even though the evidence held sourced rates (Wise mid-market 5.7202 BRL; Analistas R$ 5,7446) and the reference expects one. The answer states no specific facts, so it is grounded, but it is wrong, incomplete and not useful.
- `g2` run 2: failed outcome, correct, complete, useful. The reference expects a current USD/BRL rate with a source, and the evidence had one (e.g., R$ 5,75 per Nomad, updated 26/11/2026). The answer said it could not find one and only opened a ticket.
- `m1` run 1: failed useful. The facts are correct and grounded: TX-90411, R$ 250,00, code 51 insufficient funds, and the Estorno steps with password 0000 on the same day. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m1` run 2: failed complete, useful. The answer is in Portuguese although the merchant wrote in English. It also gives code 51 and the issuer but leaves out the reason itself, insufficient funds.
- `m2` run 1: failed grounded. The answer says the Getnet site has no page specifically about the Get Smart, but the evidence includes a 'Soluções Get Smart' page, so that statement is contradicted. The rest (GS-48213 offline with E-NET-02, and the Wi-Fi steps) matches the reference and the evidence.
- `m3` run 1: failed useful. The facts are correct and grounded: R$ 1.265,59 + R$ 42,30 = R$ 1.307,89 scheduled for 27/11, and a R$ 50,00 minimum. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m3` run 2: failed useful. The facts match the reference and the evidence: R$ 1,265.59 + R$ 42.30 = R$ 1,307.89, and the R$ 50.00 minimum. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m3` run 3: failed useful. The facts match the reference and the evidence: R$ 1,265.59 + R$ 42.30 = R$ 1,307.89 tomorrow, and a R$ 50.00 minimum advance. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m4` run 1: failed useful. The facts match the reference and the evidence: the Santander account ending 4321 and the app and Portal steps. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m4` run 2: failed useful. The facts match the reference and the evidence: Santander ending 4321, the app path and the Portal do Cliente option. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m4` run 3: failed useful. The facts match the reference and the evidence: the Santander account ending in 4321 and the app and Portal steps. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `f1` run 1: failed useful. The fees (R$ 7,37 debit, R$ 44,41 credit, R$ 51,78 total) match the reference and the settlement evidence, but the merchant wrote in English and the answer is in Portuguese.
- `m5` run 2: failed useful. The facts agree with the reference and appear in the evidence: firmware 3.8.1 is out of date, and the app and portal maintenance steps match. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m7` run 1: failed useful. The facts match the reference and the evidence: TX-90398, R$ 42.90, debit, GM-10377, approved, and the autorizada/aprovada definitions from the KB. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m7` run 2: failed useful. The facts match the reference and the evidence: TX-90398, R$ 42.90 debit on GM-10377 approved, and the Autorizada/Aprovada definitions. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
- `m7` run 3: failed useful. The facts are right and grounded in the evidence: TX-90398, R$ 42.90 debit, approved on 2026-11-26 on GM-10377, plus the autorizada/aprovada definitions from the KB. However, the merchant wrote in English and the answer is in Portuguese.
- `m8` run 1: failed useful. The facts match the reference and the evidence: error E-NET-02, Get Tap on Android 11+ with NFC, and no monthly fee. However, the merchant wrote in English and the answer is in Portuguese, so it is not useful.
