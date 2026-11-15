# E0 — Fondations

| Champ | Valeur |
|---|---|
| Epic | `E0` |
| Jalon | M0 — Fondations |
| Tâches couvertes | `E0-01` → `E0-11` |
| Statut | E0 terminé (E0-01 → E0-11) |
| Dernière mise à jour | 2026-11-13 |
| ADR liées | [001 → 009](../adr/README.md) |
| Commits | `bb7f49b`, `0b82963` (fondations), `29f9a79` (E0-06/07), `17f6fd7` (E0-08), `6d50b68` (E0-09), `ad1a395` (E0-10), `4fe4b22` (E0-11) |

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
| `E0-08` | Noyau `shared` : `Principal`, erreurs, horloge, ids, pagination, enveloppe d'erreur API | ✅ | importé par les tests des deux premiers modules, 42 tests, couverture 100 % |
| `E0-09` | Alembic + base de test testcontainers + fixtures | ✅ | migration `upgrade`/`downgrade` vérifiée, 5 tests d'intégration sur vrai Postgres |
| `E0-10` | Logging structuré + `request_id` + middleware d'erreurs | ✅ | chaque requête produit une ligne JSON avec `request_id`, en-tête `X-Request-ID` |
| `E0-11` | Squelette frontend : Vite, TS strict, Tailwind, shadcn, TanStack Router/Query, client OpenAPI | ✅ | page `/` appelant `/api/v1/health` avec types générés, servie par Compose sur `:8080` |

## Ce qui a été implémenté

### E0-01 — Arborescence et documents racine

```text
workhub-plan/
├── .gitignore
├── README.md               # présentation, stack, démarrage, liens
├── CONTRIBUTING.md         # prérequis, commandes, règles, DoD, commits
├── LICENSE                 # MIT
├── backend/
│   ├── src/workhub/        # 11 modules métier + shared + interfaces/{rest,mcp}
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
- `deploy/docker-compose.yml` : `db` (Postgres 16-alpine), `migrate` (one-shot
  `alembic upgrade head`), `api` (build backend), `web` (build multi-étapes
  `frontend/Dockerfile` : Node/pnpm puis Nginx, proxy `/api`), avec healthchecks et
  `depends_on` sur l'état sain ; volume nommé `pgdata`. `POSTGRES_PASSWORD` est
  **obligatoire** et les ports sont publiés sur `127.0.0.1` uniquement.
- `deploy/.env.example` : identifiants Postgres, ports, `LOG_LEVEL` surchargeables.

### E0-05 — Intégration continue

`.github/workflows/ci.yml` comporte quatre jobs :

- `backend` : uv + Python 3.12, `sync --frozen`, ruff lint/format, pyright, import-linter,
  vérification du snapshot OpenAPI, pytest avec service PostgreSQL 16, `pip-audit` ;
- `cli` : ruff, pyright, import-linter, pytest, `pip-audit` ;
- `frontend` : pnpm + Node 20, `install --frozen-lockfile`, `pnpm audit`, `tsc`, vérification
  de dérive des types OpenAPI, Vitest, build Vite ;
- `docker` : `docker compose config` et `docker build` des images API et web.

Déclencheurs : `push` sur `main` et `pull_request` du dépôt, avec annulation des exécutions
obsolètes (`concurrency`). Les jobs tournent sur le **runner self-hosted** du dépôt
(`runs-on: [self-hosted, linux, x64]`) car les runners hébergés GitHub sont bloqués par un
problème de facturation du compte. Les PR issues de forks sont ignorées pour ne pas exécuter
de code externe sur l'hôte ; `permissions: contents: read`, `persist-credentials: false` et
les actions épinglées par SHA limitent la surface. Le service PostgreSQL de la CI publie
`55432` pour éviter tout conflit avec la stack locale (`5432`).

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

### E0-08 — Noyau partagé `shared`

Le noyau est le seul module conçu pour être importé par tous les autres. Il expose une API
publique stable via `workhub.shared.api` (règle 7) et ne dépend d'aucun module métier (règle 6).

| Élément | Fichier | Rôle |
|---|---|---|
| `Principal`, `PrincipalType` | `shared/domain/principal.py` | identité unifiée (humain, intégration, système) + scopes et jokers `*` / `skills:*` |
| `WorkHubError` et sous-classes | `shared/domain/errors.py` | codes stables : `validation_error`, `not_found`, `conflict`, `precondition_failed`, etc. |
| `Clock`, `SystemClock` | `shared/domain/clock.py` | horloge injectable, toujours `timezone-aware` en UTC |
| `new_id`, `IdFactory` | `shared/domain/ids.py` | UUID v4 générés en application |
| `Page`, `PageRequest`, `paginate` | `shared/domain/pagination.py` | pagination bornée (`limit` 1–100, `offset ≥ 0`), navigation |
| `install_error_handlers` | `interfaces/rest/errors.py` | enveloppe JSON unique des erreurs |

Enveloppe d'erreur REST :

```json
{"error": {"code": "not_found", "message": "Skill absente", "details": {"slug": "inconnue"}, "request_id": null}}
```

| Code | Statut HTTP |
|---|---|
| `validation_error` | 422 |
| `authentication_required` | 401 |
| `permission_denied` | 403 |
| `not_found` | 404 |
| `conflict` | 409 |
| `precondition_failed` | 412 |
| `rate_limited` | 429 |
| `internal_error` | 500 |

Les erreurs de validation FastAPI (`RequestValidationError`) sont converties dans la même
enveloppe. Le `request_id` est déjà présent dans le contrat et sera alimenté par le middleware
de E0-10.

Le contrat 4 autorise explicitement le noyau via `ignore_imports` (`shared.api` réexporte des
types de `shared.domain`) tout en continuant d'interdire tout accès direct aux internals.

### E0-09 — Alembic, PostgreSQL réel et fixtures

- **SQLAlchemy 2 async** (`postgresql+psycopg`, psycopg 3) et **Alembic** ajoutés aux
  dépendances ; `backend/alembic.ini` et `backend/migrations/` créés.
- **Migration initiale `0001_schema_v0`** : reprend le DDL v0 (copie vendue dans
  `migrations/sql/`) et l'exécute instruction par instruction ; un test garantit que la copie
  reste identique à [`docs/specs/schema-v0.sql`](../specs/schema-v0.sql).
- **`migrations/sql_split.py`** : découpage SQL conscient des chaînes, commentaires et blocs
  `$$`, car `psycopg` n'accepte pas plusieurs instructions par `execute`.
- **Downgrade** : supprime les 29 tables puis les fonctions, en laissant `alembic_version`
  cohérent (`base`).
- **Infrastructure partagée** : `shared/infrastructure/database.py` expose une `Base`
  déclarative, `create_engine()` et `create_session_factory()` (moteur asynchrone).
- **Tests d'intégration** : fixture `testcontainers` (`postgres:16-alpine`), migration appliquée
  via Alembic, session async. Surcharge possible par `WORKHUB_TEST_DATABASE_URL`. Les tests
  vérifient la version de migration, l'existence des tables, les 16 triggers, le `CHECK` de
  hash des blobs et l'append-only de `audit_log`.

Commandes :

```bash
# appliquer les migrations (DATABASE_URL prioritaire sur alembic.ini)
DATABASE_URL=postgresql+psycopg://workhub:change-me@localhost:5432/workhub \
  uv run alembic upgrade head

