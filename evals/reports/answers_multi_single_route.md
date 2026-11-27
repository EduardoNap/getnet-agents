# Answer evaluation

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 8 cases (dev), 3 runs each, at commit `d246848`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 24 | 0/24 | 24/24 | 0/24 | 0/24 | 3/24 | 24/24 | 24/24 | 0/24 | 10/24 |
| all, 95% interval | | 0%–14% | 86%–100% | 0%–14% | 0%–14% | 4%–31% | 86%–100% | 86%–100% | 0%–14% | 24%–61% |
| split=dev | 24 | 0/24 | 24/24 | 0/24 | 0/24 | 3/24 | 24/24 | 24/24 | 0/24 | 10/24 |
| split=dev, 95% interval | | 0%–14% | 86%–100% | 0%–14% | 0%–14% | 4%–31% | 86%–100% | 86%–100% | 0%–14% | 24%–61% |
| multi | 24 | 0/24 | 24/24 | 0/24 | 0/24 | 3/24 | 24/24 | 24/24 | 0/24 | 10/24 |

- Cases passing on every run: 0 of 8.
- Cases whose result changed between runs: none.
- Cases failing on every run: m1, m2, m3, m4, m5, m6, m7, m8.
- Verifier, by outcome: not run.
- Time per case: median 7.3 s, 95th percentile 8.5 s.
- Estimated cost: $0.0091 per request (answering only; tokens at list price).

## Runs that did not pass

