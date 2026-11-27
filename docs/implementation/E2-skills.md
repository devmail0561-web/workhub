# E2 — Skills versionnées

## Périmètre livré

Cœur Skills : création d'une Skill et de son brouillon, fichiers adressés par contenu,
publication immuable, lecture des versions, manifeste canonique, comparaison et historique des
versions, API REST.

Tâches couvertes : E2-01 → E2-08, E2-11, E2-12 (partie REST/ownership) et E2-14
(ETag/If-Match). L'export/import (E2-09/E2-10), la recherche (E2-13), l'UI (E2-15/E2-16)
et le scan de secrets E2-03 restent à livrer.

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

## Dépendances entre Skills

`POST /api/v1/skills/{slug}/publish` accepte `dependencies: [{slug, constraint}]` :

- le slug cible doit exister et être publié (ou déprécié) ; une dépendance vers soi-même est
  rejetée (`422`) ;
- la contrainte SemVer est validée puis évaluée : version exacte, `>=`, `>`, `<=`, `<`, `=`,
  plages `^`/`~`, jokers `*`/`x` et alternatives `||` ;
- la résolution retient la version publiée la plus récente qui satisfait la contrainte ; une
  contrainte insatisfaite renvoie `409` ;
- le graphe est parcouru récursivement sur les dépendances des versions résolues ; toute
  boucle revenant à la Skill publiée est rejetée (`422`) avec le chemin du cycle ;
- la déclaration et la version résolue sont figées dans le manifeste
  (`slug`, `constraint`, `resolved_semver`) et dans la table `skill_dependency`
  (`version_id`, `depends_on_skill_id`, `version_constraint`) ;
- `GET /api/v1/skills/{slug}/versions/{semver}` expose la résolution dans `dependencies`.

Les dépendances ne modifient jamais les versions déjà publiées : une nouvelle version d'une
dépendance n'affecte que les publications suivantes.

## Cycle de vie de la Skill

`POST /api/v1/skills/{slug}/transitions` applique une transition autorisée :

| État courant | Transitions autorisées |
|---|---|
| `draft` | `review` |
| `review` | `draft` |
| `published` | `deprecated`, `archived` |
| `deprecated` | `published`, `archived` |
| `archived` | aucune (terminal) |

- La publication fait passer la Skill en `published` depuis `draft`, `review` ou
  `deprecated` ; une Skill `archived` est en lecture seule et refuse toute écriture ou
  publication (`409`).
- L'archivage renseigne `archived_at`, retire la Skill des listes et la rend invisible aux
  autres principals ; le propriétaire et les administrateurs conservent l'accès.
- **Seule la Skill change d'état** : ses versions restent toutes `published`, immuables et
  lisibles via `GET /versions/{semver}`. Aucune version n'est archivée.
- Chaque transition est auditée (`skill.transition`) avec les états source et cible.

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

- Le scan de secrets, l'export/import, la recherche, l'UI et MCP restent hors de ce lot.
- L'historique recalcule les statistiques à chaque appel ; une pagination ou un cache pourra
  être ajouté si les historiques deviennent volumineux.

## Vérifications

- `uv run pytest -m "not integration" -q` : 144 tests, couverture 86,49 %.
- `uv run ruff check .` et `uv run ruff format --check .` : verts.
- `uv run pyright` : 0 erreur.
- `uv run lint-imports` : 6 contrats conservés.
- `frontend/openapi.json` : 20 chemins, dont les 10 routes Skills, avec les schémas de
  dépendances et de transition ; snapshot et types régénérés.
- `pnpm run typecheck`, `pnpm test`, `pnpm run build` : verts.
- Tests d'intégration Skills : 3 tests verts sur PostgreSQL réel (Docker local).
