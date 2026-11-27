# Answer evaluation

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 60 cases (blind), 3 runs each, at commit `d246848`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 180 | 151/180 | 174/180 | 175/180 | 175/180 | 174/180 | 174/180 | 160/180 | 171/180 | 172/180 |
| all, 95% interval | | 78%–89% | 93%–98% | 94%–99% | 94%–99% | 93%–98% | 93%–98% | 83%–93% | 91%–97% | 91%–98% |
| split=blind | 180 | 151/180 | 174/180 | 175/180 | 175/180 | 174/180 | 174/180 | 160/180 | 171/180 | 172/180 |
| split=blind, 95% interval | | 78%–89% | 93%–98% | 94%–99% | 94%–99% | 93%–98% | 93%–98% | 83%–93% | 91%–97% | 91%–98% |
| abstain | 21 | 17/21 | 18/21 | 18/21 | 18/21 | 20/21 | 21/21 | 18/21 | 21/21 | 21/21 |
| approval | 9 | 2/9 | 8/9 | 9/9 | 9/9 | 7/9 | 9/9 | 2/9 | 9/9 | 7/9 |
| followup | 18 | 16/18 | 18/18 | 18/18 | 18/18 | 18/18 | 17/18 | 16/18 | 18/18 | 17/18 |
| knowledge | 48 | 42/48 | 46/48 | 46/48 | 46/48 | 46/48 | 44/48 | 46/48 | 42/48 | 43/48 |
| multi | 36 | 35/36 | 36/36 | 36/36 | 36/36 | 35/36 | 36/36 | 36/36 | 35/36 | 36/36 |
| resume | 12 | 5/12 | 12/12 | 12/12 | 12/12 | 12/12 | 11/12 | 6/12 | 12/12 | 12/12 |
| support | 36 | 34/36 | 36/36 | 36/36 | 36/36 | 36/36 | 36/36 | 36/36 | 34/36 | 36/36 |

- Cases passing on every run: 45 of 60.
- Cases whose result changed between runs: xa3, xf2, xf4, xk16, xk3, xm3, xn2, xr3, xs10.
- Cases failing on every run: xa1, xa2, xk15, xn4, xr2, xr4.
- Verifier, by outcome: {'ok': 143, 'revised': 19}.
- Time per case: median 10.3 s, 95th percentile 20.6 s.
- Estimated cost: $0.0255 per request (answering only; tokens at list price).

## Runs that did not pass