# tests d'intégration (Docker requis pour testcontainers)
uv run pytest -m integration
```

### E0-10 — Logging JSON, `request_id` et middleware

- **structlog 26** configuré en JSON (`interfaces/rest/logging.py`) : niveau via `LOG_LEVEL`
  (défaut `INFO`), horodatage UTC, niveau, exception et contextvars fusionnés.
- **`RequestContextMiddleware`** (`interfaces/rest/middleware.py`) :
  - reprend `X-Request-ID` s'il respecte `[A-Za-z0-9._-]{1,128}`, sinon génère un UUID v4 ;
  - expose l'identifiant dans `request.state.request_id`, les contextvars et l'en-tête de
    réponse `X-Request-ID` ;
  - journalise une ligne `http.request` avec `method`, `path`, `status_code`, `duration_ms`,
    `request_id` (sans en-tête ni corps sensible) ;
  - journalise les exceptions non gérées en niveau `error` avec la trace, puis les propage.
- **Enveloppe d'erreur** : `request_id` renseigné dans toutes les réponses d'erreur (métier,
  validation FastAPI, erreurs HTTP 404/405 et exception inattendue), y compris `422` ; les
  valeurs d'entrée ne sont pas renvoyées dans les détails de validation.
- `LOG_LEVEL` est transmis au conteneur API par Compose (`deploy/.env`).
- L'access log Uvicorn est désactivé (`--no-access-log`) pour éviter une ligne non JSON en
  doublon ; le middleware production la ligne `http.request`.

Exemple de ligne (une par requête) :

```json
{"event":"http.request","request_id":"req-42","method":"GET","path":"/api/v1/health","status_code":200,"duration_ms":1.23,"level":"info","timestamp":"2026-11-13T16:00:00.000000Z"}
```

### E0-11 — Squelette frontend

- **Vite 8 + React 19 + TypeScript 5.9 strict** (`strict`, `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes`, `noUnusedLocals/Parameters`), alias `@/` vers `src/`.
- **Tailwind CSS 4** via `@tailwindcss/vite` et **shadcn/ui** initialisé (`components.json`,
  `cn()`, composant `Button` basé sur Radix Slot et CVA).
- **TanStack Router** : route typée `/` et layout racine ; **TanStack Query** : clé `health`
  et bouton de rafraîchissement.
- **Client OpenAPI généré** : `frontend/openapi.json` (instantané du contrat FastAPI) est
  converti par `openapi-typescript` en `src/api/schema.d.ts` ; `openapi-fetch` consomme ces
  types, aucun type de réponse n'est écrit à la main.
- **Même origine** : en développement, le proxy Vite relaie `/api` vers `localhost:8000` ; en
  production, Nginx relaie `/api/` vers le service `api`. Pas de CORS à ouvrir.
- **Image web multi-étapes** (`frontend/Dockerfile`) : build Node/pnpm puis Nginx ; Compose
  construit l'image et sert l'application sur `127.0.0.1:8080`.
- **Tests** : Vitest + Testing Library (3 tests : client typé, erreur HTTP, rendu de l'état) ;
  `tsc --noEmit` et `vite build` passent. Playwright et Monaco restent pour les écrans métier.
- **Gestionnaire** : pnpm 10 avec `pnpm-lock.yaml` versionné ; `npm` 10.8 échouait sur la
  résolution des pairs de cet ensemble.

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
| Frontend | Vite 8 + React 19 + TypeScript strict, Tailwind 4, shadcn/ui, TanStack Router/Query, client OpenAPI généré | squelette E0-11 ; Playwright/Monaco avec les écrans métier |
| Gestionnaire frontend | **pnpm 10** (lockfile versionné) | `npm install` échouait sur cet ensemble de dépendances |
| Origine API | proxy Vite/Nginx, pas de CORS | même origine en dev et en production |
| Tests | 70 tests, couverture 100 % | noyau, schéma, erreurs et frontend couverts ; les scénarios métier arrivent en E1+ |
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

Noyau partagé et enveloppe d'erreur (critère E0-08) :

```bash
cd backend
uv run ruff check .          # All checks passed!
uv run ruff format --check . # 84 files already formatted
uv run pyright               # 0 errors, 0 warnings
uv run lint-imports          # Contracts: 6 kept, 0 broken.
uv run pytest -q             # 42 passed, couverture 100 %
```

Migrations et tests d'intégration (critère E0-09) :

```bash
cd backend
uv run pytest -q                    # 55 passed, couverture 100 %
DATABASE_URL=postgresql+psycopg://workhub:change-me@localhost:5432/workhub_alembic_test \
  uv run alembic upgrade head       # 0001_schema_v0 (head)
