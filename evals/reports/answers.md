# Answer evaluation

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 60 cases (blind), 3 runs each, at commit `d246848`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 180 | 161/180 | 174/180 | 175/180 | 175/180 | 174/180 | 172/180 | 178/180 | 171/180 | 172/180 |
| all, 95% interval | | 84%–93% | 93%–98% | 94%–99% | 94%–99% | 93%–98% | 91%–98% | 96%–100% | 91%–97% | 91%–98% |
| split=blind | 180 | 161/180 | 174/180 | 175/180 | 175/180 | 174/180 | 172/180 | 178/180 | 171/180 | 172/180 |
| split=blind, 95% interval | | 84%–93% | 93%–98% | 94%–99% | 94%–99% | 93%–98% | 91%–98% | 96%–100% | 91%–97% | 91%–98% |
| abstain | 21 | 17/21 | 18/21 | 18/21 | 18/21 | 20/21 | 21/21 | 21/21 | 21/21 | 21/21 |
| approval | 9 | 6/9 | 8/9 | 9/9 | 9/9 | 7/9 | 8/9 | 9/9 | 9/9 | 7/9 |
| followup | 18 | 16/18 | 18/18 | 18/18 | 18/18 | 18/18 | 17/18 | 16/18 | 18/18 | 17/18 |
| knowledge | 48 | 42/48 | 46/48 | 46/48 | 46/48 | 46/48 | 43/48 | 48/48 | 42/48 | 43/48 |
| multi | 36 | 35/36 | 36/36 | 36/36 | 36/36 | 35/36 | 36/36 | 36/36 | 35/36 | 36/36 |
| resume | 12 | 11/12 | 12/12 | 12/12 | 12/12 | 12/12 | 11/12 | 12/12 | 12/12 | 12/12 |
| support | 36 | 34/36 | 36/36 | 36/36 | 36/36 | 36/36 | 36/36 | 36/36 | 34/36 | 36/36 |

- Cases passing on every run: 48 of 60.
- Cases whose result changed between runs: xa2, xa3, xf2, xf4, xk16, xk3, xm3, xn2, xr3, xs10.
- Cases failing on every run: xk15, xn4.
- Verifier, by outcome: {'ok': 143, 'revised': 19}.
- Time per case: median 10.3 s, 95th percentile 20.6 s.
- Estimated cost: $0.0255 per request (answering only; tokens at list price).

## Runs that did not pass

