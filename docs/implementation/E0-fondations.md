# E0 — Fondations

| Champ | Valeur |
|---|---|
| Epic | `E0` |
| Jalon | M0 — Fondations |
| Tâches couvertes | `E0-01` → `E0-07` |
| Statut | E0-01 → E0-07 terminés ; E0-08 → E0-11 à faire |
| Dernière mise à jour | 2026-11-13 |
| ADR liées | [001 → 009](../adr/README.md) |
| Commits | `bb7f49b` (documents), `0b82963` (fondations) |

## Objectif

Poser un dépôt monorepo reproductible, un outillage de qualité bloquant en CI et une stack
locale saine, **avant la première ligne de métier**. C'est l'ordre imposé par le plan
(section 13, action 2 : « CI verte avant la première ligne métier »).

## Tâches et état

| Tâche | Description | État | Critère de fin vérifié |
|---|---|---|---|
| `E0-01` | Monorepo (backend, cli, frontend, deploy, docs), licence, README, CONTRIBUTING | ✅ | arborescence §3.2 en place |
| `E0-02` | Config Python : uv, ruff, pyright strict, pytest, pre-commit | ✅ | `uv run pytest` + lint passent |
| `E0-03` | import-linter avec les règles §3.3 + preuve qu'une violation échoue | ✅ | violation volontaire détectée |
| `E0-04` | Docker Compose Postgres + API + web, healthchecks, `.env.example` | ✅ | `docker compose up` sain (vérifié) |
| `E0-05` | CI GitHub Actions : lint, types, tests, import-linter, pip-audit, build | ✅ | workflow vert sur le runner self-hosted (run `43317081941`) |
| `E0-06` | Modèle de données v0 : diagramme + DDL des tables MVP | ✅ | DDL appliqué sur Postgres 16, 12 scénarios d'invariants validés ([schéma](../specs/schema-v0.md)) |
| `E0-07` | ADR 001 → 009 | ✅ | 9 ADR acceptées et indexées dans [docs/adr](../adr/README.md) |

## Ce qui a été implémenté

### E0-01 — Arborescence et documents racine

```text
workhub-plan/
├── .gitignore
├── README.md               # présentation, stack, démarrage, liens
├── CONTRIBUTING.md         # prérequis, commandes, règles, DoD, commits
├── LICENSE                 # MIT
├── backend/
│   ├── src/workhub/        # 12 modules métier + interfaces/{rest,mcp}
│   └── tests/{unit,integration,contract,security}
├── cli/
├── frontend/
├── deploy/
├── docs/{adr,specs,integrations,implementation}
└── .github/workflows/
```

Chaque module métier de `backend/src/workhub/` contient `domain/`, `application/`,
`infrastructure/` (packages vides) et un `api.py` documenté comme **seul point d'entrée
autorisé** pour les autres modules. `workhub/__init__.py` expose `__version__ = "0.1.0"`.

### E0-02 — Outillage Python

**Backend** (`backend/pyproject.toml`) :

- package `workhub`, `requires-python = ">=3.12"`, build `hatchling` (layout `src/`) ;
- dépendances d'exécution : `fastapi`, `pydantic`, `pydantic-settings`, `uvicorn[standard]` ;
- groupe `dev` : `httpx`, `import-linter`, `pip-audit`, `pre-commit`, `pyright`, `pytest`,
  `pytest-asyncio`, `pytest-cov`, `ruff` ;
- ruff : cibles `E,W,F,I,UP,B,SIM,RUF`, largeur 100, `known-first-party = ["workhub"]` ;
- pyright : `typeCheckingMode = "strict"`, Python 3.12, `.venv` local ;
- pytest : `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope
  = "function"`, `pythonpath = ["src"]` ;
- couverture : `--cov=workhub` par défaut, seuil bloquant global **80 %**
  (`[tool.coverage.report] fail_under`).

**CLI** (`cli/pyproject.toml`) : package séparé `workhub-cli` (`typer`, `httpx`), avec sa propre
configuration ruff/pyright/pytest et un contrat import-linter (règle 5).

