# ADR 005 — MCP comme adaptateur mince

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07
- **Décisions liées** : D4 (plan §0)

## Contexte

Les agents externes (Claude Code, OpenCode) doivent découvrir et récupérer des Skills, puis à
terme proposer des modifications. Le serveur MCP ne doit pas dupliquer la logique métier ni les
permissions, et doit pouvoir évoluer avec le protocole sans contaminer le domaine.

## Décision

MCP est un **adaptateur** dans le même processus que l'API :

- il traduit les appels d'outils en **cas d'usage de la couche `application`** ;
- il ne contient ni règles métier ni accès direct à la base ;
- il réutilise la résolution du `Principal` et les scopes (jeton d'intégration) ;
- **lecture d'abord** : à M2, `search_skills` et `get_skill` ; écritures (propositions,
  exécutions) à M3, soumises aux mêmes contrôles que le REST ;
- transports : `stdio` pour l'usage local, transport HTTP ajouté ensuite si nécessaire ;
- le schéma des outils est dérivé des cas d'usage, jamais l'inverse.

## Conséquences

**Positives**

- Une seule implémentation du métier et des permissions.
- Tests de contrat MCP possibles sans base réelle (doubles de la couche application).
- Évolution du protocole MCP isolée dans `interfaces/mcp`.

**Négatives**

- Verrouillage sur un protocole encore jeune (changements de schéma).
- Le même processus signifie un couplage de déploiement (assumé, cf. ADR 001).
- Les longs appels d'outils doivent respecter les timeouts du client.

## Alternatives écartées

- **Service MCP séparé** : complexité de déploiement et d'authentification prématurée.
- **MCP avec accès direct à la base** : contourne les cas d'usage et l'audit.
- **Passerelle REST→MCP générique** : perd la sémantique des cas d'usage et les permissions.

## Références

- Plan §3.1, §5.6, §7.3
- [Architecture](../architecture.md)
- [ADR 004](004-identite-principal.md)
