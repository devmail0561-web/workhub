# ADR 003 — Manifeste canonique et empreinte d'une SkillVersion

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07
- **Priorité** : décision coûteuse à changer (plan §13-3)

## Contexte

L'empreinte d'une Skill doit permettre de vérifier qu'un agent exécute exactement le contenu
attendu, et de détecter toute modification. Elle doit couvrir non seulement les fichiers, mais
aussi les **dépendances** et les **exigences** (`requirements`) : deux Skills aux fichiers
identiques mais aux exigences différentes ne sont pas interchangeables.

## Décision

Chaque `SkillVersion` porte un **manifeste JSON canonique** et `manifest_sha256`.

**Contenu du manifeste** (versionné par `manifest_version`) :

- identité : `name`, `slug`, `description`, `manifest_version` ;
- fichiers : `path`, `sha256`, `size`, `mode`, triés par `path` ;
- dépendances : Skill cible + contrainte SemVer, triées ;
- exigences : `kind` (`package|system|service|script`), nom, écosystème, contrainte/version
  épinglée, hashes, commande de vérification, `tool_version_id` pour un script ;
- interface déclarée (entrées/sorties/effets) si présente.

**Canonicalisation** : JSON UTF-8, clés triées lexicographiquement, aucun espace insignifiant,
pas de nombres flottants, tableaux dans l'ordre défini ci-dessus. L'empreinte est
`SHA-256(canonical_json_bytes)`.

**Règles**

- `manifest_sha256` est stocké sur la version et **recalculé** à l'export/import.
- Un seul octet modifié ⇒ empreinte différente (tests property-based en E2-04).
- L'ordre d'ajout des fichiers dans le brouillon n'influence pas l'empreinte.
- Toute évolution de structure incrémente `manifest_version` ; on ne réécrit jamais une
  empreinte existante.

## Conséquences

**Positives**

- Vérification indépendante de l'application (agent, CLI, export).
- Le bloc `requirements` est protégé par la même empreinte que les fichiers.
- Base saine pour la signature et la distribution (E2-09, E14).

**Négatives**

- La canonicalisation doit être spécifiée et testée précisément (risque d'empreintes divergentes
  entre implémentations).
- Ajouter un champ au manifeste change toutes les empreintes futures (d'où le versionnage).
- Les très gros manifestes alourdissent la base et les réponses.

## Alternatives écartées

- **Hash d'une archive tar** : métadonnées d'archive (mtime, ordre, uid) non déterministes.
- **Hash uniquement des fichiers** : ignore les exigences, pourtant déterminantes à l'exécution.
- **Arbre de Merkle** : utile pour de très gros ensembles, complexité inutile ici.
- **JSON non canonique** : ordre des clés et espaces feraient varier l'empreinte.

## Références

- Plan §5.1, §5.4, §13-3
- [Schéma v0](../specs/schema-v0.md)
- [ADR 002](002-blobs-postgres.md)
