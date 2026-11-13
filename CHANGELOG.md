# Changelog

Tous les changements notables de WorkHub sont consignés dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le versionnement
sémantique ([SemVer](https://semver.org/lang/fr/)). Le projet est actuellement en
développement : la version `0.1.0` correspond à l'amorçage, sans release publiée.

## [Unreleased]

### Added

- **Monorepo (E0-01)** : arborescence `backend/`, `cli/`, `frontend/`, `deploy/`,
  `docs/`, `.github/workflows/` ; modules métier en `domain`/`application`/`infrastructure`
  avec une API publique `api.py` ; `README.md`, `CONTRIBUTING.md`, `LICENSE` (MIT),
  `.gitignore`.
- **Outillage Python (E0-02)** : projets `uv` backend (`workhub`) et CLI (`workhub-cli`) avec
  `ruff`, `pyright` strict, `pytest`/`pytest-asyncio`, `pip-audit`, `pre-commit` ; locks
  versionnés.
- **Sonde de santé (E0-02)** : `GET /api/v1/health` → `{"status":"ok","version":"0.1.0"}` et
  test associé.
- **Règles d'architecture (E0-03)** : contrats `import-linter` pour la pureté du domaine,
  l'isolation de la couche application, l'indépendance des modules, les interfaces et le CLI ;
  preuve qu'une violation échoue.
- **Stack locale (E0-04)** : `deploy/docker-compose.yml` (Postgres 16, API, web) avec
  healthchecks, `backend/Dockerfile`, `deploy/.env.example`, page web placeholder.
- **Intégration continue (E0-05)** : workflow GitHub Actions avec jobs `backend` (ruff, pyright,
  import-linter, pytest + service Postgres, pip-audit), `cli` et `docker`.
- **Noyau partagé (E0-08)** : `Principal` et scopes, hiérarchie d'erreurs métier, horloge
  injectable UTC, génération d'UUID, pagination bornée et enveloppe d'erreur REST unique ;
  42 tests, couverture 100 %.
- **ADR 001 → 009 (E0-07)** : monolithe modulaire, blobs SHA-256, manifeste/empreinte,
  identité et scopes, MCP adaptateur, brouillons/versions, plans, archivage et concurrence
  optimiste ; index dans [`docs/adr/`](docs/adr/README.md).
- **Modèle de données v0 (E0-06)** : [spécification](docs/specs/schema-v0.md) et DDL
  exécutable (29 tables, 16 triggers) couvrant identité, Skills, plans, audit, outils et
  propositions ; scripts de vérification des invariants.
- **Documentation (E0)** : `docs/README.md`, `docs/installation.md`, `docs/developpement.md`,
  `docs/architecture.md`, `docs/specs/schema-v0.md`, journal
  `docs/implementation/E0-fondations.md` et modèle `docs/implementation/TEMPLATE.md` ;
  ADR 001 → 009.
- **Audit initial** : rapport [`docs/audits/2026-11-12-audit-initial.md`](docs/audits/2026-11-12-audit-initial.md).
- **Changelog** : ce fichier.

### Changed

- La définition de « terminé » exige désormais la mise à jour de la page d'implémentation de
  l'epic concerné (`docs/implementation/`) et une entrée dans ce changelog.
- La configuration `pre-commit` est déplacée à la racine du dépôt avec un jeu de hooks par
  projet ; installation via `uv run --project backend pre-commit install`.
- Le README distingue Nginx (web local) et Caddy (TLS/production, à venir).

### Fixed

- `pre-commit` fonctionne réellement : les hooks ruff, pyright et import-linter s'exécutent dans
  le bon projet et le motif de fichiers couvre bien les sources.
- 21 fichiers sans newline final.
- `.import_linter_cache/` ajouté au `.gitignore`.
- L'image Docker de l'API ne tourne plus en root (utilisateur `appuser`, uid 10001).
- Les dépendances du CLI sont désormais auditées (`pip-audit`) en local et en CI.
- La CI s'exécute sur le runner **self-hosted** du dépôt (runners GitHub hébergés bloqués par
  facturation) et le port du service Postgres est passé à `55432` pour éviter les conflits.
- Actions GitHub mises à jour (`checkout@v7`, `setup-uv@v7`, runtime Node 24).
- Le contrat d'architecture 3 ne s'applique qu'aux modules métier ; deux contrats dédiés
  encadrent le noyau `shared` (règles 6 et 7).
- Couverture de tests mesurée et bloquante : `pytest-cov`, seuil global 80 %.
- Image Docker construite de façon reproductible avec `uv sync --frozen` (uv `0.13.0`).
- Ports de développement liés à `127.0.0.1` et `POSTGRES_PASSWORD` désormais obligatoire.

### Notes

- Première CI verte sur GitHub : run `43317081941` (backend, CLI, docker).
- API non connectée à PostgreSQL à ce stade (prévu en E0-06/E0-09).
- Risques ouverts de l'audit (contrat d'indépendance vs noyau `shared`, couverture de tests,
  reproductibilité de l'image Docker, surface réseau de dev) : voir le rapport d'audit.
