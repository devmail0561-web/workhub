# Architecture

Vue synthétique de l'architecture **telle qu'implémentée** et des règles qui encadrent la
suite. Les décisions détaillées vivent dans les [ADR](adr/README.md) et le plan de
développement.

## Style

**Monolithe modulaire** organisé en quatre couches par module :

```text
interfaces (REST, MCP, CLI)  ──►  application (cas d'usage + autorisation)
                                        │
                                        ▼
                                  domain (entités, règles)
                                        ▲
                                        │
                              infrastructure (SQLAlchemy, blobs)
```

Règle centrale : **REST, MCP et CLI n'embarquent aucune logique métier**. Ils traduisent un
protocole vers un cas d'usage de la couche `application`.

## Modules

Sous `backend/src/workhub/` :

| Module | Rôle | Jalon |
|---|---|---|
| `shared` | noyau : `Principal`, erreurs, horloge, ids, pagination | M0 |
| `iam` | utilisateurs, sessions, jetons, scopes | M0–M2 |
| `skills` | Skills versionnées, blobs, manifeste, exigences | M1 |
| `projects` | projets, missions, profil technique | M3 |
| `plans` | templates, versions, instances de plans | M4 |
| `competencies` | compétences, rôles, preuves | M5 |
| `execution` | tâches, exécutions, livrables, blocages | M3 |
| `knowledge` | ressources documentaires | M6 |
| `tools` | catalogue de scripts versionnés | M3b |
| `proposals` | mécanisme générique de propositions | M3b |
| `integrations` | environnements connectés, déploiements | M6 |
| `audit` | journal append-only | M0 |
| `interfaces/rest` | routeurs FastAPI `/api/v1` | M0 |
| `interfaces/mcp` | serveur MCP | M2 |

Chaque module métier est structuré en `domain/`, `application/`, `infrastructure/` et expose
son point d'entrée public dans `api.py`.

## Règles de dépendance (vérifiées par import-linter)

Les règles sont exécutées à chaque CI via `uv run lint-imports` (backend et CLI).

| # | Règle | Contrat | Portée |
|---|---|---|---|
| 1 | `domain` n'importe ni FastAPI, ni SQLAlchemy, ni application/infrastructure/interfaces | `forbidden` | `backend` |
| 2 | `application` n'importe pas `infrastructure` ni `interfaces` | `forbidden` | `backend` |
| 3 | Les modules ne dépendent pas les uns des autres (tout couplage doit être déclaré) | `independence` | `backend` |
| 4 | `interfaces.rest` et `interfaces.mcp` ne parlent qu'à `application` | `forbidden` | `backend` |
| 5 | `cli` ne dépend pas du package backend | `forbidden` | `cli` |

Précisions d'implémentation :

- **Règle 3** : `import-linter` n'exprime pas nativement « importer uniquement via `api.py` ».
  Le contrat `independence` est donc **plus strict** : aucun import croisé n'est autorisé par
  défaut. Quand un module devra appeler l'API publique d'un autre, l'import sera **whitelisté
  explicitement** dans le contrat (`ignore_imports`), ce qui rend tout couplage visible en
  revue.
- **Règle 5** : le CLI étant un package séparé (`workhub_cli`), la règle est portée par un
  contrat dans `cli/pyproject.toml`, avec `include_external_packages = true` pour pouvoir
  interdire le module externe `workhub`.
- Les contrats utilisent des jokers (`workhub.*.domain`) pour couvrir tous les modules sans
  duplication : un nouveau module est automatiquement soumis aux règles 1, 2 et 4.

## Frontières et dépendances externes

- **Pas de LLM embarqué** dans l'application (décision D8 du plan) : les suggestions passent
  par le mécanisme `Proposal`.
- **L'application n'installe et n'exécute rien** : le catalogue d'outils contient des scripts
  et leurs exigences déclarées ; c'est l'agent externe qui décide (décision D7).
- **MCP est un adaptateur mince** dans le même processus, qui réutilise les services de la
  couche `application` (décision D4).

## Points d'entrée implémentés à ce stade

| Point d'entrée | Fichier | État |
|---|---|---|
| API REST | `backend/src/workhub/interfaces/rest/app.py` | `GET /api/v1/health` |
| CLI | `cli/src/workhub_cli/__init__.py` | package vide (commandes à venir) |
| MCP | `backend/src/workhub/interfaces/mcp/` | vide (M2) |