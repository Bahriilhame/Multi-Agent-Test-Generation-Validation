# MBPP - bilan pilote sur 10 tâches

- Jeu : `google-research/google-research/mbpp/sanitized-mbpp.json`, split de test officiel (IDs 11-510).
- Protocol : tests de référence `test_list` versus tests de référence plus tests générés par Ollama.
- Limite : ce protocole mesure la réussite d’exécution et la couverture sur les solutions de référence; il ne mesure pas le score pass@k ni le score de mutation.

## Résumé

| Mesure | Résultat |
|---|---:|
| Baselines de référence réussies | 10/10 |
| Lots multi-agent réussis | 5/10 (50.0%) |
| Tests générés qui passent sur la solution de référence | 53/59 (89.8%) |
| Tests générés qui échouent | 6/59 |
| Couverture moyenne avant | 97.14% |
| Couverture moyenne après | 100.0% |
| Variation moyenne de couverture | +2.86 points |
| Critique heuristique moyen | 67.0/100 |

Un lot multi-agent est déclaré réussi uniquement si tous ses tests passent. Un bon taux de tests individuels peut donc coexister avec un taux plus faible de lots entièrement réussis.

## Résultats par tâche

| ID | Baseline | Multi-agent | Tests générés passés | Tests générés échoués | Couverture avant | Couverture après | Critique | Run |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 455 | passed | passed | 5/5 | 0 | 100.0% | 100.0% | 80.0 | `20261118T174632Z_multiagent_67130486` |
| 145 | passed | failed | 5/6 | 1 | 100.0% | 100.0% | 50.0 | `20261118T174903Z_multiagent_b9b9b3dd` |
| 396 | passed | passed | 6/6 | 0 | 100.0% | 100.0% | 80.0 | `20261118T174903Z_multiagent_b9b9b3dd` |
| 93 | passed | failed | 5/6 | 1 | 71.42857142857143% | 100.0% | 70.0 | `20261118T174903Z_multiagent_b9b9b3dd` |
| 234 | passed | passed | 6/6 | 0 | 100.0% | 100.0% | 80.0 | `20261118T175334Z_multiagent_c1fe4d69` |
| 395 | passed | passed | 6/6 | 0 | 100.0% | 100.0% | 80.0 | `20261118T175334Z_multiagent_c1fe4d69` |
| 405 | passed | passed | 6/6 | 0 | 100.0% | 100.0% | 80.0 | `20261118T175334Z_multiagent_c1fe4d69` |
| 300 | passed | failed | 5/6 | 1 | 100.0% | 100.0% | 50.0 | `20261118T180140Z_multiagent_c5c599e0` |
| 64 | passed | failed | 4/6 | 2 | 100.0% | 100.0% | 50.0 | `20261118T180140Z_multiagent_c5c599e0` |
| 238 | passed | failed | 5/6 | 1 | 100.0% | 100.0% | 50.0 | `20261118T180140Z_multiagent_c5c599e0` |

## Lecture des échecs

- MBPP/145, /93 et /300 ont inclus des entrées négatives ou vides dont le comportement n’était pas garanti par l’énoncé.
- MBPP/64 contient des attentes erronées pour le tri des valeurs négatives et un mélange de types numériques et texte.
- MBPP/238 contient une valeur attendue incorrecte pour le nombre de sous-chaînes.
- MBPP/396 passe, mais ses tests générés vérifient peu de sorties distinctes.

Les échecs sont conservés comme résultats du générateur; ils n’ont pas été corrigés manuellement dans le score.
