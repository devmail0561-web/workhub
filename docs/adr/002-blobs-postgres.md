# ADR 002 — Blobs de Skills dans PostgreSQL, adressés par SHA-256

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07

## Contexte

Une Skill est un ensemble de fichiers texte (SKILL.md, scripts, ressources) de taille modérée.
Il faut garantir l'intégrité (le contenu ne change jamais sans changer d'identifiant), éviter
les doublons entre versions, et conserver une transaction atomique entre métadonnées et
contenus. L'infrastructure actuelle ne comporte qu'une base PostgreSQL.

## Décision

Stocker les contenus dans **PostgreSQL**, dans une table `blob` :

- clé primaire `sha256 bytea` (32 octets), `size bigint`, `content bytea`, `created_at` ;
- insertion **idempotente** : même contenu ⇒ un seul blob ;
- contrainte `CHECK` : `octet_length(content) = size` et `digest(content, 'sha256') = sha256` ;
- **append-only** : `UPDATE` interdit ; `DELETE` réservé à un GC explicite
  (`workhub.allow_blob_gc = on`) et aux blobs non référencés ;
- les fichiers de brouillon et de version référencent `blob.sha256` (pas de copie).

Des plafonds (taille par fichier et par version) seront fixés en E2-01 ; au-delà, un stockage
objet pourra être introduit **derrière la même interface applicative**, sans changer le modèle
logique.

## Conséquences

**Positives**

- Atomicité : publier une version et ses fichiers est une seule transaction.
- Déduplication naturelle entre versions et brouillons.
- Sauvegarde/restauration unique (base + contenus) et vérification d'intégrité possible.
- Aucun service supplémentaire à exploiter.

**Négatives**

- La base grossit et la mémoire du serveur porte les écritures/lectures.
- Les gros fichiers imposent du streaming applicatif (à traiter en E2-01).
- Le GC doit être conçu avec soin (références croisées, courses).

## Alternatives écartées

- **Système de fichiers local** : cohérence transactionnelle difficile, sauvegardes séparées.
- **S3/MinIO** : complexité opérationnelle prématurée ; réévaluable si volume ou multi-instance.
- **Git comme stockage** : détourne l'outil, complique les permissions et le versionnage métier.

## Références

- [Schéma v0 § Skills](../specs/schema-v0.md)
- Plan §4.1, §5.1
- [ADR 003](003-manifeste-empreinte.md), [ADR 006](006-brouillons-versions.md)
