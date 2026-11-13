# ADR 009 — Concurrence : verrouillage optimiste (`ETag` / `If-Match`)

- **Statut** : acceptée
- **Date** : 2026-11-13
- **Tâche** : E0-07

## Contexte

Plusieurs humains et agents peuvent modifier le même brouillon de Skill ou la même instance de
plan. Un « dernier écrit gagne » écrase silencieusement le travail d'autrui ; un verrou
pessimiste prolongé bloque les agents et complique les transactions.

## Décision

**Verrouillage optimiste** sur les ressources mutables :

- chaque ressource expose une version monotone (`lock_version` en base, `updated_at` en
  complément) sous forme d'**`ETag` fort** ;
- toute écriture exige `If-Match` ; l'absence ou l'incohérence renvoie **`412 Precondition
  Failed`** ;
- la mise à jour SQL est conditionnelle (`WHERE id = :id AND lock_version = :expected`) et
  incrémente la version dans la même transaction ;
- les créations et les lectures n'exigent pas de précondition ;
- la publication vérifie elle aussi la version du brouillon (pas de publication d'un état
  modifié entre-temps) ;
- pas de verrou pessimiste, sauf transactions courtes internes (migrations, GC).

## Conséquences

**Positives**

- Aucune perte silencieuse de modifications, y compris avec des agents concurrents.
- API sans état, adaptée au REST, au CLI et au MCP.
- Comportement prévisible et testable (matrice de tests de concurrence).

**Négatives**

- Les clients doivent gérer `412` (relire puis rejouer).
- Une longue session d'édition peut échouer à la sauvegarde (friction UX, à guider dans l'UI).
- Les écritures multi-ressources nécessitent une coordination applicative.

## Alternatives écartées

- **Dernier écrit gagne** : perte de données inacceptable.
- **Verrou pessimiste par ressource** : bloque les agents, gestion des expirations complexe.
- **CRDT / édition collaborative temps réel** : hors périmètre à ce stade.

## Références

- Plan §2.1, §4.1, §6.3
- [Schéma v0](../specs/schema-v0.md)
- [ADR 006](006-brouillons-versions.md)
