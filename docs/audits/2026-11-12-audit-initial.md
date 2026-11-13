# Audit initial de l'implémentation — 2026-11-12

| Champ | Valeur |
|---|---|
| Date | 2026-11-12 |
| Périmètre | dépôt complet, commit `b4bcf35` + corrections de l'audit |
| Référentiels | [plan de développement](../../tasks/workhub-plan-developpement.md), [architecture](../architecture.md), DoD |
| Verdict | **Fondations saines et fonctionnelles** ; constats élevés et moyens corrigés (sauf F-12), 7 points mineurs restants |

## Résumé exécutif

L'implémentation E0-01 → E0-05 est conforme au plan et reproductible : lint, format, typage strict
et règles d'architecture passent, les tests passent, la stack Docker est saine et tourne
désormais avec un utilisateur non privilégié. L'audit a toutefois révélé que **la configuration
`pre-commit` ne fonctionnait pas** (emplacement, répertoire d'exécution, motifs de fichiers) :
le garde-fou local annoncé dans la documentation était inopérant. C'est le défaut le plus
important, corrigé pendant l'audit et vérifié.

Les points restants sont des **choix de durcissement ou de gouvernance** à traiter avant les
jalons concernés : couverture de tests, reproductibilité de l'image, surface réseau de
développement, et interprétation du contrat d'indépendance des modules.

## Méthode

Inspection manuelle des fichiers suivis, puis exécution de tous les contrôles :

```bash
# backend et cli
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run lint-imports
uv run pytest
uv run pip-audit
uv lock --check

# pré-commit (racine)
uv run --project backend pre-commit run --all-files

# docker
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example up -d --build
docker inspect workhub-api-1 --format 'User={{.Config.User}}'

# hygiène du dépôt
git ls-files              # inventaire
git grep -nE "(password|secret|token|api[_-]?key)\s*[:=]"   # secrets
# vérification des liens relatifs des fichiers markdown
```

## Constats par sévérité

### Élevé — corrigés

| ID | Constat | Preuve | Correction |
|---|---|---|---|
| F-01 | `pre-commit` inopérant : config dans `backend/.pre-commit-config.yaml`, hooks exécutés à la racine du dépôt, `uv run pyright` sans projet résoluble, `files: ^src/` ne correspondait jamais à `backend/src/`, CLI non couvert | `pyright` échouait sur `cli/tests/test_package.py` ; `import-linter` affichait `(no files to check) Skipped` | config déplacée à la racine, un hook par projet via `bash -c 'cd <projet> && uv run …'` ; les 13 hooks passent |
| F-02 | 21 fichiers suivis sans newline final | `end-of-file-fixer` a modifié 21 fichiers au premier passage | corrigé par le hook puis committé |

### Moyen — corrigés

| ID | Constat | Correction |
|---|---|---|
| F-03 | `.import_linter_cache/` ignoré uniquement par une config Git globale, pas par le `.gitignore` du dépôt | ajouté au `.gitignore` |
| F-04 | l'image API tournait en **root** (`User=` vide) | ajout d'un utilisateur `appuser` (uid 10001) ; image reconstruite, `User=appuser`, conteneur `healthy` |
| F-05 | les dépendances du CLI n'étaient pas auditées (`pip-audit` absent du groupe dev et du job CI `cli`) | `pip-audit` ajouté à `cli/pyproject.toml` et au job `cli` de la CI |
| F-06 | le README annonçait **Caddy** alors que le web local utilise **Nginx** | README corrigé : Nginx local, Caddy pour TLS/production à venir |
| F-11 | CI jamais exécutée (pas de remote ; runners GitHub hébergés bloqués par facturation) | dépôt `devmail0561-web/workhub` poussé ; workflows basculés sur le runner self-hosted ; run `43317081941` vert (backend, CLI, docker) |
| F-07 | contrat `independence` interdisant aussi l'import du noyau `shared` | contrat 3 limité aux modules métier ; contrats 6 et 7 encadrent `shared` (API publique uniquement) ; violations testées |
| F-08 | image Docker construite avec `pip install .` (ignore `uv.lock`) | Dockerfile basé sur `uv sync --frozen --no-dev --no-editable` ; build vérifié |
| F-09 | aucune couverture de tests | `pytest-cov` + seuil global bloquant 80 % ; `pytest` mesure 100 % à ce stade |
| F-10 | ports sur `0.0.0.0` et mot de passe Postgres par défaut | ports liés à `127.0.0.1` ; `POSTGRES_PASSWORD` obligatoire (Compose refuse de démarrer sans) |

### Moyen — ouverts (recommandations)

| ID | Risque | Impact | Recommandation |
|---|---|---|---|
| F-12 | Image de base non épinglée par digest, pas de scan d'image ni de SBOM | surface d'approvisionnement non maîtrisée | épingler `python:3.12-slim@sha256:…`, ajouter Trivy/Grype en CI |

### Faible — ouverts

| ID | Constat | Note |
|---|---|---|
| F-13 | version `0.1.0` dupliquée dans deux `pyproject.toml` et `workhub/__init__.py` | risque de dérive ; envisager une version dynamique depuis les métadonnées |
| F-14 | `.dockerignore` utilise `__pycache__` (non récursif) | résolu : `**/__pycache__`, caches de test et couverture exclus |
| F-15 | pas de `HEALTHCHECK` dans le Dockerfile | couvert par Compose, acceptable pour l'instant |
| F-16 | pas de `SECURITY.md`, `CODEOWNERS`, template de PR, `.editorconfig` | à ajouter avant collaboration élargie |
| F-17 | versions d'actions GitHub (`checkout@v4`, `setup-uv@v5`) | résolu : `checkout@v7` et `setup-uv@v7` (Node 24) |
| F-18 | pas encore de tests de contrat ni de permissions | normal à ce stade (aucun endpoint protégé) |
| F-19 | frontend absent (seulement README + placeholder) | résolu en E0-11 : Vite/React/TS strict, client OpenAPI, tests et proxy même origine |
| F-20 | pas d'ADR rédigées | prévu en E0-07 ; décisions structurantes déjà listées |

## Conformité au plan (E0)

| Tâche | Critère de fin | État |
|---|---|---|
| E0-01 | arborescence §3.2 en place | ✅ conforme |
| E0-02 | `uv run pytest` et lint passent | ✅ conforme |
| E0-03 | violation volontaire détectée | ✅ conforme (4 contrats backend + 1 CLI, vérifiés par violation temporaire) |
| E0-04 | `docker compose up` sain | ✅ conforme (db/api/web `healthy`) |
| E0-05 | PR bloquée si rouge | ✅ workflow vert sur le runner self-hosted (run `43317081941`) |

Éléments du plan non requis avant E0-06 : schéma de données, ADR, noyau `shared`, Alembic,
logging, frontend.

## Contrôles après correction

| Contrôle | Backend | CLI |
|---|---|---|
| `ruff check` | `All checks passed!` | `All checks passed!` |
| `ruff format --check` | 71 fichiers déjà formatés | 3 fichiers déjà formatés |
| `pyright` (strict) | 0 erreur | 0 erreur |
| `lint-imports` | 6 contrats `KEPT` | 1 contrat `KEPT` |
| `pytest` | 1 test passé, couverture 100 % (seuil 80 %) | 1 test passé |
| `pip-audit` | aucune vulnérabilité connue | aucune vulnérabilité connue |
| `uv lock --check` | OK | OK |

```text
pre-commit run --all-files : 13 hooks, tous Passed
docker compose ps          : db (healthy), api (healthy), web (healthy)
docker inspect api User    : appuser
GET /api/v1/health         : {"status":"ok","version":"0.1.0"}
liens relatifs markdown    : 16 fichiers analysés, 0 lien cassé
secrets dans les fichiers suivis : aucun motif détecté
CI GitHub (self-hosted)    : run 43317081941 — backend, CLI et docker verts
```

## Corrections appliquées

| Fichier | Changement |
|---|---|
| `.pre-commit-config.yaml` (racine) | nouvelle config, hooks par projet, fonctionnelle et testée |
| `backend/.pre-commit-config.yaml` | supprimé |
| `.gitignore` | ajout de `.import_linter_cache/` |
| `backend/Dockerfile` | exécution en `appuser` non privilégié |
| `cli/pyproject.toml` | ajout de `pip-audit` + mise en forme |
| `.github/workflows/ci.yml` | `pip-audit` ajouté au job `cli` |
| `README.md` | clarification Nginx (local) / Caddy (production) |
| `CONTRIBUTING.md`, `docs/installation.md` | installation de `pre-commit` depuis la racine |
| 21 fichiers | newline final (via `end-of-file-fixer`) |

## Recommandations priorisées

**P0 — avant E1**
Aucune : F-07 (contrat/noyau) et F-09 (couverture) sont résolus.

**P1 — avant M1**
1. Épingler et scanner l'image de base (F-12).

**P2 — hygiène**
2. F-13 → F-20 : version unique, `.dockerignore`, `SECURITY.md`, templates, Dependabot,
   `.editorconfig`, ADR.

## Suivi

- **2026-11-12 — F-11 résolu.** Dépôt `devmail0561-web/workhub` créé et poussé. Les runners
  hébergés GitHub étant bloqués par un problème de facturation du compte, la CI a été basculée
  sur le runner self-hosted du dépôt (`runs-on: [self-hosted, linux, x64]`) et le port du
  service Postgres déplacé à `55432`. Run `43317081941` : backend, CLI et docker verts.
- **2026-11-12 — F-17 résolu.** Actions mises à jour vers `checkout@v7` et `setup-uv@v7`
  (runtime Node 24), supprimant l'avertissement de dépréciation de Node 20.
- **2026-11-12 — F-07 résolu.** Contrat 3 limité aux modules métier ; contrats 6 (le noyau
  `shared` ne dépend d'aucun module métier) et 7 (les modules métier n'importent de `shared` que
  son API publique). Violations testées puis retirées.
- **2026-11-12 — F-08 résolu.** Dockerfile construit avec `uv sync --frozen` (image uv épinglée
  `0.13.0`), build et health vérifiés.
- **2026-11-12 — F-09 résolu.** `pytest-cov` ajouté, seuil global 80 % bloquant dans la config
  pytest ; couverture mesurée à 100 % à ce stade. Le seuil domaine 90 % sera activé avec E0-08/E1.
- **2026-11-12 — F-10 résolu.** Ports liés à `127.0.0.1` ; `POSTGRES_PASSWORD` obligatoire
  (Compose échoue explicitement s'il manque).

## Conclusion

Les fondations sont **validées** : outillage, règles d'architecture, stack locale et
documentation sont cohérents et vérifiés. Le défaut majeur (`pre-commit` inopérant) est corrigé,
ainsi que l'ensemble des constats élevés et moyens hormis F-12. La poursuite vers **E0-06**
(modèle de données) et **E0-07** (ADR) est débloquée, y compris **E0-08** (noyau `shared`) grâce
au nouveau contrat 6/7.
