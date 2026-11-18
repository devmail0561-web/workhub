# E1 — Identité et authentification

## Métadonnées

| Champ | Valeur |
|---|---|
| Epic | `E1` |
| Jalon | `M0 → M2` |
| Tâches couvertes | `E1-01`, `E1-02`, `E1-03` |
| Statut | E1-01 à E1-03 terminés ; E1-04 → E1-07 à venir |
| Dernière mise à jour | 2026-11-18 |
| ADR liées | [004 — Identité](../adr/004-identite-principal.md) |

## Objectif

Donner à WorkHub une identité humaine réelle : un compte administrateur créé explicitement,
un mot de passe jamais stocké en clair, et des sessions révocables. Les agents et les
intégrations arriveront ensuite (E1-04 → E1-07) sur le même `Principal`.

## Tâches et état

| Tâche | Description | État | Critère de fin vérifié |
|---|---|---|---|
| `E1-01` | Entité `User`, hash argon2id, premier admin via CLI d'amorçage | fait | Aucun compte par défaut ; création explicite testée ; mot de passe haché |
| `E1-02` | Login JWT court + refresh cookie `HttpOnly`, rotation, logout, expiration | fait | Tests de session, rotation, ancien jeton rejeté, expiration et déconnexion |
| `E1-03` | Limitation des tentatives de connexion | fait | Verrou temporaire par IP et par compte testé, expiration et remise à zéro |
| `E1-04` → `E1-07` | Intégrations, scopes, permissions | à faire | — |

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
- `backend/src/workhub/iam/application/views.py` : `UserView` et `AuthResult`, sans hash ni
  donnée interne.

### Infrastructure

- `backend/src/workhub/iam/infrastructure/security.py` : argon2id
  (`time_cost=3`, `memory_cost=65536`, `parallelism=4`), JWT HS256, refresh token opaque de
  48 octets aléatoires haché en SHA-256.
- `backend/src/workhub/iam/infrastructure/repositories.py` : dépôts SQLAlchemy async ;
  la rotation est atomique (`UPDATE … WHERE hash = ancien AND non révoqué AND non expiré
  RETURNING user_id`), ce qui invalide immédiatement l'ancien jeton.
- `backend/src/workhub/iam/infrastructure/throttle.py` : compteurs PostgreSQL par hash
  SHA-256 d'IP et de compte, `INSERT … ON CONFLICT` atomique et transaction séparée pour que
  les échecs restent comptabilisés malgré l'annulation de la transaction métier.
- `backend/src/workhub/iam/infrastructure/config.py` : `AuthSettings` par variables
  d'environnement.
- `backend/src/workhub/iam/api.py` : composition du service, transaction par requête et
  paramètres publics du cookie.
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

### HTTP

`backend/src/workhub/interfaces/rest/auth.py` expose :

| Méthode | Route | Comportement |
|---|---|---|
| `POST` | `/api/v1/auth/login` | vérifie le verrou et les identifiants, renvoie un JWT d'accès et dépose le refresh cookie ; `429` + `Retry-After` si verrouillé |
| `POST` | `/api/v1/auth/refresh` | rotate le refresh token et renvoie un nouveau JWT |
| `POST` | `/api/v1/auth/logout` | révoque la session et efface le cookie (204) |
| `GET` | `/api/v1/auth/me` | valide le JWT `Bearer` et retourne le compte |

Le cookie s'appelle `workhub_refresh`, vaut 30 jours par défaut, est `HttpOnly`,
`SameSite=Strict`, limité au chemin `/api/v1/auth` ; `Secure` est activé par
`WORKHUB_COOKIE_SECURE=true`. Les réponses de jeton portent `Cache-Control: no-store`.

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
- **`is_admin` minimal** : la colonne marque le compte d'amorçage. Les scopes et la matrice de
  permissions restent en E1-05/E1-07 ; aucune route métier ne s'appuie encore sur ce drapeau.
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
`import-linter` `KEPT`, **98 tests passés**, couverture **94,57 %**, audit sans vulnérabilité
connue. Les **12 tests d'intégration** passent sur PostgreSQL réel, y compris
`workhub-bootstrap`, le verrou par IP/compte et son expiration.

Validation Compose sur un projet neuf (`workhub-e1-03`, ports isolés puis détruit) :

- `alembic_version = 0005_login_attempts` ;
- 32 tables (`31` métier + `alembic_version`), 17 triggers, 43 FK, 66 `CHECK` de table,
  85 index hors `alembic_version` ;
- `workhub-bootstrap` crée `admin@example.test` ;
- `POST /login` → 200, cookie `HttpOnly` `SameSite=Strict` ;
- `GET /me` → 200 avec le JWT ;
- `POST /refresh` → 200 et nouveau cookie ;
- trois échecs → 401, puis le bon mot de passe → 429 avec `Retry-After: 60` ;
- deux compteurs `login_attempt` (IP et compte), hashes de 32 octets, tous deux verrouillés ;
- après 60 s, `POST /login` → 200 et compteurs supprimés.

La rotation et le logout restent couverts par les tests d'intégration de session.

## Limites connues

- La limitation couvre la connexion par IP et par compte, pas encore les autres routes
  (E6-04). Derrière un proxy inverse, l'IP vue par l'API est celle du proxy tant que les
  en-têtes `X-Forwarded-*` ne sont pas explicitement approuvés.
- Pas de récupération de mot de passe, de changement de mot de passe ou de MFA.
- Aucune purge planifiée des sessions expirées ni des compteurs `login_attempt` inactifs ;
  une tâche de rétention pourra s'appuyer sur `expires_at`, `window_started_at` et
  `updated_at`.
- Le frontend n'a pas encore d'écran de connexion (E12) ; le contrat OpenAPI et le client
  TypeScript sont à jour.
- Le runner self-hosted n'est toujours pas isolé de façon éphémère ; hors périmètre E1.

## Suites

1. **E1-04/E1-05** — `Integration`, `ApiToken`, résolution du `Principal` et scopes.
2. **E1-06/E1-07** — restriction des jetons par projet et matrice de permissions.
3. **E1-08** — journal d'audit append-only et service `audit.record()`.