DATABASE_URL=postgresql+psycopg://workhub:change-me@localhost:5432/workhub_alembic_test \
  uv run alembic downgrade base     # retour à l'état vide
```

Après `upgrade` : 30 tables (`29` métier + `alembic_version`) et 16 triggers ; après
`downgrade base` : uniquement `alembic_version`.

Logs et `request_id` (critère E0-10) :

```bash
cd backend
uv run pytest -q             # 70 passed, couverture 100 % (correctifs post-audit inclus)
docker logs workhub-api-1    # une ligne JSON par requête, avec request_id
```

Squelette frontend (critère E0-11) :

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run typecheck           # tsc --noEmit, aucune erreur
pnpm run test                # 3 tests Vitest
pnpm run build               # build Vite dans dist/
curl -fsS http://localhost:8080/api/v1/health
# {"status":"ok","version":"0.1.0"}
```

Stack Docker (critère E0-04) :

```text
workhub-db-1    Up (healthy)   127.0.0.1:5432->5432/tcp
workhub-api-1   Up (healthy)   127.0.0.1:8000->8000/tcp  (User=appuser)
workhub-web-1   Up (healthy)   127.0.0.1:8080->80/tcp

GET http://localhost:8000/api/v1/health
{"status":"ok","version":"0.1.0"}
GET http://localhost:8080/api/v1/health   (via Nginx)
{"status":"ok","version":"0.1.0"}
```

