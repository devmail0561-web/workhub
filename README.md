# WorkHub

Référentiel central de **compétences, projets, plans de travail et Skills**, consommé par des agents externes (Claude Code, OpenCode, Codex) via le protocole **MCP**.

L'application ne contient **aucun LLM** : elle expose des données et des cas d'usage ; l'agent décide de ce qu'il installe et exécute dans son propre projet.

## Stack

| Domaine | Technologies |
|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x async, Alembic, PostgreSQL 16 |
| MCP | SDK MCP officiel Python (FastMCP), transports stdio + Streamable HTTP |
| CLI | Typer + httpx (`workhub-cli`) |
| Frontend | Vite, React, TypeScript strict, Tailwind, shadcn/ui, TanStack Router/Query, Monaco |
| Qualité | uv, ruff, pyright strict, pytest, import-linter, pre-commit |
| Infra | Docker Compose, Caddy, GitHub Actions |

## Structure du dépôt

```text
.
├── backend/            # API FastAPI + domaine (monolithe modulaire)
│   ├── src/workhub/    # modules métier + interfaces REST/MCP
│   └── tests/          # unit / integration / contract / security
├── cli/                # client en ligne de commande (HTTP uniquement)
├── frontend/           # interface web React
├── deploy/             # docker-compose, Caddyfile, sauvegardes
├── docs/               # adr / specs / integrations
└── .github/workflows/  # CI
```

## Démarrage rapide

```bash
# Backend (outils de développement installés via uv)
cd backend
uv sync
uv run pytest

# Stack locale
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml up
```

## Documentation

- Plan de développement et backlog : [`tasks/workhub-plan-developpement.md`](tasks/workhub-plan-developpement.md)
- Cahier des charges : `docs/plans-de-travail.pdf`
- Décisions d'architecture : [`docs/adr/`](docs/adr/)

## Licence

MIT — voir [`LICENSE`](LICENSE).