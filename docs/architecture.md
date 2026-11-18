# Architecture

Vue synthétique de l'architecture **telle qu'implémentée** et des règles qui encadrent la
suite. Les décisions détaillées vivent dans les [ADR](adr/README.md) et le plan de
développement.

## Style

**Monolithe modulaire** organisé en quatre couches par module :

```text
interfaces (REST, MCP, CLI)  ──►  application (cas d'usage + autorisation)
                                        │
                                        ▼
                                  domain (entités, règles)
                                        ▲
                                        │
                              infrastructure (SQLAlchemy, blobs)
```

Règle centrale : **REST, MCP et CLI n'embarquent aucune logique métier**. Ils traduisent un
protocole vers un cas d'usage de la couche `application`.

## Modules

Sous `backend/src/workhub/` :

| Module | Rôle | Jalon |
|---|---|---|
| `shared` | noyau : `Principal`, erreurs, horloge, ids, pagination | M0 |
| `iam` | utilisateurs, sessions, jetons, scopes | M0–M2 |
| `skills` | Skills versionnées, blobs, manifeste, exigences | M1 |
| `projects` | projets, missions, profil technique | M3 |
| `plans` | templates, versions, instances de plans | M4 |
| `competencies` | compétences, rôles, preuves | M5 |
| `execution` | tâches, exécutions, livrables, blocages | M3 |
| `knowledge` | ressources documentaires | M6 |
| `tools` | catalogue de scripts versionnés | M3b |
| `proposals` | mécanisme générique de propositions | M3b |
| `integrations` | environnements connectés, déploiements | M6 |
| `audit` | journal append-only | M0 |
| `interfaces/rest` | routeurs FastAPI `/api/v1` | M0 |
| `interfaces/mcp` | serveur MCP | M2 |

Chaque module métier est structuré en `domain/`, `application/`, `infrastructure/` et expose
son point d'entrée public dans `api.py`.

## Règles de dépendance (vérifiées par import-linter)

Les règles sont exécutées à chaque CI via `uv run lint-imports` (backend et CLI).

| # | Règle | Contrat | Portée |
|---|---|---|---|
| 1 | `domain` n'importe ni FastAPI, ni SQLAlchemy, ni application/infrastructure/interfaces | `forbidden` | `backend` |
| 2 | `application` n'importe pas `infrastructure` ni `interfaces` | `forbidden` | `backend` |
| 3 | Les modules **métier** sont indépendants (tout couplage doit être déclaré) | `independence` | `backend` |
| 4 | `interfaces.rest` et `interfaces.mcp` ne parlent qu'à `application` | `forbidden` | `backend` |
| 5 | `cli` ne dépend pas du package backend | `forbidden` | `cli` |
| 6 | Le noyau `shared` ne dépend d'aucun module métier | `forbidden` | `backend` |
| 7 | Les modules métier n'importent de `shared` que son API publique | `forbidden` | `backend` |

Précisions d'implémentation :

- **Règle 3** : `import-linter` n'exprime pas nativement « importer uniquement via `api.py` ».
  Le contrat `independence` est donc **plus strict** : aucun import croisé entre modules métier
  n'est autorisé par défaut. Quand un module devra appeler l'API publique d'un autre, l'import
  sera **whitelisté explicitement** dans le contrat (`ignore_imports`), ce qui rend tout
  couplage visible en revue.
- **Noyau `shared`** : il est volontairement **exclu** de l'indépendance, car il est conçu pour
  être utilisé par tous les modules. Deux contrats dédiés encadrent cette exception : `shared`
  ne dépend d'aucun module métier (règle 6) et les modules métier ne peuvent l'importer que par
  son API publique, jamais par `domain`/`application`/`infrastructure` (règle 7).
- **Interfaces et noyau** : les interfaces peuvent importer `workhub.shared.api` (types
  transverses : `Principal`, erreurs, pagination) ; une exception `ignore_imports` ciblée évite
  que le réexport transitif de `shared.domain` ne déclenche la règle 4. L'accès direct aux
  internals de `shared` reste interdit.
- **Règle 5** : le CLI étant un package séparé (`workhub_cli`), la règle est portée par un
  contrat dans `cli/pyproject.toml`, avec `include_external_packages = true` pour pouvoir
  interdire le module externe `workhub`.
- Les contrats utilisent des jokers (`workhub.*.domain`) pour couvrir tous les modules sans
  duplication : un nouveau module est automatiquement soumis aux règles 1, 2 et 4.

## Noyau partagé (`workhub.shared.api`)

| Primitive | Usage |
|---|---|
| `Principal`, `PrincipalType` | identité unifiée (utilisateur, intégration, système) et scopes |
| `WorkHubError` + sous-classes | erreurs métier à code stable, sans dépendance HTTP |
| `Clock`, `SystemClock` | temps injectable, UTC et timezone-aware |
| `new_id` | UUID v4 générés en application |
| `Page`, `PageRequest`, `paginate` | pagination bornée et navigation |
| `install_error_handlers` (interface REST) | enveloppe JSON unique `{"error": {...}}` |

