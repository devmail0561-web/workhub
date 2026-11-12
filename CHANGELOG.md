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
- **Documentation (E0)** : `docs/README.md`, `docs/installation.md`, `docs/developpement.md`,
  `docs/architecture.md`, journal `docs/implementation/E0-fondations.md` et modèle
  `docs/implementation/TEMPLATE.md` ; index des ADR.
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

### Notes

- CI définie mais pas encore exécutée sur GitHub (dépôt local sans remote).
- API non connectée à PostgreSQL à ce stade (prévu en E0-06/E0-09).
- Risques ouverts de l'audit (contrat d'indépendance vs noyau `shared`, couverture de tests,
  reproductibilité de l'image Docker, surface réseau de dev) : voir le rapport d'audit.
