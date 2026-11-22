# Journal d'implémentation

Historique de l'implémentation, epic par epic et tâche par tâche. Chaque page suit le modèle
[`TEMPLATE.md`](TEMPLATE.md) et documente :

- l'objectif et les tâches couvertes ;
- ce qui a été créé ou modifié, avec les chemins ;
- les décisions prises et les écarts éventuels par rapport au plan ;
- les commandes de vérification et leurs résultats ;
- les limites connues et les suites.

## Index

| Epic | Jalon | Page | État |
|---|---|---|---|
| **E0** — Fondations | M0 | [E0-fondations.md](E0-fondations.md) | E0-01 → E0-11 terminés |
| E1 — IAM | M0 → M2 | [E1-iam.md](E1-iam.md) | E1-01 → E1-05 terminés ; E1-06 → E1-07 à venir |
| E2 — Skills / blobs | M1 | [E2-skills.md](E2-skills.md) | cœur Skills + diff/historique livrés ; E2-07, E2-09 → E2-11, E2-13, E2-15 → E2-16 à venir |
| E3 — Projets / missions | M3 | — | à venir |
| E4 — Plans de travail | M4 | — | à venir |
| E5 — Compétences | M5 | — | à venir |
| E6 — Contrats d'API | M0 → | — | à venir |
| E7 — MCP | M2 → | — | à venir |
| E13 — Exploitation | M6 | — | à venir |

> Les pages sont créées au démarrage de chaque epic, puis complétées au fil des tâches. Une
> page n'est jamais réécrite après coup pour masquer un écart : les écarts sont documentés.

## Correspondance backlog ↔ documentation

Le backlog détaillé reste la source de vérité pour le **périmètre** et les **critères de fin**
([`tasks/workhub-plan-developpement.md`](../../tasks/workhub-plan-developpement.md)). La
documentation d'implémentation décrit, elle, **ce qui existe réellement** dans le dépôt et
**comment le vérifier**.
