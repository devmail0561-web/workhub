# ADR 008 — Suppression : soft delete et archivage

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07

## Contexte

Skills, projets, missions et plans sont référencés par des épinglages, des exécutions et le
journal d'audit. Une suppression physique casserait l'historique, les empreintes et la
traçabilité. À l'inverse, conserver indéfiniment certaines données peut poser des problèmes de
confidentialité ou de volume.

## Décision

**Archivage par défaut**, suppression physique exceptionnelle :

- les entités métier portent `archived_at` (et/ou un statut `archived`) ; l'archivage est
  réversible tant que la politique de rétention le permet ;
- les listes/API masquent les éléments archivés sauf demande explicite ;
- aucune suppression physique d'une version publiée, d'un blob référencé, d'un instantané ou
  d'une ligne d'audit ;
- suppression physique autorisée uniquement pour les **brouillons** et les objets jamais
  publiés/référencés ;
- les blobs passent par un **GC explicite** (`workhub.allow_blob_gc = on`) après vérification
  d'absence de références ;
- une purge réglementaire (RGPD) sera une procédure dédiée, journalisée, distincte de l'usage
  courant.

## Conséquences

**Positives**

- Intégrité référentielle et historique préservés.
- Les épinglages et audits restent lisibles.
- L'archivage sert aussi de « corbeille » fonctionnelle.

**Négatives**

- Les requêtes doivent filtrer les archivés (risque d'oubli, à tester).
- Le stockage croît ; le GC et la rétention demandent des outils.
- Une vraie purge nécessite une procédure spécifique.

## Alternatives écartées

- **Suppression en cascade systématique** : casse l'audit et les références.
- **Event sourcing complet** : sur-ingénierie pour le stade actuel.
- **Aucune suppression, jamais** : ne répond pas aux obligations de purge.

## Références

- Plan §4.1, §4.4
- [Schéma v0](../specs/schema-v0.md)
- [ADR 002](002-blobs-postgres.md)
