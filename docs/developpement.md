# Développement

## Organisation du dépôt

```text
workhub-plan/
├── backend/          # API FastAPI + domaine (package `workhub`)
├── cli/              # package `workhub-cli` (HTTP uniquement)
├── frontend/         # interface React (squelette prévu en E0-11)
├── deploy/           # docker-compose, .env.example, web statique
├── docs/             # cette documentation (adr, specs, integrations, implementation)
├── tasks/            # plan de développement et backlog
└── .github/workflows # CI
```

## Commandes backend

Depuis `backend/` :

| Commande | Rôle | Attendu |
|---|---|---|
| `uv run pytest` | tests | tous verts |
| `uv run ruff check .` | lint | `All checks passed!` |
| `uv run ruff format --check .` | format | aucun fichier à reformater |
| `uv run pyright` | typage strict | `0 errors` |
| `uv run lint-imports` | règles d'architecture | tous les contrats `KEPT` |
| `uv run pip-audit` | vulnérabilités des dépendances | `No known vulnerabilities found` |

Le script `pre-commit` enchaîne ruff, pyright et import-linter à chaque commit.

## Commandes CLI

Depuis `cli/` : `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run pyright`, `uv run lint-imports`.

## Workflow d'une tâche

1. Lire la tâche correspondante dans le [backlog](../tasks/workhub-plan-developpement.md).
2. Implémenter **avec ses tests** (test de permission obligatoire pour tout endpoint).
3. Créer ou mettre à jour la page d'implémentation dans `docs/implementation/`.
4. Ajouter l'entrée correspondante dans `CHANGELOG.md` (section `Unreleased`).
5. Si la tâche prend une décision structurante, rédiger l'ADR correspondante.
6. Vérifier localement les six commandes backend ci-dessus.
7. Commiter (message `type(scope): description`).

## Définition de « terminé »

Reprise de la DoD du plan, complétée par l'exigence de documentation :

1. CI verte (lint, format, typage, `import-linter`, tests, `pip-audit`).
2. Tests passants + test de permission pour tout endpoint.
3. Migration Alembic réversible (dès E0-09).
4. Toute écriture d'intégration produit une ligne d'audit.
5. OpenAPI à jour + client TS régénéré (dès E0-11).
6. ADR mise à jour si une décision structurante est prise.
7. **Page `docs/implementation/` créée ou mise à jour**, avec commandes et résultats de
   vérification.
8. **Entrée ajoutée ou complétée dans `CHANGELOG.md`** (section `Unreleased`).

## Conventions de code

- Python 3.12, typage **strict** (pyright), `from __future__` non requis.
- Ruff : pycodestyle, pyflakes, isort, pyupgrade, bugbear, simplify, règles RUF ; largeur 100.
- Aucun import de framework dans `domain` ; aucune dépendance de `application` vers
  `infrastructure`/`interfaces` ; échanges inter-modules explicitement déclarés (voir
  [Architecture](architecture.md)).
- Pas de commentaire narratif : le code et la documentation suffisent.

## Intégration continue

`.github/workflows/ci.yml` définit trois jobs :

- **backend** : ruff (lint + format), pyright, import-linter, pytest avec un service
  PostgreSQL 16, puis `pip-audit`.
- **cli** : ruff, pyright, import-linter, pytest.
- **docker** : validation de la configuration Compose et construction de l'image API.

La CI se déclenche sur `push` vers `main` et sur toute `pull_request`. Les jobs s'exécutent
sur le **runner self-hosted** du dépôt (`runs-on: [self-hosted, linux, x64]`), les runners
hébergés GitHub étant indisponibles sur le compte (blocage de facturation). Le service
PostgreSQL du job backend publie le port `55432` pour ne pas entrer en conflit avec la stack
locale (`5432`).

Dernière exécution vérifiée : run `43317081941`, trois jobs verts (backend, CLI, docker).
