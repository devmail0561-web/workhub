# E1 — Identité et authentification

## Métadonnées

| Champ | Valeur |
|---|---|
| Epic | `E1` |
| Jalon | `M0 → M2` |
| Tâches couvertes | `E1-01`, `E1-02`, `E1-03`, `E1-04`, `E1-05` |
| Statut | E1-01 à E1-05 terminés ; E1-06 → E1-07 à venir |
| Dernière mise à jour | 2026-11-18 |
| ADR liées | [004 — Identité](../adr/004-identite-principal.md) |

## Objectif

Donner à WorkHub une identité unifiée : un compte administrateur créé explicitement, un mot
de passe jamais stocké en clair, des sessions révocables, puis des intégrations à jetons
opaques portant des scopes explicites. Toutes ces identités convergent vers le même
`Principal`.

## Tâches et état

| Tâche | Description | État | Critère de fin vérifié |
|---|---|---|---|
| `E1-01` | Entité `User`, hash argon2id, premier admin via CLI d'amorçage | fait | Aucun compte par défaut ; création explicite testée ; mot de passe haché |
| `E1-02` | Login JWT court + refresh cookie `HttpOnly`, rotation, logout, expiration | fait | Tests de session, rotation, ancien jeton rejeté, expiration et déconnexion |
| `E1-03` | Limitation des tentatives de connexion | fait | Verrou temporaire par IP et par compte testé, expiration et remise à zéro |
| `E1-04` | Entités `Integration`, `ApiToken` (haché), scopes, expiration, révocation | fait | Création, affichage unique du jeton, expiration, révocation et isolation par propriétaire testés |
| `E1-05` | Résolution du `Principal` (session ou jeton) et décorateur d'autorisation | fait | `/auth/principal` résout les deux types ; le décorateur refuse un scope absent |
| `E1-06` → `E1-07` | Restriction par projet, matrice de permissions | à faire | — |

## Ce qui a été implémenté

### Domaine et application

- `backend/src/workhub/iam/domain/user.py` : `User`, normalisation d'e-mail et politique
  minimale du mot de passe d'amorçage (12 à 1024 caractères).
- `backend/src/workhub/iam/domain/session.py` : session de rafraîchissement (hash, expiration,
  révocation).
- `backend/src/workhub/iam/application/ports.py` : ports `UserRepository`,
  `SessionRepository`, `LoginAttemptLimiter`, `PasswordHasher`, `TokenIssuer` et
  `RefreshTokenFactory`.
- `backend/src/workhub/iam/application/auth.py` : connexion, rafraîchissement avec rotation,
  déconnexion idempotente et validation du JWT d'accès. La connexion vérifie le verrou avant
  toute vérification de mot de passe, compte chaque échec et efface les compteurs après succès.
- `backend/src/workhub/iam/application/bootstrap.py` : création du premier administrateur,
  refus des doublons et des mots de passe faibles.
- `backend/src/workhub/iam/domain/integration.py` : `Integration`, types `opencode`,
  `claude_code`, `codex`, `other`, normalisation du nom et révocation idempotente.
- `backend/src/workhub/iam/domain/api_token.py` : `ApiToken`, validation stricte des scopes
  (`ressource:action`), refus des jokers et des droits réservés aux humains, contrôle de
  l'expiration.
- `backend/src/workhub/iam/application/integration_ports.py` : ports `IntegrationRepository`,
  `ApiTokenRepository`, `ApiTokenFactory` et projection `TokenIdentity`.
- `backend/src/workhub/iam/application/integrations.py` : création, liste, révocation des
  intégrations, émission et révocation des jetons, isolation par propriétaire.
- `backend/src/workhub/iam/application/principal.py` : `PrincipalResolver` qui accepte un JWT
  d'access ou un jeton `whub_…`, vérifie l'état du compte, du jeton et de l'intégration, puis
  met à jour `last_used_at`.
- `backend/src/workhub/iam/application/views.py` : `UserView`, `AuthResult`,
  `IntegrationView`, `IssuedApiTokenView`, `CreatedIntegrationView` et conversion
  `UserView.to_principal()`, sans hash ni donnée interne.
- `backend/src/workhub/shared/domain/authorization.py` : décorateur `require_scope`, réexporté
  par `shared.api`, qui exige un `Principal` et un scope avant d'exécuter le cas d'usage.

### Infrastructure

