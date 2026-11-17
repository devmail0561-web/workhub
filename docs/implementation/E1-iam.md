# E1 — Identité et authentification

## Métadonnées

| Champ | Valeur |
|---|---|
| Epic | `E1` |
| Jalon | `M0 → M2` |
| Tâches couvertes | `E1-01`, `E1-02` |
| Statut | E1-01 et E1-02 terminés ; E1-03 → E1-07 à venir |
| Dernière mise à jour | 2026-11-17 |
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
| `E1-03` | Limitation des tentatives de connexion | à faire | — |
| `E1-04` → `E1-07` | Intégrations, scopes, permissions | à faire | — |

## Ce qui a été implémenté

### Domaine et application

- `backend/src/workhub/iam/domain/user.py` : `User`, normalisation d'e-mail et politique
  minimale du mot de passe d'amorçage (12 à 1024 caractères).
- `backend/src/workhub/iam/domain/session.py` : session de rafraîchissement (hash, expiration,
  révocation).
- `backend/src/workhub/iam/application/ports.py` : ports `UserRepository`,
  `SessionRepository`, `PasswordHasher`, `TokenIssuer` et `RefreshTokenFactory`.
- `backend/src/workhub/iam/application/auth.py` : connexion, rafraîchissement avec rotation,
  déconnexion idempotente et validation du JWT d'accès.
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

### HTTP

`backend/src/workhub/interfaces/rest/auth.py` expose :

| Méthode | Route | Comportement |
|---|---|---|
| `POST` | `/api/v1/auth/login` | vérifie les identifiants, renvoie un JWT d'accès et dépose le refresh cookie |
| `POST` | `/api/v1/auth/refresh` | rotate le refresh token et renvoie un nouveau JWT |
| `POST` | `/api/v1/auth/logout` | révoque la session et efface le cookie (204) |
| `GET` | `/api/v1/auth/me` | valide le JWT `Bearer` et retourne le compte |

Le cookie s'appelle `workhub_refresh`, vaut 30 jours par défaut, est `HttpOnly`,
`SameSite=Strict`, limité au chemin `/api/v1/auth` ; `Secure` est activé par
`WORKHUB_COOKIE_SECURE=true`. Les réponses de jeton portent `Cache-Control: no-store`.

### Configuration

`deploy/.env.example` et Compose ajoutent `WORKHUB_SECRET_KEY` (obligatoire, 32 caractères
minimum), `WORKHUB_COOKIE_SECURE`, `WORKHUB_ACCESS_TOKEN_TTL_SECONDS` (900 s par défaut) et
`WORKHUB_REFRESH_TOKEN_TTL_SECONDS` (30 jours par défaut).

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

Résultats obtenus le 2026-11-17 : lint et format verts, pyright `0 errors`, six contrats
`import-linter` `KEPT`, **94 tests passés**, couverture **94,19 %**, audit sans vulnérabilité
connue. Les **11 tests d'intégration** passent sur PostgreSQL réel, y compris la commande
`workhub-bootstrap`.

Validation Compose sur un projet neuf (`workhub-e1`, ports isolés puis détruit) :

- `alembic_version = 0004_auth_sessions` ;
- 31 tables (`30` métier + `alembic_version`), 17 triggers, 43 FK, 63 `CHECK` de table,
  84 index hors `alembic_version` ;
- `workhub-bootstrap` crée `admin@example.test` ;
- `POST /login` → 200, cookie `HttpOnly` `SameSite=Strict` ;
- `GET /me` → 200 avec le JWT ;
- `POST /refresh` → 200 et nouveau cookie ;
- ancien refresh token → 401 ;
- `POST /logout` → 204 puis refresh → 401 ;
- les hashes en base font 32 octets, jamais le token en clair.

## Limites connues

- Pas de limitation de débit ni de verrouillage de compte (E1-03).
- Pas de récupération de mot de passe, de changement de mot de passe ou de MFA.
- Aucune purge planifiée des sessions expirées ; l'index `ix_session_expires_at` la facilitera.
- Le frontend n'a pas encore d'écran de connexion (E12) ; le contrat OpenAPI et le client
  TypeScript sont à jour.
- Le runner self-hosted n'est toujours pas isolé de façon éphémère ; hors périmètre E1.

## Suites

1. **E1-03** — limitation des tentatives et temporisation de connexion.
2. **E1-04/E1-05** — `Integration`, `ApiToken`, résolution du `Principal` et scopes.
3. **E1-06/E1-07** — restriction des jetons par projet et matrice de permissions.
