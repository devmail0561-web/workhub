# Changelog

Tous les changements notables de WorkHub sont consignés dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le versionnement
sémantique ([SemVer](https://semver.org/lang/fr/)). Le projet est actuellement en
développement : la version `0.1.0` correspond à l'amorçage, sans release publiée.

## [Unreleased]

### Added

- **Authentification utilisateur (E1-01/E1-02)** : entité `User` et migration
  `0004_auth_sessions` (`is_admin`, table `session`), hash **argon2id**, commande
  `workhub-bootstrap` pour créer le premier administrateur sans compte par défaut, routes
  `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout` et
  `GET /api/v1/auth/me`, JWT d'accès court et refresh token opaque en cookie `HttpOnly` /
  `SameSite=Strict` avec rotation et révocation.
- **Protection brute-force (E1-03)** : compteurs persistés en base (`login_attempt`, migration
  `0005_login_attempts`) pour verrouiller temporairement une IP ou un compte après plusieurs
  échecs, réponse `429` avec `Retry-After`, remise à zéro après une connexion réussie ;
  `WORKHUB_LOGIN_MAX_ATTEMPTS`, `WORKHUB_LOGIN_ATTEMPT_WINDOW_SECONDS` et
  `WORKHUB_LOGIN_LOCK_SECONDS` configurables.
- **Intégrations et jetons opaques (E1-04)** : `Integration`, `ApiToken` haché en SHA-256,
  scopes `ressource:action`, expiration optionnelle, révocation en cascade, routes
  `POST/GET /api/v1/integrations`, `DELETE /api/v1/integrations/{id}` et
  `/api/v1/integrations/{id}/tokens` ; le jeton brut préfixé `whub_` n'est affiché qu'une fois.
  Migration `0006_integrations` pour les garde-fous de type et d'expiration.
- **Résolution unifiée du `Principal` (E1-05)** : `/api/v1/auth/principal` accepte un JWT de
  session ou un jeton d'intégration, décorateur `require_scope` côté application, scope `*`
  temporaire pour l'administrateur et refus des scopes de gestion pour les intégrations.
- **Cœur Skills (E2-01 → E2-06, E2-12, E2-14 partiel)** : domaine des fichiers et versions,
  manifeste canonique versionné (`manifest_version`, nom, description, dépendances et
  requirements triés), blobs SHA-256, brouillons, publication immuable, API REST
  `/api/v1/skills/*`, audit des écritures et tests unitaires/REST.
- **Concurrence des brouillons (E2-14/ADR 009)** : `ETag` fort basé sur `lock_version`,
  `If-Match` obligatoire sur les écritures et publication, incrément conditionnel en SQL et
  réponse `412` en cas de conflit.
- **Ownership et provenance des intégrations (E2-12)** : une Skill créée par une intégration
  appartient à l'utilisateur propriétaire de l'intégration ; l'origine de version est
  persistée (`origin_kind`/`origin_integration_id`) et exposée au client.
- **Lecture du référentiel publié** : les principals avec `skills:read` peuvent lire les
  Skills publiées dont ils ne sont pas propriétaires ; les brouillons restent privés.
- **Scopes humains par défaut** : les utilisateurs non-admin reçoivent `skills:read`,
  `skills:propose` et `skills:publish` ; l'administrateur conserve `*`.
- **Requirements complets** : support de `hashes` et `tool_version_id`, validation des formes
  `package|system|service|script` avant insertion, tri canonique et hash stable.
- **Diff de versions (E2-08)** : `GET /api/v1/skills/{slug}/diff?from=&to=` compare deux
  versions publiées, classe les fichiers ajoutés/modifiés/supprimés, produit des diffs
  unifiés texte tronqués à 200 000 caractères et signale les contenus binaires.
- **Historique des versions** : `GET /api/v1/skills/{slug}/history` expose un journal type
  `git log` (du plus récent au plus ancien) avec parent, auteur, changelog, origine,
  empreinte et statistiques de changements ; les versions précédentes restent publiées et
  lisibles, sans archivage.
- **Dépendances entre Skills (E2-11)** : `POST /publish` accepte `dependencies` avec une
  contrainte SemVer (exacte, `>=`, `^`, `~`, jokers, `||`), résout la version publiée la plus
  récente qui la satisfait, persiste le lien dans `skill_dependency` et rejette les
  auto-dépendances, contraintes insatisfaites et cycles avec le chemin fautif.
- **Cycle de vie de la Skill (E2-07)** : machine à états `draft → review → published →
  deprecated → archived` avec transitions contrôlées, route
  `POST /api/v1/skills/{slug}/transitions`, audit des changements, `archived_at` et lecture
  seule des Skills archivées. Les versions publiées ne sont jamais archivées : seule la
  Skill change d'état.
- **Durcissement base de données** : rôles `workhub_owner` (migrations) et `workhub_app`
  (runtime, sans DDL ni `TRUNCATE`), scripts `deploy/postgres/bootstrap.sh` et
  `permissions.sh`, services Compose `db-bootstrap` et `db-grants`.
- **Migrations de durcissement** : `0002_audit_log_truncate_guard` (trigger `BEFORE TRUNCATE`
  sur `audit_log`) et `0003_fk_indexes` (21 index couvrant les FK, dont 4 composites).
- **Contrat OpenAPI** : réponses 401/404/405/500 documentées avec `ApiErrorResponse`, `429`
  sur la connexion verrouillée, et client TypeScript régénéré.
- **Squelette frontend (E0-11)** : Vite 8 + React 19 + TypeScript strict, Tailwind 4,
  shadcn/ui, TanStack Router/Query, client OpenAPI généré (`openapi-typescript` +
  `openapi-fetch`) ; page `/` appelant `/api/v1/health`, proxy même origine (Vite/Nginx),
  image web multi-étapes, tests Vitest, job CI `frontend`.
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
- **Observabilité (E0-10)** : logs JSON structlog, `request_id` repris/généré et exposé en
  `X-Request-ID`, middleware de contexte, `request_id` dans l'enveloppe d'erreur, `LOG_LEVEL`
  configurable (65 tests, couverture 100 %).
- **Persistance (E0-09)** : SQLAlchemy 2 async + psycopg 3, Alembic et migration initiale
  `0001_schema_v0` (29 tables, 16 triggers), fixtures `testcontainers` et tests d'intégration
  sur PostgreSQL réel (55 tests, couverture 100 %).
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

- **Durcissement web** : image `nginx-unprivileged` (uid 101, port 8080), `server_tokens off`,
  en-têtes CSP/`nosniff`/`DENY`/referrer/permissions, `/healthz` en `text/plain` et propagation
  des en-têtes `X-Forwarded-*` ; Uvicorn sans en-tête `Server`.
- **CI et gouvernance** : `timeout-minutes` par job, tests d'intégration sur le service
  PostgreSQL via `WORKHUB_TEST_DATABASE_URL`, vérification upgrade/downgrade/upgrade Alembic,
  exécution de `schema-v0.verify.sql` dans pytest, `sha_pinning_required: true` et protection
  de `main` avec les quatre checks CI requis (force-push et suppression interdits).
- **Correctifs post-audit** : `/api/v1/health` est typé (`HealthResponse`) et l'enveloppe
  d'erreur couvre aussi 404/405/500 ; Compose exécute un service one-shot `migrate` avant
  l'API ; la CI verrouille les permissions, épingle les actions par SHA et refuse les PR de
  forks sur le runner self-hosted.
- **Configuration d'authentification** : `WORKHUB_SECRET_KEY` (32 caractères minimum),
  `WORKHUB_COOKIE_SECURE`, durées des jetons et cookie `workhub_refresh` configurables ;
  Compose refuse de démarrer sans secret JWT.
- La définition de « terminé » exige désormais la mise à jour de la page d'implémentation de
  l'epic concerné (`docs/implementation/`) et une entrée dans ce changelog.
- La configuration `pre-commit` est déplacée à la racine du dépôt avec un jeu de hooks par
  projet ; installation via `uv run --project backend pre-commit install`.
- Le README distingue Nginx (web local) et Caddy (TLS/production, à venir).

### Fixed

- **Verrouillage derrière proxy** : l'IP client n'est lue depuis `X-Forwarded-For` que si le
  pair est listé dans `WORKHUB_TRUSTED_PROXIES` (conteneur web par défaut) ; Nginx limite en
  plus les tentatives de connexion (`limit_req`/`limit_conn`).
- **Jeton d'intégration après désactivation** : la résolution vérifie désormais que le
  propriétaire est actif.
- **Configuration de production** : `WORKHUB_ENV` est lu ; en production, les secrets
  d'exemple et `WORKHUB_COOKIE_SECURE=false` sont refusés.
- **Commit après réponse HTTP** : les services d'authentification, d'intégration et de
  résolution du principal committent avant de répondre ; plus de succès HTTP sur transaction
  annulée en teardown.
- **Coût Argon2 et limite non atomique** : hachage/vérification hors boucle avec sémaphore,
  et réussite de connexion ne remet à zéro que le compteur du compte, pas celui de l'IP.
- **Audit des intégrations (E1-08)** : créations/révocations d'intégrations et de jetons
  journalisées avec `request_id`, sans jeton brut.
- **Skills et intégrations** : une intégration ne peut plus créer une Skill avec l'ID
  d'intégration comme propriétaire (faux 409), une intégration `skills:read` lit désormais les
  versions publiées, et l'origine n'est plus forcée à `app`.
- **Concurrence Skills** : les mises à jour de brouillon ne sont plus « dernier écrit gagne » ;
  `lock_version` est incrémenté et les publications concurrentes renvoient `412`/`409`.
- **Manifeste Skills** : ajout des champs ADR 003 manquants, normalisation du mode (`755` →
  `0755`), tri des requirements et validation stricte des SemVer, chemins et requirements.
- **Contrat Skills** : `frontend/openapi.json` et `src/api/schema.d.ts` régénérés avec les sept
  routes Skills, les headers `If-Match` et les métadonnées d'origine.
- **Proxy Skills** : `client_max_body_size` passe de `1m` à `70m` pour couvrir une version de
  50 Mo encodée en base64.
- **`TRUNCATE audit_log`** : l'append-only est désormais protégé aussi au niveau statement ;
  `workhub_app` n'a pas le privilège et le trigger rejette l'opération côté owner.
- **FK sans index** : 21 index ajoutés pour éviter les parcours séquentiels lors des
  vérifications et suppressions de parents.
- **Enveloppe d'erreur** : 404/405 renvoyaient `{"detail": ...}`, 422 avait `request_id: null`
  et 500 renvoyait `text/plain` sans `X-Request-ID` ; tous les cas utilisent désormais
  `{"error": ...}` avec l'identifiant, et les entrées de validation ne sont plus exposées.
- **Healthcheck web** : BusyBox `wget` résolvait `localhost` en `::1` alors que Nginx n'écoute
  qu'en IPv4 ; le healthcheck utilise `127.0.0.1`, le conteneur redevient `healthy`.
- **Déploiement des migrations** : l'image API ne contenait pas `alembic.ini`/`migrations/` et
  Compose laissait la base vide ; les fichiers sont copiés et un service `migrate` précède
  l'API.
- **`LOG_LEVEL`** : une valeur inconnue faisait échouer l'import (`KeyError`) ; elle retombe
  désormais sur `INFO` avec un avertissement.
- **Pagination** : `paginate()` appliquait l'offset une seconde fois lorsqu'un `total` était
  fourni ; la sémantique « séquence complète » est documentée et testée.
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
- Le moteur et les migrations existent, mais l'API n'utilise pas encore la base au runtime
  (premiers cas d'usage en E1/E2).
- Constats F-07 à F-10 de l'audit corrigés ; reste F-12 (image de base non épinglée/scannée) :
  voir le rapport d'audit.
- Le runner self-hosted reste requis ; les PR issues de forks sont désormais ignorées pour ne
  pas exécuter de code externe sur l'hôte. Une isolation éphémère du runner reste recommandée.
- La branche `main` est protégée par les checks CI requis et l'épinglage SHA des actions est
  imposé ; le prochain run GitHub validera le workflow courant.
