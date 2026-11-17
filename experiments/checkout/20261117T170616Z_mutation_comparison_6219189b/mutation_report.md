# Mutation testing — checkout

- Statut : `completed`
- Outil : `mutmut`

| Suite évaluée | Tués | Survivants | Sans test | Score des exécutés | Tués / tous générés | Statut |
|---|---:|---:|---:|---:|---:|---|
| Tests manuels | 60 | 35 | 0 | 63.16% | 63.16% | completed |
| Manuels + générés | 95 | 0 | 0 | 100.0% | 100.0% | completed |

Écart multi-agent moins baseline parmi les mutants exécutés : `36.84` points de pourcentage.
Écart multi-agent moins baseline sur tous les mutants : `36.84` points de pourcentage.

`Score des exécutés` = tués / (tués + survivants + timeout + suspects). `Tués / tous générés` inclut les mutants `no_tests` dans le dénominateur; il reflète la capacité totale de la suite à atteindre et détecter les mutations. Consulte les sorties brutes dans `cases/` et `logs/`.
