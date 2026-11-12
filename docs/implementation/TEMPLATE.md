# Modèle de page d'implémentation

> Copier ce fichier vers `E<epic>-<theme>.md` au démarrage d'un epic, puis le compléter.
> Supprimer les notes entre guillemets et les sections inutiles.

## Métadonnées

| Champ | Valeur |
|---|---|
| Epic | `E…` |
| Jalon | `M…` |
| Tâches couvertes | `E…-…` |
| Statut | en cours / terminé |
| Dernière mise à jour | AAAA-MM-JJ |
| ADR liées | `docs/adr/NNN-…` |

## Objectif

"Décrire en 2–4 phrases le résultat attendu et pourquoi cet epic est dans cet ordre."

## Tâches et état

| Tâche | Description | État | Critère de fin vérifié |
|---|---|---|---|
| `E…-…` | … | fait / partiel / à faire | … |

## Ce qui a été implémenté

"Détailler les fichiers et le comportement, avec les chemins précis. Mentionner les
interfaces publiques (`api.py`, endpoints, commandes CLI, outils MCP)."

## Décisions et écarts par rapport au plan

"Lister chaque décision non triviale et chaque écart au backlog, avec la raison. Renvoyer aux
ADR quand elles existent."

## Vérifications

"Reproduire les commandes exactes et le résultat attendu/obtenu."

```bash
# ex.
cd backend
uv run pytest
```

## Limites connues

"Ce qui n'est pas encore fait, les contours temporaires, les risques."

## Suites

"Prochaines tâches, dépendances débloquées."
