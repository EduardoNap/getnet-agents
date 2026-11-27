# Retrieval evaluation

119 questions that are not the brief's examples, each with its correct page labelled by hand. Top 6 chunks of 40 candidates. Higher is better; 1.0 is perfect.

| Group | Search | n | recall@1 | recall@3 | recall@6 | mrr | ndcg@6 | context_precision@6 |
|---|---|---|---|---|---|---|---|---|
| all | vector only | 119 | 0.504 | 0.622 | 0.706 | 0.588 | 0.608 | 0.221 |
| all | keywords only | 119 | 0.471 | 0.555 | 0.655 | 0.546 | 0.612 | 0.203 |
| all | hybrid | 119 | 0.529 | 0.655 | 0.756 | 0.616 | 0.657 | 0.251 |
| all | hybrid, English rewritten in Portuguese | 119 | 0.706 | 0.849 | 0.941 | 0.792 | 0.825 | 0.325 |
| kind=adversarial | vector only | 15 | 0.467 | 0.600 | 0.667 | 0.550 | 0.571 | 0.156 |
| kind=adversarial | keywords only | 15 | 0.467 | 0.667 | 0.667 | 0.581 | 0.622 | 0.167 |
| kind=adversarial | hybrid | 15 | 0.467 | 0.667 | 0.733 | 0.582 | 0.636 | 0.178 |
| kind=adversarial | hybrid, English rewritten in Portuguese | 15 | 0.733 | 0.867 | 0.933 | 0.820 | 0.877 | 0.256 |
| kind=hard | vector only | 40 | 0.300 | 0.400 | 0.525 | 0.392 | 0.402 | 0.175 |
| kind=hard | keywords only | 40 | 0.350 | 0.425 | 0.550 | 0.429 | 0.474 | 0.188 |
| kind=hard | hybrid | 40 | 0.300 | 0.500 | 0.625 | 0.432 | 0.478 | 0.229 |
| kind=hard | hybrid, English rewritten in Portuguese | 40 | 0.425 | 0.750 | 0.850 | 0.594 | 0.637 | 0.321 |
| kind=plain | vector only | 64 | 0.641 | 0.766 | 0.828 | 0.720 | 0.745 | 0.266 |
| kind=plain | keywords only | 64 | 0.547 | 0.609 | 0.719 | 0.612 | 0.696 | 0.222 |
| kind=plain | hybrid | 64 | 0.688 | 0.750 | 0.844 | 0.740 | 0.774 | 0.281 |
| kind=plain | hybrid, English rewritten in Portuguese | 64 | 0.875 | 0.906 | 1.000 | 0.909 | 0.931 | 0.344 |
| lang=en | vector only | 65 | 0.523 | 0.615 | 0.723 | 0.597 | 0.622 | 0.246 |
| lang=en | keywords only | 65 | 0.169 | 0.246 | 0.415 | 0.263 | 0.377 | 0.124 |
| lang=en | hybrid | 65 | 0.431 | 0.523 | 0.615 | 0.505 | 0.535 | 0.205 |
| lang=en | hybrid, English rewritten in Portuguese | 65 | 0.754 | 0.877 | 0.954 | 0.826 | 0.843 | 0.341 |
| lang=pt | vector only | 54 | 0.481 | 0.630 | 0.685 | 0.578 | 0.590 | 0.191 |
| lang=pt | keywords only | 54 | 0.833 | 0.926 | 0.944 | 0.887 | 0.895 | 0.299 |
| lang=pt | hybrid | 54 | 0.648 | 0.815 | 0.926 | 0.750 | 0.804 | 0.306 |
| lang=pt | hybrid, English rewritten in Portuguese | 54 | 0.648 | 0.815 | 0.926 | 0.750 | 0.804 | 0.306 |
| split=blind | vector only | 55 | 0.455 | 0.564 | 0.618 | 0.528 | 0.552 | 0.167 |
| split=blind | keywords only | 55 | 0.455 | 0.564 | 0.655 | 0.543 | 0.616 | 0.179 |
| split=blind | hybrid | 55 | 0.455 | 0.636 | 0.782 | 0.574 | 0.640 | 0.233 |
| split=blind | hybrid, English rewritten in Portuguese | 55 | 0.673 | 0.836 | 0.927 | 0.766 | 0.816 | 0.288 |
| split=confirm | vector only | 12 | 0.500 | 0.667 | 0.833 | 0.632 | 0.679 | 0.222 |
| split=confirm | keywords only | 12 | 0.667 | 0.667 | 0.750 | 0.706 | 0.755 | 0.225 |
| split=confirm | hybrid | 12 | 0.667 | 0.750 | 0.917 | 0.725 | 0.770 | 0.278 |
| split=confirm | hybrid, English rewritten in Portuguese | 12 | 0.833 | 0.833 | 1.000 | 0.868 | 0.899 | 0.319 |
| split=main | vector only | 52 | 0.558 | 0.673 | 0.769 | 0.642 | 0.650 | 0.279 |
| split=main | keywords only | 52 | 0.442 | 0.519 | 0.635 | 0.513 | 0.575 | 0.224 |
| split=main | hybrid | 52 | 0.577 | 0.654 | 0.692 | 0.636 | 0.649 | 0.263 |
| split=main | hybrid, English rewritten in Portuguese | 52 | 0.712 | 0.865 | 0.942 | 0.802 | 0.817 | 0.365 |

## Questions still missed in the top 6 as the service searches (7)

- `r40` How much cash can I withdraw per day?
- `r49` qual o valor mínimo para antecipar?
- `r52` preciso mudar a conta onde cai o dinheiro das vendas
- `b24` How do I get my money sooner without requesting it every time?
- `b25` cliente nao recebeu o comprovante da compra
- `b31` onde acompanho quanto a getnet ja me pagou por bandeira
- `a12` I need a document proving that a sale was declined.