## Correctifs post-audit (2026-11-15)

Après l'audit complet du 2026-11-13, les correctifs suivants ont été appliqués sans changer le
périmètre fonctionnel de E0 :

- **Erreurs HTTP** : handlers pour `StarletteHTTPException` et `Exception` ; 404, 405, 422 et
  500 utilisent désormais l'enveloppe `{"error": ...}`, avec `X-Request-ID` et `request_id`.
  Les détails de validation n'exposent plus `input`.
- **Santé** : `HealthResponse` typé (`status: Literal["ok"]`, `version`), `response_model`
  FastAPI et régénération de `frontend/openapi.json` / `src/api/schema.d.ts`.
- **Logging** : `LOG_LEVEL` inconnu retombe sur `INFO` avec un avertissement au lieu de faire
  échouer l'import.
- **Pagination** : `paginate()` documente et teste une séquence complète ; l'offset n'est
  appliqué qu'une fois, même avec `total`.
- **Migrations** : `alembic.ini` et `migrations/` sont inclus dans l'image API ; Compose
  exécute le service one-shot `migrate` avant l'API.
- **Healthchecks** : API et web utilisent `127.0.0.1` (le `localhost` IPv6 de BusyBox causait
  un faux `unhealthy` du conteneur web).
- **CI** : `permissions: contents: read`, `persist-credentials: false`, actions épinglées par
  SHA, PR de forks ignorées sur le runner self-hosted, contrôle du snapshot OpenAPI, dérive
  des types TypeScript et `pnpm audit`.

Commandes exécutées le 2026-11-15 :

```bash
cd backend
uv run ruff format .          # 1 fichier reformatté
uv run ruff check .           # All checks passed!
uv run pyright                # 0 errors, 0 warnings
uv run lint-imports           # Contracts: 6 kept, 0 broken.
uv run pytest -q              # 70 passed, couverture 100 %

cd ../frontend
pnpm run typecheck            # aucune erreur
pnpm run test                 # 3 tests Vitest
pnpm run build                # build Vite réussi
pnpm audit --prod             # No known vulnerabilities found
```

Stack Compose vérifiée après reconstruction :

```text
workhub-api-1      Up (healthy)
workhub-db-1       Up (healthy)
workhub-migrate-1  Exited (0)
workhub-web-1      Up (healthy)

GET /api/v1/health         -> 200 {"status":"ok","version":"0.1.0"}
GET /unknown               -> 404 enveloppe JSON + X-Request-ID
POST /api/v1/health        -> 405 enveloppe JSON + Allow: GET
tables PostgreSQL          -> 30 (29 métier + alembic_version)
```

Restent ouverts, hors de ce lot : index des FK, triggers `TRUNCATE`/séparation des rôles DB,
tests CI du script `schema-v0.verify.sql` et du downgrade, scan d'images et durcissement
Nginx/frontend (voir le rapport d'audit).

## Limites connues

- **Runner self-hosted requis** : la CI s'exécute sur le runner du dépôt, car les runners
  hébergés GitHub sont indisponibles sur le compte (blocage de facturation). Le runner doit
  rester en ligne pour que les workflows démarrent.
- **Docker Desktop requis** : `docker compose up` suppose le démon actif. La validation a été
  faite avec Docker 29.9.2 (Docker Desktop 4.86.0).
- **API sans persistance au runtime** : le moteur et les migrations existent, mais aucun cas
  d'usage ne lit/écrit encore en base ; c'est l'objet de E1/E2.
- **Contrat 7 et infrastructure** : `shared/infrastructure` n'est pas encore importé par des
  modèles métier ; l'exception ciblée du contrat sera ajoutée au premier modèle (E1).
- **Pas d'OpenTelemetry** : traces et métriques restent optionnelles (plan §2.1) ; seuls les
  logs JSON et le `request_id` sont en place.
- **Frontend minimal** : une seule route et la sonde de santé ; écrans métier, Playwright et
  Monaco arrivent avec E12/E2+.
- **Client OpenAPI instantané** : `frontend/openapi.json` est versionné ; il doit être
  régénéré à chaque évolution du contrat (procédure dans [Développement](../developpement.md)).
- **Noyau sans persistance** : `shared` fournit les primitives ; la résolution réelle du
  `Principal` et le chargement des scopes arrivent en E1-05.

## Suites

1. **E1-01** — entité `User`, hash argon2id et amorçage du premier administrateur par le CLI.
2. **E1-02** — sessions JWT d'accès court + refresh cookie `HttpOnly`, rotation et logout.