- `xk3` run 3: failed complete. The answer correctly names CNH or RG with a clear photo and mentions the face validation, all supported by the evidence. It omits that registration also confirms the phone number and e-mail with codes, which the reference covers.
- `xk15` run 1: failed correct, complete, useful. The reference says the Initial (starter) plan is free and charges R$ 1.00 per paid link, only when the link's payment is approved. The answer instead says no starter plan exists and gives R$ 14,90/mês and a 1,90% rate. Those figures do appear in the evidence, but the answer contradicts the reference and never gives the starter plan's cost.
- `xk15` run 2: failed correct, complete, useful. The reference says the Initial plan is free and charges R$ 1.00 per paid link only when payment is approved. The answer instead says it cannot confirm a starter plan price and offers R$ 14,90/mês and 1,90%, which does not match the reference.
- `xk15` run 3: failed correct, complete, useful. The reference says the starter (Initial) plan is free and charges R$ 1.00 per paid link only when the payment is approved. The answer instead says no starter plan exists and gives R$ 14,90/mês as the price, which contradicts the reference. The figures it does give all appear in the evidence.
- `xk16` run 1: failed outcome, agents, tools, facts, correct, complete, useful. The answer does not give the fix from the reference (type #90 and press Enter on the home screen to update the terminal). It only hands off to a human. The ticket number it states is grounded in the evidence.
- `xk16` run 2: failed outcome, agents, tools, facts, correct, complete, useful. The answer never gives the fix in the reference (type #90 and press Enter on the home screen to update), so it is incorrect and incomplete. The ticket number and handoff are grounded, but only escalating is not useful when a concrete step exists, and the evidence shows GS-48213 has outdated firmware.
- `xn2` run 2: failed facts. The answer says no official, current Curitiba office address was found, which matches the reference. The Rua Emiliano Perneta, 860 address is taken from the cited registration record and is clearly flagged as a closed registration, not presented as a working office. It also refers the merchant to 4002-4000, in Portuguese.
- `xn4` run 1: failed outcome, agents, tools. The answer invents no procedure or fine amount and hands both questions to a human agent, as the reference expects. Ticket TCK-CC62D3DE appears in the evidence, and the reply is in Portuguese with a clear next step.
- `xn4` run 2: failed outcome, agents, tools. The answer invents no procedure or fine amount and hands both questions to a human agent, which matches the reference's expectation. The only specific fact, ticket number TCK-0AF1F27E, appears in the evidence, and the answer is in Portuguese.
- `xn4` run 3: failed outcome, agents, tools. The answer invents no procedure or fine amount and hands both questions to a human agent through ticket TCK-2170FBAA, which appears in the evidence. This is consistent with the reference, and the answer is in Portuguese.
- `xs10` run 1: failed complete. Both days' sales match the reference and the evidence: TX-71198, R$ 2,400.00 on credit, and TX-71150, R$ 75.40 on debit. The answer leaves out the combined total of R$ 2,475.40 that the reference gives.
- `xs10` run 3: failed complete. The transaction IDs, amounts and methods all match the reference and the evidence. The answer omits the combined total of R$ 2,475.40 that the reference gives.
- `xm3` run 3: failed facts, complete. The R$ 174.60 net from the R$ 180.00 credit sale, paid out in 30 days on 2026-12-26, matches the reference and the evidence. The answer only says businesses (CNPJ) can open a Get Conta. It omits the reference's point that every company type (MEI, EI, EIRELI, franchise, LTDA) qualifies.
- `xf2` run 2: failed correct, grounded, useful. The answer miscounts 30 days from 26/11/2026 as 27/12/2026 instead of 26/12/2026, so it says there is no payout then. The reference says R$ 328,47 from today's credit sale arrives in 30 days, and the date 27/12/2026 does not appear in the evidence.
- `xf4` run 3: failed grounded. The fee of R$ 5,40 on the R$ 180,00 sale matches the reference, and the net amount, payout date and account all come from the evidence. The '3%' rate never appears in the evidence; it was calculated by the assistant.
- `xr3` run 2: failed correct. The answer repeats the agent's instruction: the signed receipt, sent through the app within 7 days, under CB-20931. It then says it cannot tell whether 7 or 12 days applies, which contradicts the reference's definite 7-day deadline for this case. Everything it says is in the evidence and it gives a next step.
- `xa2` run 1: failed facts, useful. The answer matches the reference facts (request not approved, battery can be replaced without swapping the terminal, maintenance request opened), and every detail is in the evidence. However, the merchant wrote in Portuguese and the answer is in English, so it is not useful.
- `xa2` run 2: failed facts, correct, useful. The answer says the replacement was refused because it was not requested, while the reference gives the reason as the battery being replaceable without swapping the terminal. The reply is also in English with a leaked internal note, though the merchant's message was in Portuguese.
- `xa3` run 1: failed outcome. The answer correctly says GM-77001 does not appear on the merchant's account and requests no replacement. It instead escalates via ticket TCK-74F9CEB5, and both the ticket and the terminal list are supported by the evidence.

## Graded again

23 stored answers that quote a ticket number were graded again with the fact that the system issued that ticket added to the evidence (`python -m evals.regrade`). No answer was regenerated. The report as first written is `answers_as_run.md`.

xk16#1, xk16#2, xn4#1, xn4#2, xn4#3, xr1#1, xr1#2, xr1#3, xr2#1, xr2#2, xr2#3, xr3#1, xr3#3, xr4#1, xr4#2, xr4#3, xa1#1, xa1#2, xa1#3, xa2#1, xa2#2, xa2#3, xa3#1
