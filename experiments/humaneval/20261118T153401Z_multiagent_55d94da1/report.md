# HumanEval — évaluation de génération de tests

- Statut : `interrupted`
- Tâches : 3
- Référence réussie : 1/3
- Multi-agent réussi : 0/3

| Mesure moyenne par tâche | Baseline | Multi-agent | Écart |
|---|---:|---:|---:|
| Couverture lignes (%) | 100.0 | non mesuré | non mesuré |
| Critique heuristique (/100) | — | non mesuré | — |

> Protocole : reference tests vs reference + generated unit tests; not official pass@k. Le score de critique est une heuristique déterministe, pas un score LLM.

## Résultats par tâche

| Task ID | Baseline | Multi-agent | Couverture baseline | Couverture après | Delta | Tests générés | Critique |
|---|---|---|---:|---:|---:|---:|---:|
| HumanEval/49 | passed | interrupted | 100.0 | non mesuré | non mesuré | non mesuré | non mesuré |

HumanEval fournit des tâches et des tests de référence; ce protocole mesure l'ajout de tests unitaires à une solution de référence. Il ne calcule pas le score officiel de génération de solutions pass@k.
