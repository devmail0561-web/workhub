# ADR 001 — Monolithe modulaire et règles de dépendance

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07
- **Décisions liées** : D1, D4 (plan §0)

## Contexte

WorkHub doit livrer rapidement un produit cohérent (Skills, projets, plans, exécution) tout en
gardant des frontières nettes entre domaines. L'équipe est réduite et le déploiement cible est
une instance unique. Un découpage en services multiplierait l'infrastructure, les transactions
distribuées et les tests d'intégration avant même d'avoir validé le métier.

## Décision

Un **monolithe modulaire** : un seul processus FastAPI, un package Python `workhub`, et par
module métier quatre couches — `domain`, `application`, `infrastructure`, `interfaces` (REST,
MCP) — avec `api.py` comme **seul point d'entrée public**.

Les frontières sont vérifiées automatiquement par `import-linter` (7 contrats) :

1. `domain` n'importe aucun framework ni couche haute ;
2. `application` n'importe ni `infrastructure` ni `interfaces` ;
3. les modules métier sont indépendants (tout couplage est whitelisté explicitement) ;
4. les interfaces ne parlent qu'à `application` ;
5. le CLI ne dépend pas du package backend (HTTP uniquement) ;
6. le noyau `shared` ne dépend d'aucun module métier ;
7. les modules métier n'importent de `shared` que son API publique.

## Conséquences

**Positives**

- Un seul déploiement, une seule base, des transactions locales.
- Refactorisation facilitée par des frontières explicites et testées en CI.
- Le jour où un module doit être extrait, ses dépendances sont déjà connues.

**Négatives**

- Couplage de release : un changement dans un module redéploie l'ensemble.
- La discipline est portée par l'outillage : un import interdit fait échouer la CI, mais la
  conception peut rester discutable.
- Le noyau `shared` est un point de couplage global : il doit rester petit.

## Alternatives écartées

- **Microservices** : coût opérationnel et transactions distribuées injustifiés à ce stade.
- **Packages distribués séparément** : sur-ingénierie tant que le découpage métier n'est pas
  stabilisé.
- **Monolithe sans règles** : dette rapide, frontières non vérifiables.

## Références

- [Architecture](../architecture.md)
- Plan de développement §3.1, §3.3
- [ADR 006](006-brouillons-versions.md) pour la frontière entre brouillon et version
