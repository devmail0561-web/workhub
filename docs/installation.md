# Installation et démarrage

## Prérequis

| Outil | Version | Usage |
|---|---|---|
| Python | **3.12+** | backend, CLI |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.8 (testé avec 0.13.0) | gestion des dépendances Python |
| Node.js | 20.19+ | frontend |
| pnpm | 10+ | dépendances frontend |
| Docker Engine + Compose v2 | testé avec Docker 29.9.2 | stack locale (Postgres, API, web) |
| Git | 2.43+ | versionnement |

> Le projet cible Python **3.12**. Sur une machine où `python3` pointe vers une version plus
> ancienne et où `uv` est fourni par un gestionnaire de versions, il peut être nécessaire de
> forcer l'interpréteur lors du premier `uv sync` : cf. [Dépannage](#dépannage).

## Installation du backend

```bash
cd backend
uv sync                # crée .venv et installe les dépendances (profil dev inclus)

# hooks Git : config à la racine du dépôt, exécutés depuis le venv backend
cd ..
uv run --project backend pre-commit install
```

`uv sync` installe le package `workhub` en mode éditable ainsi que les outils de
développement déclarés dans le groupe `dev` de `backend/pyproject.toml` : `ruff`, `pyright`,
`pytest`, `pytest-asyncio`, `httpx`, `import-linter`, `pip-audit`, `pre-commit`.

## Installation du CLI

```bash
cd cli
uv sync
```

Le CLI est un package **indépendant** (`workhub-cli`) : il ne dépend pas du package backend et
ne parle à WorkHub que par HTTP. Cette contrainte est vérifiée par `import-linter` (contrat 5).

## Lancer la stack locale

```bash
cp deploy/.env.example deploy/.env     # POSTGRES_PASSWORD est obligatoire
docker compose -f deploy/docker-compose.yml up -d --build
```

`POSTGRES_PASSWORD` n'a pas de valeur par défaut : Compose refuse de démarrer tant qu'il n'est
pas défini dans `deploy/.env`. Les ports sont publiés sur `127.0.0.1` uniquement (accès local).

Services démarrés :

| Service | URL | Rôle |
|---|---|---|
| API | http://localhost:8000 | FastAPI |
| API — santé | http://localhost:8000/api/v1/health | sonde utilisée par Docker/CI |
| Web | http://localhost:8080 | SPA React servie par Nginx, proxy `/api` |
| PostgreSQL | `localhost:5432` | base de données |

Le service `migrate` n'est pas un serveur : il se termine normalement (`Exited (0)`) après avoir
appliqué le schéma.

Vérification :

```bash
docker compose -f deploy/docker-compose.yml ps
curl -fsS http://localhost:8000/api/v1/health
# {"status":"ok","version":"0.1.0"}
```

Le service web est construit depuis `frontend/` (Node + pnpm puis Nginx) ; la page `/` appelle
la sonde via `http://localhost:8080/api/v1/health`.

## Installation du frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev          # http://localhost:5173, proxy /api vers :8000
```

Compose applique les migrations automatiquement : le service one-shot `migrate` exécute
`alembic upgrade head` après le healthcheck de PostgreSQL, puis l'API démarre lorsque la
migration a réussi. Pour un backend lancé hors Compose :

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://workhub:<mot-de-passe>@localhost:5432/workhub"
uv run alembic upgrade head
```

Arrêt :

```bash
docker compose -f deploy/docker-compose.yml down       # conserve le volume Postgres
docker compose -f deploy/docker-compose.yml down -v    # supprime aussi les données
```

Les ports sont surchargeables dans `deploy/.env` (`API_PORT`, `WEB_PORT`, `POSTGRES_PORT`).
Le niveau de log se règle avec `LOG_LEVEL` (`INFO` par défaut).

## Dépannage

### `uv sync` échoue avec un message `pyenv: version '3.12' is not installed`

Certains environnements combinent `pyenv` et `uv`, et un fichier `.python-version` local peut
entrer en conflit. Forcer l'interpréteur système :

```bash
cd backend
UV_PYTHON=/usr/bin/python3.12 uv sync
```

### `docker info` répond « daemon unavailable »

Le client Docker est installé mais le démon ne tourne pas. Démarrer Docker Desktop (ou le
service Docker) puis relancer `docker compose`.

### `pip-audit` signale `workhub` comme non auditable

C'est normal : le package local n'existe pas sur PyPI. `pip-audit` l'ignore et audite le reste
(`No known vulnerabilities found`).