## Persistance

- **SQLAlchemy 2** en mode asynchrone, pilote **psycopg 3** (`postgresql+psycopg`).
- **Alembic** dans `backend/migrations/` ; migration initiale `0001_schema_v0` issue du
  [schéma v0](specs/schema-v0.md), puis `0002_audit_log_truncate_guard`,
  `0003_fk_indexes`, `0004_auth_sessions` (`app_user.is_admin`, table `session`) et
  `0005_login_attempts` (compteurs de tentatives de connexion). Le DDL de référence reste
  documenté, une copie vendue est utilisée par la migration et un test empêche la dérive.
- **Séparation des rôles PostgreSQL** : `workhub_owner` possède la base, le schéma et les
  objets et applique les migrations ; `workhub_app` n'a que le DML runtime, sans DDL ni
  `TRUNCATE`, et `audit_log` reste en `SELECT`/`INSERT`. `workhub` est réservé au bootstrap.
- L'image API contient `alembic.ini` et `migrations/`. Compose enchaîne `db-bootstrap`, le
  service one-shot `migrate` (`alembic upgrade head` avec l'URL owner), `db-grants`, puis
  l'API avec l'URL app.
- `shared/infrastructure/database.py` fournit `Base`, `create_engine()` et
  `create_session_factory()`. Les tests d'intégration démarrent un PostgreSQL jetable via
  **testcontainers** et appliquent les migrations.
- Les migrations sont **synchrones** (déploiement) ; l'application utilise un moteur
  asynchrone.
- **Authentification** : le module `iam` compose le service via `iam/api.py` ; les interfaces
  ne voient que `AuthService` et les DTO publics. Les mots de passe sont hachés en argon2id,
  les JWT d'accès sont courts et les refresh tokens opaques sont stockés hachés en SHA-256
  dans `session`, avec rotation atomique et révocation.

## Frontend

- **SPA React 19 + TypeScript strict** construite par **Vite 8**, servie par Nginx non
  privilégié (uid 101, port 8080) ; Tailwind 4 et composants shadcn/ui copiés dans
  `frontend/src/components/ui`. En-têtes CSP, `nosniff`, `DENY` frame, referrer et permissions
  activés, `server_tokens off`.
- **TanStack Router** pour les routes typées et **TanStack Query** pour le cache des données
  serveur ; aucune donnée métier n'est stockée hors du cache de requêtes.
- **Contrat API unique** : `openapi-typescript` génère `src/api/schema.d.ts` depuis
  `frontend/openapi.json` ; `openapi-fetch` utilise ces types. L'instantané OpenAPI est
  régénéré depuis FastAPI à chaque évolution du contrat.
- **Même origine** : en développement Vite proxifie `/api` vers l'API ; en production Nginx
  fait de même vers le service `api`. Pas de CORS.
- **Tests** : Vitest + Testing Library pour les composants et le client API ; Playwright pour
  les parcours E2E critiques à partir des écrans métier.

## Observabilité

- Logs **JSON** via structlog (une ligne par requête) : `event`, `request_id`, `method`, `path`,
  `status_code`, `duration_ms`, niveau et horodatage UTC.
- `RequestContextMiddleware` reprend ou génère `X-Request-ID`, l'expose dans la réponse et dans
  l'enveloppe d'erreur ; aucune donnée sensible (en-têtes, corps) n'est journalisée.
- Toutes les erreurs HTTP (404/405, validation, erreur métier, exception inattendue) utilisent
  la même enveloppe JSON et exposent `request_id` ; les entrées de validation sont filtrées.
- `GET /api/v1/health` est typé par `HealthResponse` (`status: "ok"`, `version`), donc présent
  dans les composants OpenAPI et dans le client TypeScript ; les réponses 404/405/500 sont
  documentées avec `ApiErrorResponse` dans le contrat OpenAPI.
- Niveau réglable par `LOG_LEVEL` (défaut `INFO`), y compris dans Compose ; une valeur inconnue
  retombe sur `INFO` avec un avertissement.
- OpenTelemetry reste une option non activée.

## Frontières et dépendances externes

- **Pas de LLM embarqué** dans l'application (décision D8 du plan) : les suggestions passent
  par le mécanisme `Proposal`.
- **L'application n'installe et n'exécute rien** : le catalogue d'outils contient des scripts
  et leurs exigences déclarées ; c'est l'agent externe qui décide (décision D7).
- **MCP est un adaptateur mince** dans le même processus, qui réutilise les services de la
  couche `application` (décision D4).

## Points d'entrée implémentés à ce stade

| Point d'entrée | Fichier | État |
|---|---|---|
| API REST | `backend/src/workhub/interfaces/rest/app.py` | `GET /api/v1/health` |
| CLI | `cli/src/workhub_cli/__init__.py` | package vide (commandes à venir) |
| MCP | `backend/src/workhub/interfaces/mcp/` | vide (M2) |