- `m1` run 1: failed agents, tools, facts, complete. The decline details for TX-90411 (R$ 250.00, code 51, insufficient funds) match the reference and the evidence. The answer leaves out how to refund a sale on the machine (Estorno steps, password, same card, CV code, same day), which the reference covers.
- `m1` run 2: failed agents, tools, facts, complete. The decline details for TX-90411 (R$ 250.00, code 51, insufficient funds) match the reference and the evidence. The answer leaves out the refund (Estorno) steps the merchant asked about.
- `m1` run 3: failed agents, tools, facts, complete, useful. The decline facts (TX-90411, R$ 250.00, code 51, insufficient funds) match the reference and the evidence. The answer omits the second question, how to refund a sale on the machine (Estorno, password, amount, card, CV code, same day), so it is incomplete and only partly useful.
- `m2` run 1: failed agents, tools, facts, complete, useful. The terminal facts (GS-48213, Get Smart, offline, E-NET-02) match the reference and appear in the evidence. The answer never explains how to configure Wi-Fi (tap Wi-Fi, Procurar Redes, choose the network, enter the password, confirm), so it misses the second half of the question and gives no next step.
- `m2` run 2: failed agents, tools, facts, complete, useful. The answer correctly names the offline Get Smart GS-48213 with error E-NET-02. It never explains how to set up Wi-Fi (tap Wi-Fi, Procurar Redes, choose the network, enter the password and confirm), so it misses half of the question.
- `m2` run 3: failed agents, tools, facts, complete, useful. The answer correctly identifies the offline Get Smart GS-48213 and its E-NET-02 error, and every detail comes from the evidence. It never answers the second question, how to configure Wi-Fi, which the reference covers with the Wi-Fi > Procurar Redes > senha steps.
- `m3` run 1: failed agents, tools, facts, complete. The payout figures (R$ 1,265.59, R$ 42.30, total R$ 1,307.89) match the reference and the evidence. The answer leaves out the second question, the minimum advance amount of R$ 50.00.
- `m3` run 2: failed agents, tools, facts, complete. The payout figures (R$ 1,265.59 + R$ 42.30 = R$ 1,307.89 on 2026-11-27) match the reference and the evidence. The answer leaves out the second question, the R$ 50.00 minimum for an advance in the app, so it is incomplete.
- `m3` run 3: failed agents, tools, facts, complete. The payout amounts and the R$ 1,307.89 total match the reference and the evidence. The answer leaves out the minimum advance amount (R$ 50.00), which the reference covers.
- `m4` run 1: failed agents, tools, facts, complete, useful. The answer correctly identifies the Santander account ending in 4321 but omits how to change it (Getnet Brasil app: name/photo > Dados do Negócio > Dados bancários, or Portal do Cliente), so the second half of the question goes unanswered.
- `m4` run 2: failed agents, tools, facts, complete, useful. The account fact, Santander ending in 4321, is correct and grounded. The answer never says how to change the account (Getnet Brasil app: name/photo > Dados do Negócio > Dados bancários, or Portal do Cliente), so the second half of the question goes unanswered and the merchant gets no next step.
- `m4` run 3: failed agents, tools, facts, complete, useful. The Santander ****4321 account matches the reference and the evidence. The answer leaves out how to change the account (Getnet Brasil app: name/photo > Dados do Negócio > Dados bancários, or the Portal do Cliente), so the second half of the question goes unanswered.
- `m5` run 1: failed agents, tools, facts, complete, useful. The firmware facts (3.8.1, not up to date) match the reference and the evidence. The answer omits the second part of the question, how to request maintenance through the app or Portal Minha Conta, so it is incomplete and does not give the merchant the next step.
- `m5` run 2: failed agents, tools, facts, complete. The answer states the firmware 3.8.1 and its not-up-to-date status, both supported by the evidence. It never says how to request maintenance (the 'Manutenção de máquina' option in the app or 'Solicitar manutenção' in the Portal Minha Conta), so the second question goes unanswered.
- `m5` run 3: failed agents, tools, facts, complete, useful. The firmware facts (3.8.1, not up to date) match the reference and the evidence. The answer never explains how to request maintenance (the Getnet Brasil app's 'Manutenção de máquina' or Portal Minha Conta's 'Solicitar manutenção'), which leaves half of the question unanswered and gives the merchant no next step.
- `m6` run 1: failed agents, tools, facts, complete, useful. The amount received today, R$ 523,13 from yesterday's debit sale, agrees with the reference and the evidence. The answer leaves out the R$ 2.000,00 daily limit for transfers from the Get Conta to another bank, which the merchant asked about and the reference covers.
- `m6` run 2: failed agents, tools, facts, complete, useful. The answer gets today's payout right (R$ 523,13, net of yesterday's debit sale), and every figure it gives matches the evidence. However, it never answers the second question, the daily Get Conta transfer limit (R$ 2.000,00 per the reference), and gives no guidance on it.
- `m6` run 3: failed agents, tools, facts, complete. The answer omits the second part of the question, the daily Get Conta transfer limit of R$ 2.000,00. The figures it does give (R$ 523,13 paid today, plus the scheduled amounts) match the evidence and the reference.
- `m7` run 1: failed agents, tools, complete, useful. The approval facts (TX-90398, R$ 42.90, GM-10377, approved) match the reference and the evidence. The answer never explains the difference between 'autorizada' and 'aprovada', which was the second part of the merchant's question.
- `m7` run 2: failed agents, tools, complete. The approval facts (TX-90398, R$ 42.90, debit, GM-10377, approved) match the reference and the evidence. The answer never explains the difference between 'autorizada' and 'aprovada', which the reference covers.
- `m7` run 3: failed agents, tools, complete. The answer correctly confirms that TX-90398 was approved, and every fact it gives appears in the evidence. It never explains the difference between 'autorizada' and 'aprovada', which the reference covers.
- `m8` run 1: failed agents, tools, facts, complete, useful. The answer correctly reports error E-NET-02 with facts from the evidence, but it never answers whether the merchant can take card payments on a phone (Get Tap on an Android phone with NFC, contactless, no monthly fee).
- `m8` run 2: failed agents, tools, facts, complete. The error code, serial, last-seen time, Wi-Fi connection and firmware details all match the evidence and the reference. The answer never addresses the second question, whether the merchant can take card payments on a phone meanwhile; the reference answers it with Get Tap on an Android phone with NFC.
- `m8` run 3: failed agents, tools, facts, complete, useful. The error details are right and come from the evidence. The answer leaves out the second question entirely: it never mentions Get Tap or taking card payments on a phone.