- `backend/src/workhub/iam/infrastructure/security.py` : argon2id
  (`time_cost=3`, `memory_cost=65536`, `parallelism=4`), JWT HS256, refresh token opaque de
  48 octets aléatoires haché en SHA-256 et `OpaqueApiTokenFactory` qui génère des jetons
  `whub_` puis ne stocke que leur hash SHA-256.
- `backend/src/workhub/iam/infrastructure/repositories.py` : dépôts SQLAlchemy async ;
  la rotation est atomique (`UPDATE … WHERE hash = ancien AND non révoqué AND non expiré
  RETURNING user_id`), ce qui invalide immédiatement l'ancien jeton. Les dépôts
  `SqlAlchemyIntegrationRepository` et `SqlAlchemyApiTokenRepository` projettent les tables
  existantes `integration` et `api_token`, y compris la résolution jointe du jeton actif.
- `backend/src/workhub/iam/infrastructure/throttle.py` : compteurs PostgreSQL par hash
  SHA-256 d'IP et de compte, `INSERT … ON CONFLICT` atomique et transaction séparée pour que
  les échecs restent comptabilisés malgré l'annulation de la transaction métier.
- `backend/src/workhub/iam/infrastructure/config.py` : `AuthSettings` par variables
  d'environnement.
- `backend/src/workhub/iam/api.py` : composition des services, du résolveur de `Principal`,
  transaction par requête et paramètres publics du cookie.