**Sonde de santé** : `backend/src/workhub/interfaces/rest/app.py` expose
`GET /api/v1/health` → `{"status":"ok","version":"0.1.0"}`. Elle sert de healthcheck Docker et
de premier test de bout en bout (`backend/tests/unit/test_health.py`, client `httpx`
`ASGITransport` pour rester compatible avec pyright strict).

**pre-commit** (`.pre-commit-config.yaml` à la racine) : hooks de base (trailing whitespace, EOF,
YAML, TOML, conflits, gros fichiers), puis un jeu de hooks locaux par projet (`backend` et
`cli`) exécutant ruff, pyright et import-linter depuis le bon environnement. À installer depuis
la racine : `uv run --project backend pre-commit install`.

Les fichiers `uv.lock` de `backend/` et `cli/` sont versionnés pour des builds reproductibles.

### E0-03 — Règles d'architecture

Six contrats `import-linter` dans `backend/pyproject.toml`, un septième dans
`cli/pyproject.toml` (voir le détail des règles dans [Architecture](../architecture.md#règles-de-dépendance-vérifiées-par-import-linter)) :

1. domaine sans framework ni dépendance vers les couches hautes ;
2. `application` sans `infrastructure`/`interfaces` ;
3. indépendance des modules **métier** (couplage explicite uniquement) ;
4. `interfaces` ne parlent qu'à `application` ;
5. le CLI ne dépend pas du package backend ;
6. le noyau `shared` ne dépend d'aucun module métier ;
7. les modules métier n'importent de `shared` que son API publique.

La configuration active `include_external_packages = true` pour pouvoir interdire des modules
externes (`fastapi`, `sqlalchemy`, `workhub`).

### E0-04 — Stack Docker

- `backend/Dockerfile` : image `python:3.12-slim`, installation **reproductible** via
  `uv sync --frozen --no-dev --no-editable` (image `ghcr.io/astral-sh/uv:0.13.0`, `uv.lock`
  respecté), exécution sous l'utilisateur non privilégié `appuser` (uid 10001), `uvicorn` sur
  le port 8000.
- `backend/.dockerignore` : exclut `.venv`, caches et tests.
- `deploy/docker-compose.yml` : `db` (Postgres 16-alpine), `api` (build backend), `web`
  (Nginx 1.27-alpine servant `deploy/web/`), tous avec healthchecks et `depends_on` sur l'état
  sain ; volume nommé `pgdata`. `POSTGRES_PASSWORD` est **obligatoire** et les ports sont
  publiés sur `127.0.0.1` uniquement.
- `deploy/.env.example` : identifiants Postgres et ports surchargeables.
- `deploy/web/index.html` : page placeholder en attendant le frontend (E0-11).

### E0-05 — Intégration continue

`.github/workflows/ci.yml` comporte trois jobs :

- `backend` : uv + Python 3.12, `sync --frozen`, ruff lint/format, pyright, import-linter,
  pytest avec service PostgreSQL 16, `pip-audit` ;
- `cli` : ruff, pyright, import-linter, pytest ;
- `docker` : `docker compose config` et `docker build` de l'image API.

Déclencheurs : `push` sur `main` et toute `pull_request`, avec annulation des exécutions
obsolètes (`concurrency`). Les jobs tournent sur le **runner self-hosted** du dépôt
(`runs-on: [self-hosted, linux, x64]`) car les runners hébergés GitHub sont bloqués par un
problème de facturation du compte. Le service PostgreSQL de la CI publie `55432` pour éviter
tout conflit avec la stack locale (`5432`).

Première exécution réelle et verte : run `43317081941` (backend, CLI et docker).

### E0-06 — Modèle de données v0

Livrable : [`docs/specs/schema-v0.md`](../specs/schema-v0.md) (diagrammes Mermaid, inventaire et
justification) et [`docs/specs/schema-v0.sql`](../specs/schema-v0.sql) (DDL exécutable), plus
[`schema-v0.verify.sql`](../specs/schema-v0.verify.sql) qui prouve les invariants.

- **29 tables** couvrant les entités critiques du plan §4 : identité/intégrations, projets et
  missions (squelette), Skills/blobs/versions, plans de travail, audit/exécution, outils,
  exigences, propositions et profil technique de projet.
- **16 triggers** garantissent en base l'immuabilité des versions, fichiers, blobs,
  instantanés et du journal d'audit, ainsi que les machines à états (versions, propositions) et
  le gel de `template_version_id`.
- **Contraintes structurelles** : `UNIQUE(skill_id, semver)`, FK composites
  `(version_id, skill_id)` pour l'épinglage/déploiement, `CHECK` de forme sur les exigences,
  hash et taille des blobs vérifiés, chemins de fichiers sûrs, exactement une cible par
  instance de plan.
- Les champs complets de `project`/`mission`, les rôles/compétences, les livrables et le
  knowledge sont **volontairement différés** (E3/E5/E9/E10), avec les points d'extension
  documentés.

### E0-07 — Décisions d'architecture (ADR 001 → 009)

Neuf ADR courtes ont été rédigées et acceptées, une par décision structurante du plan §3.4 :

| ADR | Décision |
|---|---|
| [001](../adr/001-monolithe-modulaire.md) | monolithe modulaire, 7 contrats `import-linter` |
| [002](../adr/002-blobs-postgres.md) | blobs dans PostgreSQL, adressage SHA-256, déduplication |
| [003](../adr/003-manifeste-empreinte.md) | manifeste JSON canonique, empreinte incluant `requirements` |
| [004](../adr/004-identite-principal.md) | `Principal`, jetons hachés, scopes, moindre privilège |
| [005](../adr/005-mcp-adaptateur.md) | MCP adaptateur mince, lecture d'abord |
| [006](../adr/006-brouillons-versions.md) | brouillons mutables / versions immuables |
| [007](../adr/007-plans-template-instance.md) | template → version → instance → overrides |
| [008](../adr/008-suppression-archivage.md) | archivage par défaut, suppression physique exceptionnelle |
| [009](../adr/009-concurrence-etag.md) | verrouillage optimiste `ETag`/`If-Match` |

Les ADR 010 à 012 restent à rédiger avec leurs epics (E14/E15) et sont listées comme telles
dans l'index.

## Décisions et écarts par rapport au plan

| Sujet | Décision / écart | Raison |
|---|---|---|
| Interpréteur local | Python **3.12.3** système (`/usr/bin/python3.12`), pas de fichier `.python-version` | un `.python-version = 3.12` entrait en conflit avec `pyenv` (3.11.9 seul installé) ; contournement documenté dans [Installation](../installation.md#dépannage) |
| Règle 3 | contrat `independence` sur les modules **métier** ; `shared` encadré par deux contrats dédiés (6 et 7) | `shared` est le noyau importé par tous ; l'indépendance stricte l'aurait bloqué (F-07 de l'audit) |
| Règle 5 | contrat porté par `cli/pyproject.toml` | le CLI est un package séparé ; import-linter opère par `root_package` |
| `readme` du package | `backend/README.md` plutôt que `../README.md` | hatchling exige un README dans le répertoire du projet |
| Dépendance `pip-audit` | ajoutée aux groupes `dev` backend et CLI | l'audit doit être reproductible en local et en CI |
| Couverture | `pytest-cov`, seuil global 80 % dès maintenant | applique le plan §10 ; le seuil domaine 90 % sera activé avec le premier code de domaine |
| Image Docker | `uv sync --frozen` + utilisateur non privilégié | build reproductible et surface réduite (F-08/F-04 de l'audit) |
| Frontend | seulement `README.md` + `src/.gitkeep` | squelette applicatif prévu en E0-11 |
| Tests | un seul test à ce stade (santé) | pas encore de logique métier ; la couverture montera avec E1+ |
| Statuts SQL | `text` + `CHECK` plutôt qu'`ENUM` | états encore provisoires, migrations plus simples |
| Table utilisateur | `app_user` | `user` est un mot réservé PostgreSQL |
| `skill.tags` | ajouté au schéma v0 | requis par la recherche E2-13 |

## Vérifications

Toutes exécutées localement le 2026-11-12.

```bash
cd backend
uv run ruff check .            # All checks passed!
uv run ruff format --check .   # 71 files already formatted
uv run pyright                 # 0 errors, 0 warnings
uv run lint-imports            # Contracts: 6 kept, 0 broken.
uv run pytest -q               # 1 passed, couverture 100 % (seuil 80 %)
uv run pip-audit               # No known vulnerabilities found
```

```bash
cd cli
uv run ruff check .            # All checks passed!
uv run pyright                 # 0 errors
uv run lint-imports            # Contracts: 1 kept, 0 broken.
uv run pytest -q               # 1 passed
```

Preuve que les contrats bloquent (E0-03) :

```text
# ajout temporaire de `import fastapi` dans workhub/skills/domain/
1. Le domaine ne dépend d'aucun framework technique
workhub.skills.domain is not allowed to import fastapi

# ajout temporaire de `import workhub.shared.domain` dans workhub/skills/application/
7. Les modules métier n'importent de shared que son API publique
workhub.skills is not allowed to import workhub.shared.domain

# ajout temporaire de `import workhub.skills` dans workhub/shared/
6. Le noyau shared ne dépend d'aucun module métier
workhub.shared is not allowed to import workhub.skills

# ajout temporaire de `import workhub` dans workhub_cli/
5. Le CLI ne dépend pas du package backend
workhub_cli is not allowed to import workhub
```

Modèle de données (critère E0-06) :

```bash
docker exec -i workhub-db-1 psql -U workhub -d workhub_schema_test -v ON_ERROR_STOP=1 \
  < docs/specs/schema-v0.sql
docker exec -i workhub-db-1 psql -U workhub -d workhub_schema_test -v ON_ERROR_STOP=1 \
  < docs/specs/schema-v0.verify.sql
# Vérifications du schéma v0 : OK  (29 tables, 12 scénarios d'invariants)
```

ADR (critère E0-07) :

```text
docs/adr/001-monolithe-modulaire.md      docs/adr/006-brouillons-versions.md
docs/adr/002-blobs-postgres.md           docs/adr/007-plans-template-instance.md
docs/adr/003-manifeste-empreinte.md      docs/adr/008-suppression-archivage.md
docs/adr/004-identite-principal.md       docs/adr/009-concurrence-etag.md
docs/adr/005-mcp-adaptateur.md           index à jour (9 acceptées, 3 à venir)
```

Stack Docker (critère E0-04) :

```text
workhub-db-1    Up (healthy)   127.0.0.1:5432->5432/tcp
workhub-api-1   Up (healthy)   127.0.0.1:8000->8000/tcp  (User=appuser)
workhub-web-1   Up (healthy)   127.0.0.1:8080->80/tcp

GET http://localhost:8000/api/v1/health
{"status":"ok","version":"0.1.0"}
```

## Limites connues

- **Runner self-hosted requis** : la CI s'exécute sur le runner du dépôt, car les runners
  hébergés GitHub sont indisponibles sur le compte (blocage de facturation). Le runner doit
  rester en ligne pour que les workflows démarrent.
- **Docker Desktop requis** : `docker compose up` suppose le démon actif. La validation a été
  faite avec Docker 29.9.2 (Docker Desktop 4.86.0).
- **API sans base** : Postgres tourne mais l'API ne s'y connecte pas encore (pas de SQLAlchemy
  ni d'Alembic) ; c'est l'objet de E0-09.
- **DDL non encore migré** : `schema-v0.sql` est la référence ; Alembic l'intégrera en E0-09.
- **Pas de squelette frontend** (E0-11) : seule une page statique placeholder est servie.

## Suites

1. **E0-08** — noyau `shared` (`Principal`, erreurs, horloge, ids, pagination).
2. **E0-09** — Alembic + testcontainers pour les tests d'intégration Postgres.
3. **E0-10** — logging structuré + `request_id` + middleware d'erreurs.
4. **E0-11** — squelette frontend (Vite/React/TS strict) appelant `/api/v1/health`.
