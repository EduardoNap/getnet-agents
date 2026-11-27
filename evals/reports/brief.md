# The brief's example questions

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging, at commit `dc68489`. 10 questions, 3 runs each: **27/30 runs passed**.

| # | Question | passed | path of the first run |
|---|---|---|---|
| 1 | What's the difference between the Get Clássica and the Get Smart? | 3/3 | guardrail → router → knowledge[search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 2 | What's the weather forecast in Porto Alegre tomorrow? | 1/3 | guardrail → router → knowledge[web_search] → router → synthesizer → verifier |
| 3 | When will the money from yesterday's sales be deposited? | 3/3 | guardrail → router → support[get_settlement_schedule] → router → synthesizer → verifier |
| 4 | Do I need a bank account to receive my sales via Pix? | 3/3 | guardrail → router → knowledge[search_getnet_kb] → router → synthesizer → verifier |
| 5 | My card machine won't connect to the internet, what should I do? | 3/3 | guardrail → router → support[get_terminal_status] → router → knowledge[search_getnet_kb,search_getnet_kb,search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 6 | How does receivables advance (antecipação) work with Getnet? | 3/3 | guardrail → router → knowledge[search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 7 | What's the euro exchange rate today? | 3/3 | guardrail → router → knowledge[web_search] → router → synthesizer → verifier |
| 8 | My card machine is showing a transaction decline error. | 2/3 | guardrail → router → support[get_recent_transactions,get_terminal_status] → router → knowledge[search_getnet_kb,search_getnet_kb,search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 9 | How many installments can I split a sale into with the crediário? | 3/3 | guardrail → router → knowledge[search_getnet_kb] → router → synthesizer → verifier |
| 10 | Can I sell through WhatsApp using the Payment Link? | 3/3 | guardrail → router → knowledge[search_getnet_kb] → router → synthesizer → verifier |

## Runs that did not pass

- #2 run 2: grounded. The News Minimalist quote is cut off at "períodos de cé...", so "periods of overcast skies" is the assistant's guess, not evidence. The HG Brasil figures (17–27°C, 0%) and the Meteored figures (70%, 0.1 mm) match their citations.
- #2 run 3: useful. The answer gives the forecast for Thursday Nov 26, which is today, not tomorrow (Nov 27). The evidence did include tomorrow's forecast (Partly cloudy, 80°/65°, east wind 8-17 mph), so the merchant did not get what they asked for. The figures it states do appear in the evidence.
- #8 run 3: useful. Every figure in the answer is grounded in the tool evidence. It is not fully useful, though: it says the help pages give no fix for the offline Get Smart's E-NET-02 "no network connection" error, yet the evidence includes a Wi-Fi setup guide the merchant could follow. It also gives only 'call support' for the code 51 decline instead of explaining that the issuer declined the card and the customer should try another payment method.
