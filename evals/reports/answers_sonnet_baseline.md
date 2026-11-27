# Answer evaluation

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging. 37 cases (dev), 3 runs each, at commit `030386a+changes`. Raw results are in the `.json` file next to this one.

`outcome`, `agents`, `tools` and `facts` are checked by code. `correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.

| Kind | runs | passed | outcome | agents | tools | facts | correct | grounded | complete | useful |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 111 | 87/111 | 110/111 | 111/111 | 110/111 | 108/111 | 95/99 | 80/99 | 95/99 | 95/99 |
| all, 95% interval | | 70%–85% | 95%–100% | 97%–100% | 95%–100% | 92%–99% | 90%–98% | 72%–87% | 90%–98% | 90%–98% |
| split=dev | 111 | 87/111 | 110/111 | 111/111 | 110/111 | 108/111 | 95/99 | 80/99 | 95/99 | 95/99 |
| split=dev, 95% interval | | 70%–85% | 95%–100% | 97%–100% | 95%–100% | 92%–99% | 90%–98% | 72%–87% | 90%–98% | 90%–98% |
| abstain | 3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| blocked | 6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | - | - | - | - |
| followup | 6 | 5/6 | 6/6 | 6/6 | 5/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| general | 6 | 0/6 | 5/6 | 6/6 | 6/6 | 6/6 | 5/6 | 1/6 | 5/6 | 5/6 |
| handoff | 6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | - | - | - | - |
| knowledge | 33 | 27/33 | 33/33 | 33/33 | 33/33 | 30/33 | 30/33 | 30/33 | 30/33 | 30/33 |
| multi | 24 | 17/24 | 24/24 | 24/24 | 24/24 | 24/24 | 24/24 | 17/24 | 24/24 | 24/24 |
| support | 27 | 23/27 | 27/27 | 27/27 | 27/27 | 27/27 | 27/27 | 23/27 | 27/27 | 27/27 |

- Cases passing on every run: 27 of 37.
- Cases whose result changed between runs: f1, m3, s4.
- Cases failing on every run: g1, g2, k2, k9, m5, m8, s3.
- Time per case: median 8.5 s, 95th percentile 21.9 s.
- Estimated cost: $0.0226 per request (answering only; tokens at list price).

## Runs that did not pass

- `s3` run 1: failed grounded. The answer matches the reference: GS-48213 is offline, last seen 19 hours ago with error E-NET-02, and GM-10377 is online. However, the troubleshooting steps (check the site Wi-Fi and signal range, then restart the machine) do not appear in the evidence.
- `s3` run 2: failed grounded. The terminal facts match the reference and the evidence: GS-48213 offline, last seen 19 hours ago, error E-NET-02, and GM-10377 online. However, the troubleshooting steps (check the site's Wi-Fi, confirm the network, restart the Get Smart) do not appear in the evidence.
- `s3` run 3: failed grounded. The answer matches the reference: GS-48213 offline, last seen 19 hours ago, error E-NET-02, and GM-10377 online. It is not grounded: the troubleshooting steps (check the Wi-Fi, stay within router range, restart the machine) are not in the evidence. The claim that it went offline "yesterday" is also an inference, since 19 hours ago could still fall on today.
- `s4` run 1: failed grounded. The firmware versions and up-to-date status for both machines match the reference. However, the claim that the Get Smart can't download the update until it reconnects to wifi, and that reconnecting is the way to update it, is not in the evidence.
- `k2` run 1: failed facts, correct, complete, useful. The reference gives a daily withdrawal limit of R$ 1.000,00 and a transfer limit of R$ 2.000,00, but the answer says it could not find the limit. The evidence indeed lacks these figures, so the answer is grounded, yet it misses both limits and only refers the merchant to support.
- `k2` run 2: failed facts, correct, complete, useful. The reference gives a daily withdrawal limit of R$ 1.000,00 and a transfer limit of R$ 2.000,00, but the answer says it could not find the limit. Its statements match the evidence, which shows no limit, so it is grounded, but it omits both figures and does not answer the question.
- `k2` run 3: failed facts, correct, complete, useful. The reference gives R$ 1.000,00 per day for withdrawals and R$ 2.000,00 per day for transfers, but the answer says the limit is not published. The evidence indeed lacks the figure, so the answer is grounded, but it gives neither limit.
- `k9` run 1: failed grounded. The definition (not approved within the processing time) matches the reference and the KB. However, the claim that the sale had already been requested with status "Autorizada" is not in the evidence, which never links Desfeita to a prior Autorizada status.
- `k9` run 2: failed grounded. The definition matches the reference and the evidence. However, the claim that a 'desfeita' sale would previously have had the status 'Autorizada' is the assistant's own inference; the evidence never links the two statuses.
- `k9` run 3: failed grounded. The core definition matches the reference and the evidence: not approved within the processing time. However, the claim that a 'Desfeita' sale first shows as 'Autorizada' and then changes status is the assistant's own inference; the evidence never describes this sequence.
- `g1` run 1: failed grounded. The answer matches the reference (Canberra), but the tools returned nothing, so the name 'Canberra' has no supporting evidence.
- `g1` run 2: failed grounded. The answer matches the reference (Canberra), but the tools returned nothing, so the name 'Canberra' has no support in the evidence.
- `g1` run 3: failed grounded. The answer matches the reference (Canberra). However, the tools returned nothing, so the name "Canberra" has no supporting evidence.
- `g2` run 1: failed grounded. The answer says the Analistas quote was updated on 26/11/2026 at 13:11, but the evidence cuts off at "Atualizada em..." with no date or time. The rates themselves (R$ 5,7446 and 5.7202 BRL at 14:16 UTC) are supported and attributed to sources.
- `g2` run 2: failed outcome, correct, complete, useful. The evidence contained sourced USD/BRL rates (e.g., Wise 5.7202, Analistas R$ 5,7446), but the answer gave no rate and escalated instead, though the reference expects a sourced figure. It makes no unsupported claims.
- `g2` run 3: failed grounded. The figure 'Wise's page shows 1 USD = 5.744 BRL' appears nowhere in the evidence. The other figures (R$5.75, 13h53, −1.33%, 5.7202 at 02:16 PM UTC) are supported.
- `m3` run 1: failed grounded. The payout amounts (R$ 1.265,59 + R$ 42,30 = R$ 1.307,89) and the R$ 50,00 minimum match the reference and the evidence. However, the claim that enabling automatic advance 'não tem custo' is not supported: the KB only says 'a habilitação é livre', meaning enabling is unrestricted, and says nothing about cost.
- `f1` run 3: failed tools. The fees (R$ 7,37 debit, R$ 44,41 credit, R$ 51,78 total) match the reference. They follow directly from the gross and net amounts in the earlier conversation, as does the computed gross total of R$ 1.840,50.
- `m5` run 1: failed grounded. The answer's facts match the reference: firmware 3.8.1 is outdated, and the app and portal maintenance steps are right. But it says the account shows no open maintenance request for this machine, and no tool returned maintenance request data.
- `m5` run 2: failed grounded. The answer matches the reference on firmware 3.8.1 not being up to date and on both maintenance routes. However, the troubleshooting steps are not in the evidence: the claim that the machine must come back online to receive the update, checking the Wi-Fi, and restarting it near the router.
- `m5` run 3: failed grounded. The firmware status and both maintenance procedures match the reference and the evidence. However, the advice to reconnect to Wi-Fi so the update can download and install is a step not found in the evidence.
- `m8` run 1: failed grounded. The troubleshooting steps (check the Wi-Fi router is on and has internet, then restart the machine) do not appear in any evidence. The error code E-NET-02 and the Get Tap details match the reference.
- `m8` run 2: failed grounded. The error E-NET-02 and the Get Tap details match the evidence. However, the troubleshooting steps (check the Wi-Fi router is on and has internet, then reconnect the machine to Wi-Fi) appear nowhere in the tool evidence.
- `m8` run 3: failed grounded. The error code E-NET-02 and the Get Tap details (Android 11+, NFC) match the reference. However, the troubleshooting step (check the Wi‑Fi, then restart the machine) does not appear anywhere in the evidence. The claim that the customer taps a card on the phone is also inferred, since the evidence only mentions a phone or watch with a digital wallet.
