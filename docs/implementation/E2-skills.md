# E2 — Skills versionnées

## Périmètre livré

Cœur Skills : création d'une Skill et de son brouillon, fichiers adressés par contenu,
publication immuable, lecture des versions, manifeste canonique, comparaison et historique des
versions, API REST.

Tâches couvertes : E2-01 → E2-06, E2-08, E2-12 (partie REST/ownership) et E2-14
(ETag/If-Match). Les dépendances entre Skills (E2-11), le cycle de vie (E2-07),
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

## Comparaison de versions

`GET /api/v1/skills/{slug}/diff?from={semver}&to={semver}` compare deux versions publiées
visibles par le principal :

- les fichiers sont appariés par chemin et classés `added`, `modified` ou `deleted` ;
- un changement de contenu **ou de mode** marque le fichier comme modifié ;
- les fichiers texte produisent un diff unifié (`--- a/...`, `+++ b/...`) tronqué à
  200 000 caractères (`truncated=true`) ;
- les contenus binaires (octet nul ou UTF-8 invalide) sont signalés par `binary=true` sans
  diff textuel ;
- une version inconnue renvoie `404`, un SemVer invalide `422`.

## Historique des versions

`GET /api/v1/skills/{slug}/history` expose un journal comparable à `git log` :

- les versions sont retournées de la plus récente à la plus ancienne, avec `head` en tête ;
- chaque entrée porte `parent_semver`, `changelog` (message de version), auteur, origine,
  empreinte du manifeste, dates et statistiques `changes` (fichiers ajoutés/modifiés/
  supprimés, lignes insérées/supprimées) ;
- les statistiques sont calculées par comparaison avec la version parente ; la version racine
  est comparée à un ensemble vide ;
- **les versions précédentes ne sont jamais archivées** : elles restent `published`, lisibles
  via `GET /versions/{semver}` et forment une chaîne linéaire par `parent_version_id`. Seule
  la Skill elle-même pourra être dépréciée ou archivée par le futur cycle de vie.

## Limites connues

- `dependencies` est présent mais vide : l'API de dépendances entre Skills n'est pas encore
  livrée.
- Le cycle de vie de la Skill (Draft/Review/Published/Deprecated/Archived), le scan de
  secrets, l'export/import, la recherche, l'UI et MCP restent hors de ce lot.
- L'historique recalcule les statistiques à chaque appel ; une pagination ou un cache pourra
  être ajouté si les historiques deviennent volumineux.
- Les tests d'intégration Skills ajoutés n'ont pas pu être exécutés localement faute de daemon
  Docker ; ils sont destinés au job CI avec PostgreSQL.

## Vérifications

- `uv run pytest -m "not integration" -q` : 135 tests, couverture 85,62 %.
- `uv run ruff check .` et `uv run ruff format --check .` : verts.
- `uv run pyright` : 0 erreur.
- `uv run lint-imports` : 6 contrats conservés.
- `frontend/openapi.json` : 19 chemins, dont les 9 routes Skills ; snapshot et types régénérés.
- `pnpm run typecheck`, `pnpm test`, `pnpm run build` : verts.
- Tests d'intégration Skills : ajoutés, non exécutés localement (Docker indisponible).
