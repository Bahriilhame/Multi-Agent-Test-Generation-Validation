# Protocole expérimental

## Questions mesurées

Les expériences distinguent l'exécution correcte des tests et la valeur des assertions. Couverture de ligne/branche, variation en points de pourcentage, taux de réussite pytest, tests produits, qualité critique, temps de génération et d'exécution sont rapportés séparément.

## Reproduction

1. Garder le même commit, image Docker et dépendances entre baseline et multi-agent.
2. Fixer la graine lors de l'échantillonnage HumanEval/MBPP et conserver les IDs effectivement sélectionnés.
3. Répéter les essais LLM pour mesurer la variabilité; conserver prompt/model, erreurs, durée et contenu généré.
4. Comparer les assertions par mutation testing lorsque le projet et l'outil le permettent.
5. Ne comparer directement que des métriques issues du même protocole. HumanEval/MBPP test generation, mutation score et SWE-bench resolved sont des résultats distincts.

Les exécutions courtes actuelles valident les adaptateurs et le pipeline, mais ne constituent pas une étude scientifique complète. Une évaluation de recherche devrait augmenter l'échantillon, répéter les seeds, publier l'image exacte, l'environnement, les versions, les intervalles de confiance et les limitations.

## Limites des métriques

- La couverture confirme que des lignes/branches ont été exécutées, pas qu'une faute serait détectée.
- Le score LLM dépend du modèle et du prompt; le score AST/pytest est heuristique.
- Le mode SWE-bench `run-tests` travaille sur le commit de base et mesure la qualité des tests générés; seule l'évaluation upstream des patches mesure la résolution d'issues.
- Les tests existants qui échouent, les dépendances manquantes et les incompatibilités d'image doivent être interprétés comme résultats d'exécution distincts, pas masqués par un score moyen.
