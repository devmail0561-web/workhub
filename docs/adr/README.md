# Décisions d'architecture (ADR)

Une décision par fichier, nommée `NNN-titre-court.md` (ex. `001-monolithe-modulaire.md`).
Chaque ADR tient sur une page : contexte, décision, conséquences, alternatives.

## Index

| ADR | Sujet | Statut |
|---|---|---|
| [001](001-monolithe-modulaire.md) | Monolithe modulaire et règles de dépendance | acceptée (2026-11-13) |
| [002](002-blobs-postgres.md) | Stockage des blobs dans PostgreSQL, adressage par SHA-256 | acceptée (2026-11-13) |
| [003](003-manifeste-empreinte.md) | Manifeste et empreinte d'une SkillVersion (`requirements` inclus) | acceptée (2026-11-13) |
| [004](004-identite-principal.md) | Modèle d'identité : Principal, intégrations, jetons, scopes | acceptée (2026-11-13) |
| [005](005-mcp-adaptateur.md) | MCP comme adaptateur (transports, séparation lecture/écriture) | acceptée (2026-11-13) |
| [006](006-brouillons-versions.md) | Brouillons mutables vs versions immuables | acceptée (2026-11-13) |
| [007](007-plans-template-instance.md) | Modèle de plan : template / version / instance / overrides | acceptée (2026-11-13) |
| [008](008-suppression-archivage.md) | Stratégie de suppression : soft delete et archivage | acceptée (2026-11-13) |
| [009](009-concurrence-etag.md) | Gestion de la concurrence (ETag / If-Match) | acceptée (2026-11-13) |
| 010 | Catalogue d'outils : types, exigences, signatures | à rédiger (E14) |
| 011 | Mécanisme `Proposal` et absence de LLM embarqué | à rédiger (E15) |
| 012 | Profil technique de projet : instantané immuable | à rédiger (E15) |

## Convention

- Une ADR acceptée n'est **jamais réécrite** : une nouvelle décision la remplace et référence
  l'ancienne.
- Le statut est mis à jour dans cet index (`proposée`, `acceptée`, `remplacée par NNN`).
- Les ADR 001 à 009 sont exigées par **E0-07** ; les suivantes accompagneront leurs epics.

Voir le plan de développement, section 3.4, pour le détail des sujets.
