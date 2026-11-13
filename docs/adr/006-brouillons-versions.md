# ADR 006 — Brouillons mutables, versions immuables

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07
- **Priorité** : décision coûteuse à changer (plan §13-3)

## Contexte

L'édition d'une Skill demande des allers-retours (fichiers, validation, tests), mais les
projets épinglent des versions précises et les agents doivent pouvoir vérifier l'intégrité de
ce qu'ils exécutent. Autoriser la modification d'une version publiée rendrait les empreintes et
les épinglages mentheurs.

## Décision

Séparer **brouillon** et **version** :

- **`skill_draft`** : un seul brouillon par Skill, fichiers mutables, verrou optimiste
  (`lock_version`, exposé en `ETag`), basé éventuellement sur une version existante.
- **`skill_version`** : créée à la publication, **immuable**. Seules les transitions de statut
  `published → deprecated → archived` sont autorisées ; `UPDATE` des autres colonnes et
  `DELETE` sont rejetés par trigger.
- Les fichiers d'une version (`skill_version_file`) sont **insert-only** et référencent des
  blobs immuables.
- **Rollback** = publier une nouvelle version à partir du contenu d'une ancienne (nouveau
  SemVer), jamais réécrire l'historique.
- Une publication est atomique (version + fichiers + dépendances + exigences).

## Conséquences

**Positives**

- Épinglage et empreintes fiables dans le temps.
- Audit et diff naturels entre versions.
- Les agents peuvent mettre en cache une version sans risque de changement silencieux.

**Négatives**

- Croissance du stockage (contenus dédupliqués par blob, mais métadonnées accumulées).
- La publication doit être transactionnelle et valider le manifeste.
- Les corrections urgentes créent une nouvelle version (pas de « hotfix » en place).

## Alternatives écartées

- **Versions éditables avec historique** : complexité d'audit et risque d'incohérence des hashs.
- **Git comme source de vérité** : hors périmètre, permissions et UX inadaptées.
- **Brouillon unique réutilisé à chaque publication** : pas d'historique fiable.

## Références

- Plan §4.1, §5.2, §5.3
- [Schéma v0](../specs/schema-v0.md)
- [ADR 003](003-manifeste-empreinte.md), [ADR 009](009-concurrence-etag.md)
