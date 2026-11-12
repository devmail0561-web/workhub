# Contribuer

## Prérequis

- **Python 3.12+** et [uv](https://docs.astral.sh/uv/)
- **Node.js 20+** (frontend)
- **Docker** + Docker Compose (stack locale)

## Mise en place

```bash
# Dépendances des deux projets Python
cd backend && uv sync
cd ../cli && uv sync

# Hooks Git (config à la racine du dépôt)
cd ..
uv run --project backend pre-commit install
```

## Commandes

Toutes les commandes backend s'exécutent depuis `backend/` :

| Commande | Rôle |
|---|---|
| `uv run pytest` | Tests |
| `uv run ruff check .` | Lint |
| `uv run ruff format --check .` | Format |
| `uv run pyright` | Typage strict |
| `uv run lint-imports` | Règles d'architecture (§3.3) |

## Règles d'architecture

Le dépôt applique un **monolithe modulaire** (Clean Architecture). Les règles sont vérifiées par `import-linter` et la CI bloque toute violation :

1. `domain` n'importe rien d'extérieur (ni SQLAlchemy, ni FastAPI).
2. `application` n'importe pas `infrastructure` ni `interfaces`.
3. Un module n'importe un autre module que via son API publique `workhub.<module>.api`.
4. `interfaces.rest`, `interfaces.mcp` et `cli` ne parlent qu'à `application`.
5. `cli` ne dépend pas du package backend : uniquement HTTP.

## Définition de « terminé »

1. CI verte (import-linter inclus).
2. Tests passants + test de permission pour tout endpoint.
3. Migration Alembic réversible.
4. Toute écriture d'intégration produit une ligne d'audit.
5. OpenAPI à jour + client TS régénéré.
6. ADR / documentation mis à jour.
7. Page `docs/implementation/E<epic>-<theme>.md` créée ou mise à jour, avec les commandes de
   vérification et leurs résultats (voir le [modèle](docs/implementation/TEMPLATE.md)).
8. Entrée ajoutée ou complétée dans [`CHANGELOG.md`](CHANGELOG.md) (section `Unreleased`).

## Documentation

L'implémentation est documentée de bout en bout dans [`docs/`](docs/README.md). Une tâche n'est
pas terminée tant que sa page d'implémentation n'est pas à jour. La documentation décrit l'état
réel du dépôt et les écarts éventuels par rapport au plan, jamais l'inverse.

## Commits

Messages concis, au format `type(scope): description` (ex. `feat(skills): publication SemVer`).