- `xk3` run 3: failed complete. The answer correctly names CNH or RG with a clear photo and mentions the face validation, all supported by the evidence. It omits that registration also confirms the phone number and e-mail with codes, which the reference covers.
- `xk15` run 1: failed correct, complete, useful. The reference says the Initial (starter) plan is free and charges R$ 1.00 per paid link, only when the link's payment is approved. The answer instead says no starter plan exists and gives R$ 14,90/mês and a 1,90% rate. Those figures do appear in the evidence, but the answer contradicts the reference and never gives the starter plan's cost.
- `xk15` run 2: failed correct, complete, useful. The reference says the Initial plan is free and charges R$ 1.00 per paid link only when payment is approved. The answer instead says it cannot confirm a starter plan price and offers R$ 14,90/mês and 1,90%, which does not match the reference.
- `xk15` run 3: failed correct, complete, useful. The reference says the starter (Initial) plan is free and charges R$ 1.00 per paid link only when the payment is approved. The answer instead says no starter plan exists and gives R$ 14,90/mês as the price, which contradicts the reference. The figures it does give all appear in the evidence.
- `xk16` run 1: failed outcome, agents, tools, facts, grounded, complete, useful. The answer never gives the fix (update the terminal by typing #90 and pressing Enter), even though the evidence shows the Get Smart firmware is out of date; it only hands off to a human. The ticket number TCK-319DC2DA does not appear in the evidence, which returned only a handoff status.
- `xk16` run 2: failed outcome, agents, tools, facts, correct, grounded, complete, useful. The answer omits the reference fix of typing #90 and pressing Enter on the home screen to update the terminal. The ticket number TCK-A5EA8483 does not appear in the evidence, since the escalate_to_human tool returned only a status. The answer gives no actionable next step, although the evidence shows outdated firmware.
- `xn2` run 2: failed facts. The answer says no official, current Curitiba office address was found, which matches the reference. The Rua Emiliano Perneta, 860 address is taken from the cited registration record and is clearly flagged as a closed registration, not presented as a working office. It also refers the merchant to 4002-4000, in Portuguese.
- `xn4` run 1: failed outcome, agents, tools, grounded. The answer invents no procedure or fine amount and hands off to a human, which matches the reference. However, the ticket number TCK-CC62D3DE and the claim that a ticket was opened do not appear in the evidence, since the tools returned nothing.
- `xn4` run 2: failed outcome, agents, tools, grounded. The answer invents no procedure or fine amount and hands the case to human support, which matches the reference. However, the ticket number TCK-0AF1F27E and the claim that a ticket was opened do not appear in the evidence, since the tools returned nothing.
- `xn4` run 3: failed outcome, agents, tools, grounded. The answer invents no procedure or fine amount, which matches the reference, and it hands both questions to support in Portuguese. However, the ticket code TCK-2170FBAA and the claim that a ticket was opened do not appear in the evidence, since the tools returned nothing.
- `xs10` run 1: failed complete. Both days' sales match the reference and the evidence: TX-71198, R$ 2,400.00 on credit, and TX-71150, R$ 75.40 on debit. The answer leaves out the combined total of R$ 2,475.40 that the reference gives.
- `xs10` run 3: failed complete. The transaction IDs, amounts and methods all match the reference and the evidence. The answer omits the combined total of R$ 2,475.40 that the reference gives.
- `xm3` run 3: failed facts, complete. The R$ 174.60 net from the R$ 180.00 credit sale, paid out in 30 days on 2026-12-26, matches the reference and the evidence. The answer only says businesses (CNPJ) can open a Get Conta. It omits the reference's point that every company type (MEI, EI, EIRELI, franchise, LTDA) qualifies.
- `xf2` run 2: failed correct, grounded, useful. The answer miscounts 30 days from 26/11/2026 as 27/12/2026 instead of 26/12/2026, so it says there is no payout then. The reference says R$ 328,47 from today's credit sale arrives in 30 days, and the date 27/12/2026 does not appear in the evidence.
- `xf4` run 3: failed grounded. The fee of R$ 5,40 on the R$ 180,00 sale matches the reference, and the net amount, payout date and account all come from the evidence. The '3%' rate never appears in the evidence; it was calculated by the assistant.
- `xr2` run 1: failed grounded. The answer matches the reference on the block of sale TX-71225, the 5-business-day review and the email notice. However, it cites ticket number TCK-8D2D5594, which does not appear in the evidence.
- `xr2` run 2: failed grounded. The answer matches the reference: TX-71225 is blocked for review, the result comes within 5 business days, and the notice arrives by email. However, the ticket number TCK-F2052EC5 does not appear anywhere in the evidence.
- `xr2` run 3: failed grounded. The facts match the reference (TX-71225 blocked, result within 5 business days, notice by email), but the ticket code TCK-79A88D8C does not appear in the evidence.
- `xr3` run 2: failed correct. The answer repeats the agent's instruction: the signed receipt, sent through the app within 7 days, under CB-20931. It then says it cannot tell whether 7 or 12 days applies, which contradicts the reference's definite 7-day deadline for this case. Everything it says is in the evidence and it gives a next step.
- `xr4` run 1: failed grounded. The answer correctly relays the R$ 15,00 charge error and the refund within 3 business days. However, the ticket number TCK-DF70B018 does not appear anywhere in the evidence.
- `xr4` run 2: failed grounded. The answer matches the reference: the R$ 15,00 charge was Getnet's error and will be refunded within 3 business days. However, the ticket number TCK-58116384 does not appear in the evidence.
- `xr4` run 3: failed grounded. The R$ 15,00 refund within 3 business days matches the reference and the agent's reply. However, the ticket code TCK-B68AFAC9 does not appear in the evidence.
- `xa1` run 1: failed grounded. The ticket number TCK-61C11958 does not appear in the evidence. The approval, terminal GC-30977 and order RPL-E18EF8D7 match the human agent's reply and the reference.
- `xa1` run 2: failed grounded. The answer cites ticket number TCK-814E7443, which appears nowhere in the evidence. The evidence supports only the approval, terminal GC-30977 and order RPL-9E2D2559, and these match the reference.
- `xa1` run 3: failed grounded. The answer matches the reference: the human agent approved and requested the replacement of terminal GC-30977. However, the ticket number TCK-40621C27 does not appear in the evidence, which contains only the approval, the terminal and order RPL-F14E1870.
- `xa2` run 1: failed facts, grounded, useful. The ticket number TCK-3BC94C20 does not appear in the evidence, so the answer is not grounded. The answer is also in English while the merchant's message is in Portuguese, which makes it not useful.
- `xa2` run 2: failed facts, grounded, useful. The facts match the reference: the replacement was not approved, the battery can be swapped, and a maintenance request was opened. However, the ticket number TCK-F16F246E does not appear in the evidence. The reply is in English, includes a leaked internal note, and the merchant wrote in Portuguese.
- `xa2` run 3: failed grounded. The answer matches the reference: the replacement was not approved, the battery can be swapped without replacing the terminal, and a maintenance request was opened. However, the ticket number TCK-D0CCC095 does not appear anywhere in the evidence.
- `xa3` run 1: failed outcome, grounded. The answer correctly says GM-77001 is not on the account and requests no replacement. However, the ticket number TCK-74F9CEB5 is not in the evidence: escalate_to_human returned only a handoff status.