- `backend/src/workhub/iam/bootstrap.py` : commande `workhub-bootstrap` (script Python du
  package backend, installé dans l'image API).

### Base de données

`backend/migrations/versions/0004_auth_sessions.py` :

- colonne `app_user.is_admin boolean not null default false` ;
- table `session` (`user_id` → `app_user`, hash SHA-256 unique, `created_at`, `expires_at`,
  `last_used_at`, `revoked_at`, `CHECK` sur la taille du hash et l'ordre des dates) ;
- index `ux_session_refresh_hash`, `ix_session_user_id`, `ix_session_expires_at`.

`backend/migrations/versions/0005_login_attempts.py` ajoute `login_attempt` : clé primaire
`key_hash` (32 octets, jamais l'IP ni l'e-mail en clair), `failure_count`,
`window_started_at`, `locked_until` et `updated_at`, avec `CHECK` sur la taille du hash, le
compteur positif et l'ordre des dates.

`backend/migrations/versions/0006_integrations.py` ne crée aucune table : `integration` et
`api_token` existent depuis le schéma v0. Elle ajoute les garde-fous
`ck_integration_kind` (`opencode`, `claude_code`, `codex`, `other`) et
`ck_api_token_expiration` (`expires_at is null or expires_at > created_at`).

### HTTP

`backend/src/workhub/interfaces/rest/auth.py` expose :

| Méthode | Route | Comportement |
|---|---|---|
| `POST` | `/api/v1/auth/login` | vérifie le verrou et les identifiants, renvoie un JWT d'accès et dépose le refresh cookie ; `429` + `Retry-After` si verrouillé |
| `POST` | `/api/v1/auth/refresh` | rotate le refresh token et renvoie un nouveau JWT |
| `POST` | `/api/v1/auth/logout` | révoque la session et efface le cookie (204) |
| `GET` | `/api/v1/auth/principal` | résout un JWT ou un jeton d'intégration et retourne type, nom et scopes |
| `GET` | `/api/v1/auth/me` | valide le JWT `Bearer` et retourne le compte |

Le cookie s'appelle `workhub_refresh`, vaut 30 jours par défaut, est `HttpOnly`,
`SameSite=Strict`, limité au chemin `/api/v1/auth` ; `Secure` est activé par
`WORKHUB_COOKIE_SECURE=true`. Les réponses de jeton portent `Cache-Control: no-store`.

`backend/src/workhub/interfaces/rest/integrations.py` expose la gestion des intégrations. Toutes
les routes exigent un `Principal` porteur de `integrations:manage` ; un jeton d'intégration ne
possède jamais ce scope.

| Méthode | Route | Comportement |
|---|---|---|
| `POST` | `/api/v1/integrations` | crée une intégration et son premier jeton, renvoyé une seule fois (201, `no-store`) |
| `GET` | `/api/v1/integrations` | liste les intégrations du propriétaire |
| `DELETE` | `/api/v1/integrations/{id}` | révoque l'intégration et tous ses jetons (204) |
| `POST` | `/api/v1/integrations/{id}/tokens` | émet un jeton supplémentaire (201, `no-store`) |
| `DELETE` | `/api/v1/integrations/{id}/tokens/{token_id}` | révoque un jeton précis (204) |

La dépendance `current_principal` résout indifféremment les deux types de `Bearer`. Les routes
de gestion restent réservées aux sessions humaines : le scope `integrations:manage` est refusé
lors de la création d'un jeton. Les erreurs conservent l'enveloppe JSON commune et `403` est
documenté globalement.

### Configuration

`deploy/.env.example` et Compose ajoutent `WORKHUB_SECRET_KEY` (obligatoire, 32 caractères
minimum), `WORKHUB_COOKIE_SECURE`, `WORKHUB_ACCESS_TOKEN_TTL_SECONDS` (900 s par défaut),
`WORKHUB_REFRESH_TOKEN_TTL_SECONDS` (30 jours par défaut), `WORKHUB_LOGIN_MAX_ATTEMPTS`
(5), `WORKHUB_LOGIN_ATTEMPT_WINDOW_SECONDS` (900 s) et `WORKHUB_LOGIN_LOCK_SECONDS` (900 s).

## Décisions et écarts par rapport au plan

- **Commande d'amorçage dans le package backend** : `workhub-bootstrap` est un script du
  package `workhub`, pas du package `workhub-cli`. Le CLI est contractuellement un client HTTP
  pur (contrat 5) et aucun compte n'existe encore pour l'authentifier ; faire dépendre le CLI
  de la base violerait cette frontière. La commande opérationnelle est donc livrée dans l'image
  API. Le mot de passe vient de `WORKHUB_BOOTSTRAP_PASSWORD` ou d'une saisie `getpass`, jamais
  d'un argument visible dans `ps`.
- **`is_admin` et joker temporaire** : le compte administrateur produit un `Principal` avec le
  scope `*`, ce qui permet immédiatement les opérations d'administration. Un compte non
  administrateur n'a encore aucun scope ; la matrice explicite ressource × action arrive en
  E1-07, qui remplacera ce joker.
- **Jetons d'intégration opaques** : le jeton brut (`whub_` + 32 octets aléatoires encodés)
  n'est affiché qu'à la création ou à l'émission ; seul son SHA-256 est stocké. Une fuite de
  la base ne permet donc pas de rejouer un jeton. L'expiration est optionnelle, doit inclure
  un fuseau horaire et être dans le futur ; il n'existe pas encore de durée maximale imposée.
- **Scopes explicites, jamais de joker pour une intégration** : le format
  `ressource:action` est validé, les doublons sont éliminés, et `*` ou
  `integrations:manage`, `projects:delete`, `skills:publish`, `tools:publish` sont refusés.
  Une intégration ne peut donc ni administrer les jetons ni publier à la place d'un humain.
- **Révocation en cascade** : révoquer une intégration révoque tous ses jetons dans la même
  transaction ; révoquer un jeton est idempotent. Il n'y a pas encore de rotation automatique
  d'un jeton : la révocation puis la réémission est le mécanisme supporté.
- **Résolution jointe et `last_used_at`** : un jeton n'est accepté que si le jeton et son
  intégration sont actifs et non expirés. La résolution met à jour `last_used_at` à chaque
  requête ; cette écriture systématique pourra être temporisée si elle devient coûteuse.
- **Deux surfaces d'identité** : `/auth/me` reste strictement réservé aux comptes humains,
  tandis que `/auth/principal` accepte les deux types. Les routes métier utiliseront
  `current_principal` et le décorateur `require_scope`, pas une inspection manuelle du JWT.
- **Refresh token opaque plutôt que JWT** : il est révocable immédiatement et son hash est seul
  stocké. Le JWT d'accès reste court (15 min) pour limiter la fenêtre en cas de fuite.
- **Rotation atomique sans détection de rejeu en chaîne** : un ancien refresh token est rejeté
  (401) après rotation, mais une famille de jetons volés n'est pas révoquée en bloc. La
  détection avancée pourra être ajoutée avec l'audit et la limitation de débit.
- **Pas de CSRF token supplémentaire** : le cookie est `SameSite=Strict` et limité au chemin
  d'authentification. Une validation d'`Origin` pourra compléter la défense si un proxy
  inverse multi-origine est ajouté.
- **Compteurs en PostgreSQL plutôt qu'en mémoire** : le verrou survit au redémarrage de l'API
  et reste correct avec plusieurs instances, sans introduire Redis. Les clés sont des hashes
  SHA-256, donc aucune IP ni adresse e-mail n'est stockée en clair. Une purge des lignes
  inactives reste à planifier.
- **Verrou par compte exposé à un déni de service ciblé** : cinq échecs peuvent bloquer
  temporairement un compte connu. Le verrou est borné (15 min par défaut), le succès le
  supprime, et le verrou par IP protège aussi les comptes inexistants. Un CAPTCHA ou une
  temporisation progressive pourra compléter la mesure si l'exposition augmente.

## Vérifications

```bash
cd backend
UV_PYTHON=/usr/bin/python3.12 uv run ruff check .
UV_PYTHON=/usr/bin/python3.12 uv run ruff format --check .
UV_PYTHON=/usr/bin/python3.12 uv run pyright
UV_PYTHON=/usr/bin/python3.12 uv run lint-imports
UV_PYTHON=/usr/bin/python3.12 uv run pytest
UV_PYTHON=/usr/bin/python3.12 uv run pip-audit
```

Résultats obtenus le 2026-11-18 : lint et format verts, pyright `0 errors`, six contrats
`import-linter` `KEPT`, **119 tests passés**, couverture **94,10 %**, audit sans
vulnérabilité connue. Les **15 tests d'intégration** passent sur PostgreSQL réel, y compris
`workhub-bootstrap`, le verrou par IP/compte, la persistance hachée des jetons, leur
expiration, leur révocation et la résolution du `Principal`.

Validation Compose sur un projet neuf (`workhub-e1-04`, ports isolés puis détruit) :

- `alembic_version = 0006_integrations` ;
- 32 tables (`31` métier + `alembic_version`), 17 triggers, 43 FK, 68 `CHECK` de table
  (70 au total avec les deux contraintes de domaine), 85 index hors `alembic_version` ;
- `workhub-bootstrap` crée l'administrateur ;
- `POST /login` → 200, `GET /me` → 200, `GET /principal` → 200 type `user`, scope `*` ;
- `POST /integrations` → 201 avec `Cache-Control: no-store`, jeton préfixé `whub_` ;
- `GET /principal` avec ce jeton → 200 type `integration` et scopes demandés ;
- `GET /integrations` avec ce jeton → 403, scope requis `integrations:manage` ;
- `POST /integrations/{id}/tokens` → 201 `no-store` ;
- révocation du jeton → 401 sur `/principal` ; révocation de l'intégration → 401 pour le
  second jeton ; l'intégration reste listée avec `revoked_at` renseigné.

Le scénario de verrouillage `429`/`Retry-After` reste couvert par les tests d'intégration
E1-03 ; la rotation et le logout restent couverts par ceux de session.

## Limites connues

- La limitation couvre la connexion par IP et par compte, pas encore les autres routes
  (E6-04). Derrière un proxy inverse, l'IP vue par l'API est celle du proxy tant que les
  en-têtes `X-Forwarded-*` ne sont pas explicitement approuvés.
- Pas de récupération de mot de passe, de changement de mot de passe ou de MFA.
- Aucune purge planifiée des sessions expirées, des compteurs `login_attempt` inactifs ni des
  jetons d'intégration expirés ou révoqués ; une tâche de rétention pourra s'appuyer sur
  `expires_at`, `window_started_at`, `last_used_at` et `updated_at`.
- Un jeton d'intégration n'est pas encore restreint à un sous-ensemble de projets (E1-06) et
  la matrice de permissions explicite n'existe pas encore (E1-07) : l'administrateur porte
  temporairement `*`.
- L'émission et la révocation des jetons ne sont pas encore auditées (E1-08) et aucune limite
  de débit propre aux jetons n'est appliquée.
- `last_used_at` est écrit à chaque requête authentifiée par jeton ; un cache ou une
  temporisation pourra réduire les écritures si nécessaire.
- Le frontend n'a pas encore d'écran de connexion ni de page Intégrations (E1-09/E12) ; le
  contrat OpenAPI et le client TypeScript sont à jour.
- Le runner self-hosted n'est toujours pas isolé de façon éphémère ; hors périmètre E1.

## Suites

1. **E1-06** — restriction des jetons par projet (`token_project_scope`).
2. **E1-07** — matrice de permissions explicite et tests générés ressource × scope × principal.
3. **E1-08** — journal d'audit append-only et service `audit.record()`.
