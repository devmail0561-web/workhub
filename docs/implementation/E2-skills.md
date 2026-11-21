# E2 — Skills versionnées

## Périmètre livré

Cœur Skills : création d'une Skill et de son brouillon, fichiers adressés par contenu,
publication immuable, lecture des versions, manifeste canonique et API REST.

Tâches couvertes : E2-01 → E2-06, E2-12 (partie REST/ownership) et E2-14 (ETag/If-Match).
Les dépendances entre Skills (E2-11), le cycle de vie (E2-07), le diff (E2-08),
l'export/import (E2-09/E2-10), la recherche (E2-13), l'UI (E2-15/E2-16) et le scan de
secrets E2-03 restent à livrer.

## Règles de sécurité et d'accès

- Une Skill créée par une intégration appartient à l'utilisateur propriétaire de cette
  intégration, jamais à l'ID d'intégration.
- Les brouillons sont accessibles uniquement au propriétaire et aux administrateurs.
- Un principal avec `skills:read` peut lire les Skills publiées de tous les propriétaires ;
  cela permet au référentiel central/MCP de fonctionner.
- Un utilisateur non-admin reçoit par défaut `skills:read`, `skills:propose` et
  `skills:publish`. Les intégrations conservent leurs scopes explicites.
- Une version créée par une intégration porte `origin_kind="integration"` et son
  `origin_integration_id`; une version applicative porte `origin_kind="app"`.

## Contrat de brouillon

- `GET /api/v1/skills/{slug}/draft` expose `ETag: "<lock_version>"`.
- `PUT`/`DELETE` sur les fichiers du brouillon et `POST /publish` exigent `If-Match`.
- `If-Match: *` accepte l'état courant ; un ETag obsolète renvoie `412`.
- Les écritures conditionnelles incrémentent `lock_version` dans la même transaction.
- La publication vérifie la version du brouillon et échoue en `412` en cas de modification
  concurrente.

## Manifeste

Le manifeste contient `manifest_version`, `name`, `description`, `slug`, `semver`, `parent`,
`files`, `dependencies` et `requirements`.

- Les fichiers sont triés par chemin et leur mode est normalisé sur quatre chiffres.
- Les requirements sont validés selon `package|system|service|script`, triés et dédupliqués.
- `hashes` et `tool_version_id` sont acceptés ; un requirement `script` exige
  `tool_version_id`.
- Le hash est `SHA-256` du JSON canonique UTF-8, clés triées, sans espace insignifiant.

## Limites connues

- `dependencies` est présent mais vide : l'API de dépendances entre Skills n'est pas encore
  livrée.
- Le scan de secrets, le diff, l'export/import, la recherche, l'UI et MCP restent hors de ce
  lot.
- Les tests d'intégration Skills ajoutés n'ont pas pu être exécutés localement faute de daemon
  Docker ; ils sont destinés au job CI avec PostgreSQL.

## Vérifications

- `uv run pytest -m "not integration" -q` : 129 tests, couverture 84,93 %.
- `uv run ruff check .` et `uv run ruff format --check .` : verts.
- `uv run pyright` : 0 erreur.
- `uv run lint-imports` : 6 contrats conservés.
- `frontend/openapi.json` : 17 chemins, dont les 7 routes Skills ; snapshot et types régénérés.
- `pnpm run typecheck`, `pnpm test`, `pnpm run build` : verts.
- Tests d'intégration Skills : ajoutés, non exécutés localement (Docker indisponible).
