# The brief's example questions

Run on 2026-11-26 with `claude-sonnet-5-5` answering and `claude-opus-5-5` judging, at commit `d246848`. 10 questions, 3 runs each: **23/30 runs passed**.

| # | Question | passed | path of the first run |
|---|---|---|---|
| 1 | What's the difference between the Get Clássica and the Get Smart? | 2/3 | guardrail → router → knowledge[search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 2 | What's the weather forecast in Porto Alegre tomorrow? | 0/3 | guardrail → router → knowledge[web_search] → router → knowledge[web_search] → router → escalation[create_support_ticket] |
| 3 | When will the money from yesterday's sales be deposited? | 3/3 | guardrail → router → support[get_settlement_schedule] → router → synthesizer → verifier |
| 4 | Do I need a bank account to receive my sales via Pix? | 3/3 | guardrail → router → knowledge[search_getnet_kb] → router → synthesizer → verifier |
| 5 | My card machine won't connect to the internet, what should I do? | 0/3 | guardrail → router → knowledge[search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 6 | How does receivables advance (antecipação) work with Getnet? | 3/3 | guardrail → router → knowledge[search_getnet_kb,search_getnet_kb] → router → synthesizer → verifier |
| 7 | What's the euro exchange rate today? | 3/3 | guardrail → router → knowledge[web_search] → router → synthesizer → verifier |
| 8 | My card machine is showing a transaction decline error. | 3/3 | guardrail → router → support[get_recent_transactions,get_terminal_status] → router → synthesizer → verifier |
| 9 | How many installments can I split a sale into with the crediário? | 3/3 | guardrail → router → knowledge[search_getnet_kb] → router → synthesizer → verifier |
| 10 | Can I sell through WhatsApp using the Payment Link? | 3/3 | guardrail → router → knowledge[search_getnet_kb] → router → synthesizer → verifier |

## Runs that did not pass

- #1 run 1: grounded. The claim that the Get Smart is free above R$ 80 mil/month is not clearly supported. On the same page layout, the Get Tap reading the answer itself uses puts the Get Smart at R$ 40 mil, so the R$ 80 mil reading is inconsistent; the fees and kiosk-mode details are grounded.
- #2 run 1: answered, grounded, useful. No reference was written, so correct and complete are true. The ticket code TCK-1D9A8BBC does not appear in the evidence. The answer is in Portuguese although the merchant wrote in English, and it declines even though the evidence gave tomorrow's (Nov 27) forecast: partly cloudy, 80°/65°.
- #2 run 2: grounded. Most figures match the cited forecasts for Nov 27 (WU 83/65, Meteored 80/65, Weather Network 27/17). However, the evidence never ties the timeanddate '16%' value to Nov 27 or labels it as a precipitation chance, so that claim is unsupported.
- #2 run 3: grounded. No reference answer exists, so correct and complete are true. The HG Brasil and Meteored figures match the evidence, but the News Minimalist passage is cut off at "períodos de cé...", so "periods of overcast sky" fills in text the evidence does not contain.
- #5 run 1: agents, tools. No reference answer exists, so correct and complete are true. Every step matches the evidence: the Wi-Fi setup and the function sequences for ADQ 1-84, 1-18, 1-19, 4-30 and 1-87. The answer is in English, like the merchant's message, and gives actionable next steps.
- #5 run 2: agents, tools. No reference answer was written, so correct and complete are true. The Wi-Fi steps and the ADQ 1-18, 1-84, 1-19, 1-87 and 4-30 fixes all match the knowledge-base passages, and the support number is the configured one. The answer is in English and gives clear next steps.
- #5 run 3: agents, tools. There is no reference answer, so correct and complete are true. The Wi-Fi steps and the ADQ 1-84, 1-18, 1-19, 4-30 and 1-87 procedures all match the knowledge-base evidence. The answer is in English, matching the merchant, gives clear next steps and points to the configured support line.
