# ADR 004 — Identité : Principal, intégrations, jetons et scopes

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07
- **Décisions liées** : D3, D6 (plan §0)

## Contexte

WorkHub est utilisé par des humains (interface web, CLI) et par des agents externes (Claude
Code, OpenCode via MCP). Les deux doivent être authentifiés, autorisés et audités de façon
uniforme. Les agents ne doivent recevoir que les droits strictement nécessaires, limités dans
le temps et éventuellement à un projet.

## Décision

Un **`Principal`** unique en application, de type `user` ou `integration`, identifié par
`(type, id)`. Toute couche `application` reçoit ce Principal et vérifie les scopes avant
d'agir ; les interfaces ne décident jamais des permissions.

- **Utilisateurs** : mot de passe `argon2id`, session via JWT d'accès court + refresh token en
  cookie `HttpOnly` (rotation, révocation).
- **Intégrations** : entité `integration` propriétaire, et `api_token` opaque **stocké haché**
  (SHA-256), affiché une seule fois à la création.
- **Scopes** granulaires lecture/écriture (ex. `skills:read`, `skills:write`,
  `projects:read`), portés par le jeton ; un jeton peut être restreint à un projet
  (`token_project_scope`, E1-06).
- **Pas de compte par défaut** : le premier administrateur est créé par une commande CLI
  d'amorçage.
- **Audit** : chaque écriture enregistre le Principal, l'action, la ressource et le résultat.

## Conséquences

**Positives**

- Un seul modèle d'autorisation pour REST, MCP et CLI.
- Révocation immédiate côté base ; pas de secret en clair.
- Principe du moindre privilège et traçabilité homogène.

**Négatives**

- Complexité des tests de permissions (matrice générée en E1-07).
- Gestion de la rotation des refresh tokens et des jetons.
- Un jeton partagé entre agents reste un risque opérationnel (à documenter).

## Alternatives écartées

- **Un jeton par utilisateur** : ne distingue pas les agents et empêche la révocation ciblée.
- **OAuth2/OIDC externe** : reporté ; non nécessaire pour une instance mono-équipe.
- **Sessions serveur opaques uniquement** : moins adapté au CLI et au MCP.

## Références

- Plan §7 (scopes et menaces)
- [Schéma v0](../specs/schema-v0.md)
- [ADR 005](005-mcp-adaptateur.md)
