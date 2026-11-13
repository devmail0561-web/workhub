# ADR 007 — Plans : template, version, instance, overrides

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07

## Contexte

Un plan de travail (Phase → Activité → Tâche → Sous-tâche) doit être réutilisable par plusieurs
projets, tout en permettant des adaptations locales et des états d'avancement indépendants.
Modifier un modèle ne doit jamais changer silencieusement les projets en cours.

## Décision

Quatre niveaux :

1. **`work_plan_template`** : identité réutilisable, catégorie A/B/C/D, slug.
2. **`work_plan_version`** : contenu JSON versionné (SemVer), éditable en brouillon puis
   **immuable une fois publié** (même garde que les Skills).
3. **`work_plan_instance`** : référence une **version figée** (`template_version_id`) et
   appartient à un projet **ou** une mission (exactement une cible).
4. **`instance_node`** : nœuds matérialisés (chemin, type, statut propre, `overrides` JSONB).

Règles :

- `template_version_id` est immuable ; changer de version passe par une opération explicite
  `migrate_instance`, avec diff et journal d'audit.
- Les overrides d'instance ne remontent jamais dans le modèle.
- Les états des nœuds sont propres à chaque instance (deux projets partagent le modèle, pas
  l'avancement).
- Les dépendances entre tâches sont validées sans cycle (E4-03).

## Conséquences

**Positives**

- Reproductibilité : une instance sait toujours quel contenu exact elle suit.
- Personnalisation locale sans « fork » du modèle.
- Migration traçable et testable.

**Négatives**

- Duplication du contenu entre modèle et instances (matérialisation).
- Outillage de migration et de diff à construire (E4-06).
- Toute correction du modèle nécessite une nouvelle version.

## Alternatives écartées

- **Instance lisant le modèle en direct** : changements silencieux inacceptables.
- **Copie complète par instance sans lien** : perte de traçabilité et migrations impossibles.
- **Overrides stockés dans le modèle** : contamination entre projets.

## Références

- Plan §4.2, §6
- [Schéma v0](../specs/schema-v0.md)
- [ADR 008](008-suppression-archivage.md)
