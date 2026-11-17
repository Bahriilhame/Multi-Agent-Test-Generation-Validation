# Mutation testing — checkout

- Statut : `completed`
- Outil : `mutmut`

| Suite évaluée | Tués | Survivants | Sans test | Score des exécutés | Tués / tous générés | Statut |
|---|---:|---:|---:|---:|---:|---|
| Tests manuels | 21 | 24 | 50 | 46.67% | 22.11% | completed |
| Manuels + générés | 67 | 28 | 0 | 70.53% | 70.53% | completed |

Écart multi-agent moins baseline parmi les mutants exécutés : `23.86` points de pourcentage.
Écart multi-agent moins baseline sur tous les mutants : `48.42` points de pourcentage.

`Score des exécutés` = tués / (tués + survivants + timeout + suspects). `Tués / tous générés` inclut les mutants `no_tests` dans le dénominateur; il reflète la capacité totale de la suite à atteindre et détecter les mutations. Consulte les sorties brutes dans `cases/` et `logs/`.
