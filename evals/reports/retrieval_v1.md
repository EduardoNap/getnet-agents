# Retrieval evaluation, before the error-code fix

The same questions and labels as `retrieval.md`, with error codes such as "1-19" not counted as keywords.

64 questions that are not the brief's examples, each with its correct page labelled by hand. Top 6 chunks of 40 candidates. Higher is better; 1.0 is perfect.

| Group | Search | n | recall@1 | recall@3 | recall@6 | mrr | ndcg@6 | context_precision@6 |
|---|---|---|---|---|---|---|---|---|
| all | vector only | 64 | 0.547 | 0.672 | 0.781 | 0.640 | 0.656 | 0.268 |
| all | hybrid | 64 | 0.609 | 0.734 | 0.766 | 0.690 | 0.690 | 0.268 |
| all | hybrid, English rewritten in Portuguese | 64 | 0.734 | 0.797 | 0.828 | 0.780 | 0.764 | 0.292 |
| kind=hard | vector only | 20 | 0.300 | 0.400 | 0.600 | 0.409 | 0.391 | 0.225 |
| kind=hard | hybrid | 20 | 0.450 | 0.500 | 0.600 | 0.510 | 0.500 | 0.267 |
| kind=hard | hybrid, English rewritten in Portuguese | 20 | 0.450 | 0.550 | 0.650 | 0.530 | 0.507 | 0.267 |
| kind=plain | vector only | 44 | 0.659 | 0.795 | 0.864 | 0.745 | 0.776 | 0.288 |
| kind=plain | hybrid | 44 | 0.682 | 0.841 | 0.841 | 0.772 | 0.776 | 0.269 |
| kind=plain | hybrid, English rewritten in Portuguese | 44 | 0.864 | 0.909 | 0.909 | 0.894 | 0.881 | 0.303 |
| lang=en | vector only | 37 | 0.541 | 0.622 | 0.757 | 0.618 | 0.640 | 0.288 |
| lang=en | hybrid | 37 | 0.568 | 0.703 | 0.730 | 0.656 | 0.661 | 0.270 |
| lang=en | hybrid, English rewritten in Portuguese | 37 | 0.784 | 0.811 | 0.838 | 0.812 | 0.788 | 0.311 |
| lang=pt | vector only | 27 | 0.556 | 0.741 | 0.815 | 0.670 | 0.677 | 0.241 |
| lang=pt | hybrid | 27 | 0.667 | 0.778 | 0.815 | 0.737 | 0.730 | 0.265 |
| lang=pt | hybrid, English rewritten in Portuguese | 27 | 0.667 | 0.778 | 0.815 | 0.737 | 0.730 | 0.265 |
| split=confirm | vector only | 12 | 0.500 | 0.667 | 0.833 | 0.632 | 0.679 | 0.222 |
| split=confirm | hybrid | 12 | 0.500 | 0.667 | 0.667 | 0.600 | 0.598 | 0.208 |
| split=confirm | hybrid, English rewritten in Portuguese | 12 | 0.667 | 0.750 | 0.750 | 0.729 | 0.713 | 0.250 |
| split=main | vector only | 52 | 0.558 | 0.673 | 0.769 | 0.642 | 0.650 | 0.279 |
| split=main | hybrid | 52 | 0.635 | 0.750 | 0.788 | 0.711 | 0.711 | 0.282 |
| split=main | hybrid, English rewritten in Portuguese | 52 | 0.750 | 0.808 | 0.846 | 0.792 | 0.776 | 0.301 |

## Questions still missed in the top 6 as the service searches (11)

- `r08` What does error ADQ 1-19 mean and how do I fix it?
- `r34` Tap to pay stopped working on my reader.
- `r35` Part of my balance is being held back as a guarantee. Why?
- `r38` Can I turn my phone into a card reader?
- `r40` How much cash can I withdraw per day?
- `r45` quero receber o dinheiro das vendas no mesmo dia
- `r49` qual o valor mínimo para antecipar?
- `r50` erro adq 119
- `c01` Erro ADQ 1-84, como resolvo?
- `c02` What should I do about error ADQ 3-30?
- `c03` erro IDL 1-08 na maquininha
