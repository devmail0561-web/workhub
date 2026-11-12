# Documentation WorkHub

Cette documentation décrit **ce qui est implémenté, comment le faire tourner, et pourquoi les choix ont été faits**. Elle est mise à jour à chaque tâche du backlog : aucune tâche n'est considérée terminée sans sa page d'implémentation.

## Parcours recommandé

| Document | À lire pour… |
|---|---|
| [Installation](installation.md) | installer les prérequis et lancer la stack |
| [Développement](developpement.md) | commandes, workflow, définition de « terminé » |
| [Architecture](architecture.md) | structure du dépôt et règles de dépendance |
| [Journal d'implémentation](implementation/README.md) | l'historique détaillé, tâche par tâche |
| [Changelog](../CHANGELOG.md) | la liste des changements notables, par version |
| [Audits](audits/README.md) | les contrôles qualité, les constats et les corrections |
| [ADR](adr/README.md) | les décisions d'architecture et leur justification |

## Documents de référence du projet

- [Plan de développement et backlog](../tasks/workhub-plan-developpement.md)
- [Cahier des charges (PDF)](plans-de-travail.pdf)
- [Guide de contribution](../CONTRIBUTING.md)

## Convention de documentation

- **Une page par epic** dans `implementation/`, nommée `E<epic>-<theme>.md` (ex. `E0-fondations.md`).
- **Une ADR par décision structurante** dans `adr/`, nommée `NNN-titre-court.md`.
- Les pages d'implémentation suivent le modèle [`implementation/TEMPLATE.md`](implementation/TEMPLATE.md).
- Elles sont écrites **au fil de l'eau**, pas après coup : la page est complétée dans la même branche que le code.
- Toute commande de vérification citée doit être **reproductible** et, quand c'est possible, son résultat attendu est indiqué.
