# E0 — Fondations

| Champ | Valeur |
|---|---|
| Epic | `E0` |
| Jalon | M0 — Fondations |
| Tâches couvertes | `E0-01` → `E0-05` |
| Statut | E0-01 → E0-05 terminés ; E0-06 → E0-11 à faire |
| Dernière mise à jour | 2026-11-12 |
| ADR liées | aucune encore (ADR 001 à rédiger en E0-07) |
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
| `E0-05` | CI GitHub Actions : lint, types, tests, import-linter, pip-audit, build | ✅ | workflow défini et validé localement |

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
  `pytest-asyncio`, `ruff` ;
- ruff : cibles `E,W,F,I,UP,B,SIM,RUF`, largeur 100, `known-first-party = ["workhub"]` ;
- pyright : `typeCheckingMode = "strict"`, Python 3.12, `.venv` local ;
- pytest : `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope
  = "function"`, `pythonpath = ["src"]`.

**CLI** (`cli/pyproject.toml`) : package séparé `workhub-cli` (`typer`, `httpx`), avec sa propre
configuration ruff/pyright/pytest et un contrat import-linter (règle 5).

**Sonde de santé** : `backend/src/workhub/interfaces/rest/app.py` expose
`GET /api/v1/health` → `{"status":"ok","version":"0.1.0"}`. Elle sert de healthcheck Docker et
de premier test de bout en bout (`backend/tests/unit/test_health.py`, client `httpx`
`ASGITransport` pour rester compatible avec pyright strict).

**pre-commit** (`backend/.pre-commit-config.yaml`) : `ruff`, `ruff-format`, hooks de base
(trailing whitespace, EOF, YAML, TOML), puis `pyright` et `lint-imports` en hooks locaux.

Les fichiers `uv.lock` de `backend/` et `cli/` sont versionnés pour des builds reproductibles.

### E0-03 — Règles d'architecture

Quatre contrats `import-linter` dans `backend/pyproject.toml`, un cinquième dans
`cli/pyproject.toml` (voir le détail des règles dans [Architecture](../architecture.md#règles-de-dépendance-vérifiées-par-import-linter)) :

1. domaine sans framework ni dépendance vers les couches hautes ;
2. `application` sans `infrastructure`/`interfaces` ;
3. indépendance des modules (couplage explicite uniquement) ;
4. `interfaces` ne parlent qu'à `application` ;
5. le CLI ne dépend pas du package backend.

La configuration active `include_external_packages = true` pour pouvoir interdire des modules
externes (`fastapi`, `sqlalchemy`, `workhub`).

### E0-04 — Stack Docker

- `backend/Dockerfile` : image `python:3.12-slim`, installation du package, `uvicorn` sur le
  port 8000.
- `backend/.dockerignore` : exclut `.venv`, caches et tests.
- `deploy/docker-compose.yml` : `db` (Postgres 16-alpine), `api` (build backend), `web`
  (Nginx 1.27-alpine servant `deploy/web/`), tous avec healthchecks et `depends_on` sur l'état
  sain ; volume nommé `pgdata`.
- `deploy/.env.example` : identifiants Postgres et ports surchargeables.
- `deploy/web/index.html` : page placeholder en attendant le frontend (E0-11).

### E0-05 — Intégration continue

`.github/workflows/ci.yml` comporte trois jobs :

- `backend` : uv + Python 3.12, `sync --frozen`, ruff lint/format, pyright, import-linter,
  pytest avec service PostgreSQL 16, `pip-audit` ;
- `cli` : ruff, pyright, import-linter, pytest ;
- `docker` : `docker compose config` et `docker build` de l'image API.

Déclencheurs : `push` sur `main` et toute `pull_request`, avec annulation des exécutions
obsolètes (`concurrency`).

## Décisions et écarts par rapport au plan

| Sujet | Décision / écart | Raison |
|---|---|---|
| Interpréteur local | Python **3.12.3** système (`/usr/bin/python3.12`), pas de fichier `.python-version` | un `.python-version = 3.12` entrait en conflit avec `pyenv` (3.11.9 seul installé) ; contournement documenté dans [Installation](../installation.md#dépannage) |
| Règle 3 | contrat `independence` (plus strict que « via `api.py` ») | import-linter n'exprime pas « uniquement via `api` » ; tout couplage futur sera whitelisté explicitement |
| Règle 5 | contrat porté par `cli/pyproject.toml` | le CLI est un package séparé ; import-linter opère par `root_package` |
| `readme` du package | `backend/README.md` plutôt que `../README.md` | hatchling exige un README dans le répertoire du projet |
| Dépendance `pip-audit` | ajoutée au groupe `dev` backend | l'audit doit être reproductible en local et en CI |
| Frontend | seulement `README.md` + `src/.gitkeep` | squelette applicatif prévu en E0-11 |
| Tests | un seul test à ce stade (santé) | pas encore de logique métier ; la couverture montera avec E1+ |

## Vérifications

Toutes exécutées localement le 2026-11-12.

```bash
cd backend
uv run ruff check .            # All checks passed!
uv run ruff format --check .   # 71 files already formatted
uv run pyright                 # 0 errors, 0 warnings
uv run lint-imports            # Contracts: 4 kept, 0 broken.
uv run pytest -q               # 1 passed
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

# ajout temporaire de `import workhub` dans workhub_cli/
5. Le CLI ne dépend pas du package backend
workhub_cli is not allowed to import workhub
```

Stack Docker (critère E0-04) :

```text
workhub-db-1    Up (healthy)
workhub-api-1   Up (healthy)
workhub-web-1   Up (healthy)

GET http://localhost:8000/api/v1/health
{"status":"ok","version":"0.1.0"}
```

## Limites connues

- **CI non exécutée sur GitHub** : le dépôt est local, sans remote. Le workflow est défini et
  ses étapes sont reproduites localement, mais le déclenchement réel reste à valider après
  création du dépôt distant.
- **Docker Desktop requis** : `docker compose up` suppose le démon actif. La validation a été
  faite avec Docker 29.9.2 (Docker Desktop 4.86.0).
- **API sans base** : Postgres tourne mais l'API ne s'y connecte pas encore (pas de SQLAlchemy
  ni d'Alembic) ; c'est l'objet de E0-06/E0-09.
- **Pas de squelette frontend** (E0-11) : seule une page statique placeholder est servie.
- **Pas encore d'ADR** : les 12 décisions structurantes sont listées dans
  [`docs/adr/README.md`](../adr/README.md) mais restent à rédiger (E0-07).

## Suites

1. **E0-06** — modèle de données v0 (diagramme + DDL des tables MVP).
2. **E0-07** — ADR 001 → 009 (au minimum 002, 003 et 006 en priorité, cf. plan §13-3).
3. **E0-08** — noyau `shared` (`Principal`, erreurs, horloge, ids, pagination).
4. **E0-09** — Alembic + testcontainers pour les tests d'intégration Postgres.
5. **E0-10** — logging structuré + `request_id` + middleware d'erreurs.
6. **E0-11** — squelette frontend (Vite/React/TS strict) appelant `/api/v1/health`.
7. Créer le dépôt distant pour activer réellement la CI.