# WorkHub — Stack recommandée, architecture et backlog de développement

> Document de planification dérivé du cahier des charges « référentiel central de compétences, projets, plans de travail et Skills ».
> Nom de travail : **WorkHub** (repris des exemples CLI du cahier des charges).
> Hypothèse de planification : **1 développeur**, ~15 à 20 h/semaine, assisté d'outils agentiques.
>
> **Révision 2 (12 novembre 2026)** — intègre : (1) le **catalogue d'outils rattaché aux Skills** (packages, scripts, outils système, signatures, exigences dans le manifeste) ; (2) le **mécanisme de propositions** (proposé / accepté / modifié / rejeté) et l'**assistant de création de projet** ; (3) le **profil technique de projet** servi aux agents ; (4) une **estimation recalculée** (≈ 26 semaines au lieu de 20, voir §8).
>
> **Révision 3** — corrections : la **contrainte de version porte sur les Skills** (pas sur les packages) ; les **scripts sont versionnés**, copiés à l'import ou créés directement dans le catalogue ; l'**empreinte d'un script = SHA-256 + signature**.
>
> **Révision 4** — précisions : les **packages (Python, Rust, Java, JS…) ne sont jamais importés ni copiés dans le catalogue** : ils sont seulement **déclarés dans la Skill** ; le **catalogue ne contient que des scripts** ; l'**agent décide** d'installer ou non, **dans le projet en cours** (jamais dans l'application).

---

## 0. Synthèse — les décisions qui comptent

| # | Décision | Pourquoi |
|---|---|---|
| D1 | **Commencer par la tranche verticale « Skills + Auth + MCP »**, pas par Compétences/Rôles (ordre du cahier des charges) | C'est le seul module qui valide l'hypothèse du produit (« un référentiel central consommé par des agents externes »). Compétences et Rôles sont du CRUD à faible risque : ils peuvent venir après. |
| D2 | **Monolithe modulaire FastAPI + PostgreSQL, sans Redis au MVP** | Rien dans le MVP n'exige un cache ou une file. Redis est une dépendance opérationnelle de plus. Si un job asynchrone devient nécessaire : file basée sur Postgres. |
| D3 | **Les fichiers de Skills sont stockés dans PostgreSQL, adressés par contenu (SHA-256)** | Immutabilité, déduplication, intégrité et sauvegarde atomique avec le reste des données. Pas de S3/MinIO avant d'en avoir besoin. |
| D4 | **Le serveur MCP est un adaptateur mince dans le même processus**, qui appelle les mêmes services applicatifs que l'API REST | Une seule logique métier, une seule couche d'autorisation. Pas de second backend. |
| D5 | **Les règles d'architecture sont vérifiées par la CI** (import-linter, tests de permissions, triggers SQL d'immutabilité) | Tes contraintes (immutabilité, séparation des modules, permissions) doivent être *imposées*, pas seulement documentées. |
| D6 | **Le contenu des Skills et des tâches est traité comme non fiable** côté agents | Une Skill ou une note modifiée peut contenir une injection de prompt qui sera lue par un agent. La gouvernance (review, hash, permissions d'écriture) est un enjeu de sécurité réel, pas administratif. |
| D7 | **Les exigences d'outils appartiennent à la Skill et sont décrites dans son manifeste hashé** ; seuls les **scripts** vivent dans le catalogue (versionnés) | Les packages (Python, Rust, Java, JS…) sont *déclarés*, jamais copiés. Ni l'application ni le catalogue n'installent ou n'exécutent quoi que ce soit : l'agent décide, dans le projet en cours. La version de la Skill fixe ce qui est déclaré ; la résolution réelle est consignée à l'exécution. |
| D8 | **Tout ce que l'application « suggère » est un `Proposal`** (proposé / accepté / modifié / rejeté). Aucun appel à un modèle de langage dans l'application | Une suggestion produite par un LLM embarqué ferait dépendre le produit d'un fournisseur et transformerait l'application en agent. Les propositions viennent d'un moteur de règles ou d'un agent externe via MCP. |

Durée estimée : **~26 semaines** pour le MVP complet (priorités 1 et 2) ; **~24 semaines** si on reporte après la 1.0 la génération automatique de structure (E15-06 à E15-08). **Première démo utile à la semaine 9** : Claude Code ou OpenCode récupère une Skill versionnée **et ses exigences** (packages à installer) via MCP.

---

## 1. Points du cahier des charges à trancher avant de coder

Ces ambiguïtés produiront de la dette si elles restent floues. Propositions de réponse incluses.

| Sujet | Question | Proposition |
|---|---|---|
| Multi-utilisateur | Le produit est-il mono-utilisateur (toi) ou multi-tenant ? | **Mono-utilisateur avec modèle multi-utilisateur prêt** (toutes les tables ont `owner_id`, les permissions passent par un `Principal`). Pas de gestion d'organisations au MVP. |
| Identité d'une Skill | Qu'est-ce qui identifie une Skill ? | Un `slug` unique (`web-pentest`) + un UUID interne. Le `name` du frontmatter SKILL.md doit correspondre au slug (convention Agent Skills). |
| Contenu d'une version | Qu'est-ce qui est hashé ? | Un **manifeste** (liste triée `chemin → sha256` + métadonnées) dont le SHA-256 est l'empreinte de la version. Voir §5. |
| Release vs. brouillon | Un brouillon est-il versionné ? | Non. Un brouillon est un **espace de travail mutable** (`SkillDraft`) ; seule la publication crée une `SkillVersion` immuable avec numéro SemVer. |
| Verrouillage | Que verrouille un projet ? | Une ligne `ProjectSkillPin(project_id, skill_id, version_id)`. Aucune résolution implicite de « latest » pour un projet épinglé. |
| Mise à jour d'un modèle de plan | Modification silencieuse interdite : comment ? | Une `WorkPlanInstance` référence une `WorkPlanVersion` figée. L'instance peut avoir des **adaptations locales** (overrides) stockées séparément. |
| Suppression | « Suppression contrôlée » ? | **Soft delete** partout ; suppression physique interdite pour tout ce qui est publié ou référencé. Archivage à la place. |
| Identité d'un agent | Comment distinguer Claude Code de Codex ? | Chaque `Integration` possède son propre jeton ; `kind` ∈ {opencode, claude_code, codex, other}. L'identité vient du jeton, jamais d'un champ déclaré par le client. |
| Conflit de sync | Que fait-on si une Skill est modifiée des deux côtés ? | Un import externe crée toujours une **proposition** (`Proposal`, §4.4) basée sur une version parente ; la fusion est humaine. Pas de merge automatique au MVP. |
| Taille des Skills | Limites ? | 5 Mo par fichier, 50 Mo par version, 500 fichiers max (configurable). Fichiers binaires autorisés mais non éditables dans Skills Studio. |
| Dépendances d'une Skill | Que signifie « cette Skill utilise l'outil X » ? | Un `requirement` **dans le manifeste** (donc dans l'empreinte). Package, outil système ou service : **simplement déclaré dans la Skill** (jamais importé ni copié). Script : référence `(slug, version, sha256)` vers le catalogue. Changer une exigence = nouvelle version de Skill. |
| Script | Où vit un script ? | Dans **le catalogue**, versionné (SemVer, immuable à la publication). Deux voies d'entrée : **copie à l'import** (origine conservée : URL + commit) ou **création directe** dans le catalogue. Jamais de référence distante : elle rendrait une version « immuable » dépendante d'un contenu qui peut changer ou disparaître. |
| Installation des outils | Qui installe, et où ? | L'agent qui utilise la Skill, **s'il le décide**, **dans le projet en cours** (jamais dans l'application). L'application ne fournit aucune commande d'installation. |
| Suggestions de l'application | Comment éviter que l'application devienne un agent ? | Mécanisme `Proposal` unique ; sources de proposition = moteur de règles déterministe ou agent externe via MCP (§6.2). |
| Conventions de projet | L'application peut-elle les faire respecter ? | Elle les **stocke de façon structurée, les expose et trace la conformité déclarée**. Le respect pendant l'exécution reste du ressort de l'agent (§6.5). |

---

## 2. Stack recommandée

Le choix de départ du cahier des charges (React/TS + FastAPI + PostgreSQL) est **le bon**. Les ajustements portent sur les outils périphériques et sur ce qu'il faut *ne pas* mettre au MVP.

### 2.1 Backend

| Besoin | Choix | Justification | Alternative écartée |
|---|---|---|---|
| Langage / runtime | **Python 3.12+** | Cohérent avec ton profil (ML, sécurité), écosystème MCP Python mature. | Go/Node : gain marginal, coût de contexte. |
| Framework | **FastAPI** + Pydantic v2 | OpenAPI natif, validation stricte, génération de client TypeScript. | Django : plus lourd, ORM moins adapté à un design en Clean Architecture. |
| ORM | **SQLAlchemy 2.x** (style 2.0, typé) en mode **async** + `psycopg` 3 | Cohérent avec le cahier des charges ; async utile pour MCP/SSE. | SQLModel : abstraction qui masque trop SQLAlchemy. |
| Migrations | **Alembic** | Standard. Les triggers d'immutabilité sont versionnés en migrations SQL. | — |
| Base | **PostgreSQL 16** | JSONB, full-text, triggers, contraintes d'exclusion, `pg_trgm`. | SQLite : insuffisant pour concurrence et triggers de garde. |
| Recherche | **FTS PostgreSQL** (`tsvector` + `pg_trgm`) | Suffisant pour Skills/documents au volume attendu. `pgvector` en évolution ultérieure si recherche sémantique. | Elasticsearch/Meilisearch : sur-ingénierie. |
| Tâches de fond | **Aucune au MVP** ; si besoin → `procrastinate` (file sur Postgres) | Évite Redis. | Redis + Celery/RQ/arq. |
| Auth UI | Sessions courtes (JWT d'accès ~15 min) + refresh token en cookie `HttpOnly`/`SameSite=Strict` ; hash **argon2id** | Bonnes pratiques OWASP. | Auth tierce : inutile en mono-utilisateur. |
| Auth intégrations | **Jetons d'API opaques** (`whub_...`), stockés **hachés** (SHA-256), avec scopes, expiration, révocation | Un jeton par environnement connecté ; identité traçable. OAuth 2.1 pour MCP distant = évolution. | JWT longue durée : non révocable proprement. |
| MCP | **SDK MCP officiel Python** (FastMCP), transports **stdio** (local) et **Streamable HTTP** (distant) | Standard ouvert, compatible Claude Code / OpenCode / Codex. | Implémentation maison du protocole. |
| CLI | **Typer** + `httpx` | Appelle l'API REST uniquement (principe du cahier des charges). | Click brut : moins ergonomique. |
| SemVer | Bibliothèque `semver` | Comparaison/validation fiables. | Regex maison. |
| Contraintes de packages | Bibliothèque `packaging` (spécificateurs PEP 440) pour PyPI ; `semver` pour npm | Validation des contraintes **facultatives** des exigences. | Parsing maison. |
| Analyse de scripts importés | Module standard `ast` (Python) pour détecter imports réseau, sous-processus, accès fichiers | Extraction des effets probables, sans exécuter le script. | Exécution en bac à sable : hors périmètre. |
| Vérification de registres | `httpx` vers PyPI/npm, **asynchrone, optionnel, P2** | Confirmer l'existence d'un package et alerter sur un nom proche d'un package populaire. | Dépendance forte au réseau. |
| Diff de versions | `difflib` côté serveur (texte) + diff Monaco côté UI | Suffisant pour fichiers texte. | — |
| Gestion de paquets | **uv** | Rapide, lockfile reproductible. | pip/poetry. |
| Qualité | **ruff** (lint + format), **pyright** ou mypy strict, **import-linter** | `import-linter` impose les frontières de modules (D5). | — |
| Tests | **pytest**, `pytest-asyncio`, **testcontainers-python** (Postgres réel), `hypothesis` pour le versionnage | Tests sur une vraie base : les triggers et contraintes sont testés. | Mocks de DB : masquent les vrais bugs. |
| Logs / observabilité | **structlog** (JSON) + `request_id` ; OpenTelemetry en option | Traçabilité des actions externes. | — |

### 2.2 Frontend

| Besoin | Choix | Justification |
|---|---|---|
| Build | **Vite** + React 18/19 + **TypeScript strict** | SPA : pas besoin de SSR pour une application interne. Next.js serait inutile ici. |
| Routing | **TanStack Router** (ou React Router 7) | Routes typées. |
| Données serveur | **TanStack Query** | Cache, invalidation, états de chargement. |
| Client API | **openapi-typescript** + `openapi-fetch` générés depuis l'OpenAPI FastAPI | Contrat unique backend ↔ frontend, pas de types écrits à la main. |
| UI | **Tailwind CSS** + **shadcn/ui** (Radix) | Composants accessibles, copiés dans le dépôt, sans verrou. |
| Formulaires | **React Hook Form** + **Zod** | Validation typée. |
| Éditeur Skills Studio | **Monaco Editor** (édition + `DiffEditor` pour la comparaison de versions) | Couvre éditeur de fichiers et diff avec un seul composant. |
| Arborescence de fichiers | `react-arborist` | Vue de la structure d'une Skill. |
| Tests | **Vitest** + Testing Library ; **Playwright** pour 3-4 parcours E2E critiques | — |
| Graphiques dashboard | **Recharts** | Suffisant. |

### 2.3 Infrastructure

| Besoin | Choix |
|---|---|
| Conteneurs | **Docker Compose** : `db` (Postgres), `api`, `web` (Nginx/Caddy servant le build), `backup` (cron `pg_dump`) |
| Reverse proxy / TLS | **Caddy** (TLS automatique, config minimale) |
| CI | **GitHub Actions** : lint, types, tests (Postgres service), `import-linter`, `pip-audit`, `npm audit`, build Docker |
| Secrets | Variables d'environnement via `.env` non versionné ; `pydantic-settings` ; jamais de secret dans la base en clair |
| Sauvegardes | `pg_dump` quotidien chiffré + test de restauration automatisé en CI hebdomadaire |
| Hébergement de départ | VPS unique (Hetzner/OVH/Contabo) ou machine locale ; pas de Kubernetes |

### 2.4 Ce qu'on n'ajoute volontairement pas (et quand le reconsidérer)

| Technologie | Raison du report | Déclencheur de réévaluation |
|---|---|---|
| Redis | Aucun besoin avéré | Rate limiting distribué ou files lourdes |
| S3 / MinIO | Postgres suffit pour des Skills (fichiers texte, quelques Mo) | Livrables volumineux (>100 Mo) |
| Microservices | Cahier des charges : à éviter | Jamais au MVP |
| Elasticsearch | FTS Postgres suffisant | >100k documents |
| WebSockets | SSE/polling suffisants pour le dashboard | Collaboration temps réel |
| OAuth 2.1 complet | Jetons scopés suffisent en mono-utilisateur | Exposition publique du serveur MCP |

---

## 3. Architecture

### 3.1 Style

**Monolithe modulaire**, Clean Architecture par module : `domain` (entités, règles) → `application` (cas d'usage) → `infrastructure` (SQLAlchemy, fichiers) → `interfaces` (REST, MCP, CLI).

Règle centrale : **REST, MCP et CLI n'embarquent aucune logique métier.** Ils traduisent un protocole vers un cas d'usage de la couche `application`.

```text
            ┌───────────── Frontend React ─────────────┐
            │                                          │
   CLI ──► REST /api/v1 ◄─────────────────────────── MCP (stdio / HTTP)
            │                                          │
            └──────────────┬───────────────────────────┘
                           ▼
                 Couche application (cas d'usage)
                 + Autorisation (Principal + scopes)
                           ▼
   ┌───────────┬───────────┬───────────┬───────────┬───────────┐
   │  skills   │ projects  │   plans   │ competen- │ execution │
   │           │ missions  │           │ cies/roles│ tracking  │
   └───────────┴───────────┴───────────┴───────────┴───────────┘
                           ▼
              Infrastructure : PostgreSQL (+ blobs adressés par contenu)
```

### 3.2 Structure du dépôt

```text
workhub/
├── backend/
│   ├── pyproject.toml          # uv, ruff, pyright, import-linter
│   ├── alembic/                # migrations (inclut triggers SQL)
│   ├── src/workhub/
│   │   ├── shared/             # kernel : Principal, erreurs, horloge, ids, pagination
│   │   ├── iam/                # users, sessions, api_tokens, scopes
│   │   ├── skills/             # domain / application / infrastructure
│   │   ├── projects/           # projets + missions
│   │   ├── plans/              # templates, versions, instances
│   │   ├── competencies/       # compétences + rôles
│   │   ├── execution/          # tâches, exécutions, livrables, blocages
│   │   ├── knowledge/          # ressources documentaires
│   │   ├── tools/              # catalogue de scripts et leurs versions
│   │   ├── proposals/          # mécanisme générique de propositions
│   │   ├── integrations/       # environnements connectés, déploiements de skills
│   │   ├── audit/              # journal append-only
│   │   └── interfaces/
│   │       ├── rest/           # routers FastAPI (/api/v1)
│   │       └── mcp/            # serveur MCP
│   └── tests/                  # unit / integration / contract / security
├── cli/                        # package `workhub-cli` (Typer, httpx)
├── frontend/                   # Vite + React + TS
├── deploy/                     # docker-compose, Caddyfile, backup
├── docs/
│   ├── adr/                    # décisions d'architecture (1 fichier / décision)
│   ├── specs/
│   └── integrations/           # guides OpenCode / Claude Code / Codex
└── .github/workflows/
```

### 3.3 Règles d'architecture imposées (import-linter)

1. `domain` n'importe rien d'extérieur (ni SQLAlchemy, ni FastAPI).
2. `application` n'importe pas `infrastructure` ni `interfaces`.
3. Un module n'importe un autre module **que via son API publique** (`workhub.<module>.api`), jamais ses internals.
4. `interfaces.rest`, `interfaces.mcp` et `cli` ne parlent qu'à `application`.
5. `cli` ne dépend **pas** du package backend : uniquement HTTP.

### 3.4 ADR à rédiger (un fichier court chacun, dès M0)

| ADR | Sujet |
|---|---|
| 001 | Monolithe modulaire et règles de dépendance |
| 002 | Stockage des blobs de Skills dans PostgreSQL, adressage par SHA-256 |
| 003 | Manifeste et empreinte d'une SkillVersion (**incluant le bloc `requirements`**) |
| 004 | Modèle d'identité : Principal, intégrations, jetons, scopes |
| 005 | MCP comme adaptateur (transports, séparation lecture/écriture) |
| 006 | Brouillons mutables vs versions immuables |
| 007 | Modèle de plan : template / version / instance / overrides |
| 008 | Stratégie de suppression : soft delete et archivage |
| 009 | Gestion de la concurrence : verrouillage optimiste (`ETag` / `If-Match`) |
| 010 | Catalogue d'outils : types, exigences, copie des scripts, rôle des signatures |
| 011 | Mécanisme `Proposal` et absence de LLM embarqué |
| 012 | Profil technique de projet : instantané immuable |

---

## 4. Modèle de données — invariants à faire respecter par la base

Le schéma complet sera produit en tâche `E0-06`. Voici les entités critiques et les **invariants garantis au niveau SQL** (pas seulement applicatif).

### 4.1 Skills

```text
skill(id, slug UNIQUE, owner_id, domain, status_logical, created_at, archived_at)
skill_draft(id, skill_id, base_version_id NULL, updated_at, lock_version)
skill_draft_file(draft_id, path, blob_sha256, mode)
blob(sha256 PK, size, content BYTEA, created_at)            -- append-only
skill_version(id, skill_id, semver, manifest JSONB, manifest_sha256,
              parent_version_id NULL, status, changelog, author_principal_id,
              origin {app|integration:<id>}, created_at, published_at,
              test_results JSONB NULL,
              UNIQUE(skill_id, semver))
skill_version_file(version_id, path, blob_sha256, size, mode)
skill_dependency(version_id, depends_on_skill_id, constraint)
-- les propositions de modification de Skill passent par la table générique `proposal` (§4.4)
skill_deployment(integration_id, skill_id, version_id, deployed_at, last_seen_at)
project_skill_pin(project_id, skill_id, version_id)
```

**Invariants imposés par triggers/contraintes :**

| Invariant | Mécanisme |
|---|---|
| Une version `published`, `deprecated` ou `archived` n'est plus modifiable (ni elle, ni ses fichiers) | Trigger `BEFORE UPDATE/DELETE` sur `skill_version` et `skill_version_file` (seuls `status` autorisé : `published → deprecated → archived`) |
| Un blob n'est jamais modifié | Trigger `BEFORE UPDATE` → exception ; `DELETE` interdit sauf GC explicite |
| `UNIQUE(skill_id, semver)` | Contrainte |
| Un SemVer publié doit être strictement supérieur à la dernière version de même lignée (ou autorisé comme patch sur ancienne branche, règle à fixer dans l'ADR 003) | Vérification applicative + test property-based |
| `manifest_sha256` = hash recalculé du manifeste (blocs `files`, `dependencies` et `requirements` inclus) | Recalcul à la publication + test de vérification à l'export |
| Épinglage : `version_id` appartient bien à `skill_id` | Clé étrangère composite |

### 4.2 Plans

```text
work_plan_template(id, category {A|B|C|D}, slug, owner_id)
work_plan_version(id, template_id, semver, content JSONB, status, created_at)   -- immuable une fois publiée
work_plan_instance(id, template_version_id, project_id/mission_id, state, started_at)
instance_node(id, instance_id, path, node_type {phase|activity|task|subtask},
              status, overrides JSONB, ...)
```

Invariant : `work_plan_instance.template_version_id` est **figé** ; changer de version = opération explicite `migrate_instance` journalisée.

### 4.3 Identité, intégrations, audit

```text
integration(id, name, kind, owner_id, created_at, revoked_at)
api_token(id, integration_id, token_sha256, scopes TEXT[], expires_at, last_used_at, revoked_at)
audit_log(id, at, principal_type, principal_id, integration_id NULL,
          action, resource_type, resource_id, request_id, outcome, details JSONB)
execution_record(id, task_id, plan_version_id, executor {human|integration}, executor_id,
                 skill_versions JSONB, requirement_resolution JSONB NULL, started_at, finished_at, outcome, validation JSONB)
```

Invariant : `audit_log` est **append-only** (trigger interdisant `UPDATE`/`DELETE`).

### 4.4 Outils, propositions et profil technique de projet

```text
tool(id, slug UNIQUE, name, kind {script},                -- catalogue : scripts uniquement (kind extensible)
     origin {import|created}, origin_ref NULL,             -- URL + commit pour un import
     notes, archived_at)
tool_version(id, tool_id, version SEMVER, manifest_sha256,    -- scripts : toujours versionnés
             signature JSONB,                                 -- interface + effets déclarés
             status, created_at, published_at)
tool_version_file(tool_version_id, path, blob_sha256, size, mode)

-- Exigences : index dérivé du manifeste de la version de Skill (source de vérité = manifeste).
-- Packages, outils système et services sont SEULEMENT déclarés ici : aucune ligne dans `tool`.
skill_requirement(skill_version_id, kind {package|system|service|script},
                  ecosystem NULL {pypi|npm|cargo|maven|...}, name NULL,   -- package / système / service
                  constraint NULL, pinned_version NULL, hashes JSONB NULL, -- facultatifs (packages)
                  check_command NULL,                                      -- outils système
                  tool_version_id NULL,                                    -- script : référence au catalogue
                  usage {required|optional}, note NULL)

project_technology(project_id, kind, name, ecosystem NULL, tool_id NULL,   -- déclaré dans le projet, hors catalogue
                   status {proposed|accepted|modified|rejected}, rationale, decided_at)
project_skill_allowlist(project_id, skill_id)
project_convention(project_id, key, rule JSONB, verifiable BOOL)
proposal(id, target_type {skill_update|project_technology|project_skill|competency|plan_structure},
         target_id NULL, payload JSONB, status {proposed|accepted|modified|rejected},
         proposed_by_principal_id, decided_by NULL, decided_at NULL, decision_note NULL)
project_profile_snapshot(id, project_id, content JSONB, sha256, created_at)   -- immuable
```

**Invariants imposés :**

| Invariant | Mécanisme |
|---|---|
| Une `tool_version` publiée (script) est immuable, comme une `skill_version` | Mêmes triggers que §4.1 |
| Le script contenu dans une `tool_version` ne change jamais de hash | Blobs append-only + recalcul du `manifest_sha256` à l'export |
| `skill_requirement` est cohérent avec le manifeste de sa version | Régénéré à la publication + test d'égalité |
| Un `project_profile_snapshot` n'est jamais modifié | Trigger `BEFORE UPDATE/DELETE` |
| Une `proposal` décidée (`accepted`/`modified`/`rejected`) ne revient pas à `proposed` | Machine à états + contrainte de transition |
| Une proposition émise par un jeton d'intégration ne peut pas être décidée par ce même jeton | Contrôle `proposed_by ≠ decided_by` côté `application` |

---

## 5. Versionnage et intégrité des Skills

### 5.1 Manifeste et empreinte

Chaque version possède un manifeste canonique (JSON trié, UTF-8, sans espaces superflus) :

```json
{
  "slug": "web-pentest",
  "semver": "1.2.0",
  "parent": "1.1.0",
  "files": [
    {"path": "SKILL.md", "sha256": "…", "size": 4210, "mode": "0644"},
    {"path": "references/methodology.md", "sha256": "…", "size": 9120, "mode": "0644"}
  ],
  "dependencies": [{"slug": "reporting-base", "constraint": ">=1.0.0 <2.0.0"}],
  "requirements": [
    {"kind": "package", "ecosystem": "pypi", "name": "python-nmap"},
    {"kind": "script", "slug": "parse-nmap-xml", "version": "1.0.0", "sha256": "…"},
    {"kind": "system", "name": "nmap", "install": "manual", "check": "nmap --version"}
  ]
}
```

`manifest_sha256 = SHA-256(manifeste canonique)`. Toute modification d'un fichier change le hash du manifeste : l'intégrité d'une version entière se vérifie avec une seule empreinte, côté application comme côté agent (export + vérification). Les `requirements` faisant partie du manifeste, **modifier une exigence d'outil produit une nouvelle version de Skill**.

### 5.2 Cycle de vie et transitions autorisées

```text
Draft ──► Review ──► Published ──► Deprecated ──► Archived
   ▲          │
   └──────────┘  (rejet de la review)
```

| Transition | Qui | Contrôles |
|---|---|---|
| Draft → Review | auteur | Validation de structure (SKILL.md + frontmatter valide, chemins sûrs, tailles) |
| Review → Published | utilisateur humain avec scope `skills:publish` | Choix SemVer cohérent, changelog obligatoire, empreinte calculée, version immuable |
| Published → Deprecated | humain | Message de dépréciation + version de remplacement conseillée |
| Deprecated → Archived | humain | Lecture seule, conservée pour l'historique |
| *Rollback* | humain | Crée une **nouvelle** version (contenu d'une ancienne) — jamais de retour en arrière destructif |

**Un jeton d'intégration ne possède jamais `skills:publish` par défaut** (principe non négociable n°11).

### 5.3 Validations à la publication

- Chemins : pas de `..`, pas de chemin absolu, pas de lien symbolique, UTF-8 normalisé, casse unique.
- `SKILL.md` présent, frontmatter YAML valide (`name` = slug, `description` non vide).
- Limites de taille et de nombre de fichiers.
- Détection basique de secrets (regex clés API/tokens) → avertissement bloquant à confirmer.
- Résolution des dépendances (pas de cycle, contraintes satisfaisables).
- Chaque `requirement` de type package : écosystème supporté et nom valide ; contrainte de version **facultative** (validée si fournie : PEP 440 pour PyPI, SemVer pour npm) ; existence sur le registre vérifiée si possible (avertissement sinon).
- Chaque `requirement` de type script : `tool_version` **publiée** dans le catalogue, SHA-256 concordant.
- Chaque `requirement` de type système/service : `install: manual` et commande `check` renseignées.

### 5.4 Exigences d'une Skill : packages, outils système, scripts

Une Skill déclare ses **exigences** dans son manifeste. **Seuls les scripts passent par le catalogue.**

| Type | Où est-ce décrit ? | Ce qu'on enregistre | Exemple |
|---|---|---|---|
| `package` (Python, Rust, Java, JS…) | **Uniquement dans la Skill** : jamais importé ni copié dans le catalogue | Écosystème + nom réel (contrainte de version facultative) | `pypi : python-nmap` |
| `system` | Uniquement dans la Skill | Nom + commande de vérification | `nmap` (`nmap --version`) |
| `service` | Uniquement dans la Skill | Nom, prérequis ou licence (non installable par un agent) | Burp Suite |
| `script` | **Catalogue** (copié à l'import ou créé directement, versionné : §5.5) | `(slug, version, sha256)` | `parse-nmap-xml` |

Pour un package, **l'écosystème et le nom réel suffisent**. Le versionnage SemVer est porté par la **Skill** (§5.2), pas par ses packages.

| Champ d'un package | Exemple | Statut |
|---|---|---|
| `ecosystem` | `pypi`, `npm`, `cargo`, `maven`… | obligatoire |
| `name` | `python-nmap` | obligatoire |
| `version_constraint` | `>=1.0,<2.0` | facultatif |
| `pinned_version` | `1.0.3` | facultatif |
| `hashes` | SHA-256 des artefacts | facultatif |

**Saisie dans Skills Studio.** Une exigence de type package, système ou service se saisit directement dans le formulaire de la Skill. L'autocomplétion s'appuie sur les exigences déjà utilisées par d'autres Skills (index dérivé, sans entité supplémentaire). Un script se sélectionne dans le catalogue, ou s'y crée / s'y importe sur place.

**Traçabilité.** Sans contrainte de version, le comportement d'une Skill peut évoluer avec ses dépendances. L'agent peut donc déclarer, dans l'`ExecutionRecord`, la **résolution de chaque exigence** (déjà présente, installée avec sa version, ignorée, indisponible) : un résultat anormal peut être relié à une dérive de dépendance, sans bloquer la publication.

### 5.5 Scripts : catalogue, versions, empreinte et signature

Le catalogue d'outils ne contient **que des scripts** : ils y vivent et nulle part ailleurs. Deux voies d'entrée :

- **Import** : copie du fichier dans l'instance (blobs adressés par SHA-256), origine conservée (URL + commit).
- **Création directe** dans le catalogue (éditeur de Skills Studio).

Un script n'est jamais référencé à distance et jamais exécuté par l'application.

**Versionnage.** Chaque script est versionné en SemVer, comme une Skill : un brouillon mutable, puis une publication qui crée une `tool_version` **immuable**. Modifier un script publié produit une nouvelle version. Une Skill référence un script par `(slug, version, sha256)` : une Skill publiée reste donc liée à un contenu exact.

**Empreinte et signature.**

| Élément | Contenu | Rôle |
|---|---|---|
| **SHA-256** | Empreinte du manifeste du script (fichiers + métadonnées) | L'agent vérifie qu'il exécute exactement le script validé |
| **Signature** | Interface (interpréteur, point d'entrée, arguments, entrées/sorties, codes de retour) + effets déclarés (réseau, écriture disque, sous-processus, variables d'environnement lues) | L'agent sait appeler le script sans lire son code ; la revue humaine sait ce qu'il fait |
| Signature cryptographique (minisign / Sigstore) | Authenticité de l'auteur | Plus tard, si les scripts circulent hors de l'instance |

Les effets déclarés restent **déclaratifs** : l'application ne peut pas prouver qu'un script les respecte. Elle détecte seulement les écarts évidents (un script déclarant « aucun réseau » mais important `requests`) et les signale comme avertissement lors de la revue.

```json
{
  "slug": "parse-nmap-xml", "version": "1.0.0", "sha256": "…",
  "signature": {
    "interpreter": "python>=3.10", "entrypoint": "parse_nmap_xml.py",
    "args": [{"name": "input", "type": "path", "required": true}],
    "outputs": [{"name": "stdout", "format": "json"}],
    "exit_codes": {"0": "ok", "2": "fichier invalide"},
    "declared_effects": {"network": false, "writes": ["stdout"], "subprocess": false, "env_read": []}
  },
  "requirements": [{"kind": "package", "ecosystem": "pypi", "name": "defusedxml"}]
}
```

**Portabilité.** À l'export d'une Skill, les scripts référencés sont inclus dans son dossier `scripts/` (compatibilité Agent Skills). À l'import d'une Skill contenant un dossier `scripts/`, chaque script est importé dans le catalogue (copie), puis référencé par la Skill. Il n'existe donc qu'une seule source de vérité pour un script.

### 5.6 Distribution aux agents : l'application déclare, l'agent décide

Le serveur MCP expose `get_skill_requirements` ; la réponse est une liste structurée de **déclarations** :

```json
{
  "skill": "web-pentest", "version": "1.2.0",
  "requirements": [
    {"kind": "package", "ecosystem": "pypi", "name": "python-nmap", "usage": "required"},
    {"kind": "script", "slug": "parse-nmap-xml", "version": "1.0.0", "sha256": "…",
     "download": "tool://parse-nmap-xml@1.0.0"},
    {"kind": "system", "name": "nmap", "check": "nmap --version"}
  ]
}
```

Règles :
- L'application **déclare** ce qu'une Skill suppose. Elle ne fournit **aucune commande d'installation** et n'installe rien.
- L'agent qui utilise la Skill **décide**, pour chaque package, de l'installer ou non. L'installation se fait **dans le projet en cours** (environnement virtuel Python, `node_modules`, `Cargo.toml`, Maven/Gradle…), jamais dans l'application ni sur son serveur. Un package déjà présent dans le projet n'a pas à être réinstallé.
- Installer un package revient à exécuter du code tiers : la confirmation relève de la **politique de l'environnement de l'agent** (OpenCode, Claude Code, Codex) et de l'utilisateur. Cela sera documenté dans les guides d'intégration (E8-05).
- Un script est la **seule ressource que l'application fournit** : il se télécharge par son empreinte et se vérifie par SHA-256 avant usage. L'agent décide aussi de l'importer ou non dans le projet.
- La commande `check` d'un outil système ou service est une aide à la vérification, exécutée par l'agent.
- La résolution de chaque exigence est **déclarée par l'agent** dans l'`ExecutionRecord` (facultatif, recommandé).

---

## 6. Création de projet assistée et propositions

### 6.1 Vocabulaire : outil, Skill, plan, tâche

| Concept | Définition | Exemple |
|---|---|---|
| Outil | Logiciel, package, script ou ressource technique utilisé pour travailler | Nmap |
| Skill | Procédure structurée expliquant comment accomplir une tâche | Reconnaissance réseau avec Nmap |
| Plan | Organisation méthodologique du travail | Réaliser un audit de sécurité réseau |
| Tâche | Action concrète à réaliser | Identifier les ports ouverts du serveur cible |

Les exigences (packages, outils système, scripts) sont rattachées aux Skills (§5.4). Un projet **hérite** de celles de ses Skills épinglées et peut déclarer ses propres technologies (`project_technology`).

### 6.2 Le principe de proposition

Tout ce que l'application « suggère » (outil, compétence, Skill, structure de plan) est un **`Proposal`** à quatre états : **proposé → accepté / modifié / rejeté**. La décision est humaine et journalisée ; rien n'entre dans le référentiel validé sans passer par là.

Sources de proposition possibles :
1. **Un moteur de règles déterministe** (règles déclaratives : type de projet → technologies, Skills et modèles de plan) — hors MVP (E15-09).
2. **Un agent externe**, via l'outil MCP `propose_project_structure` (scope `projects:propose`), qui n'écrit que des `Proposal`.
3. **L'utilisateur** lui-même.

L'application **n'embarque aucun appel à un modèle de langage** (D8) : sinon la règle « jamais dépendante d'un fournisseur de modèle » tomberait.

### 6.3 Assistant de création en étapes

Plutôt qu'un formulaire unique : un assistant en étapes, **sauvegardable à tout moment** (statut « idée »), dont tous les champs techniques sont facultatifs.

| Étape | Contenu | Jalon |
|---|---|---|
| 1 — Informations générales | Nom, description, catégorie, type, objectif principal, priorité, statut, dates | M3b |
| 2 — Objectifs et livrables | Objectifs secondaires, livrables attendus | M3b |
| 3a — Compétences et outils déclarés | Compétences disponibles / à acquérir (étiquettes libres tant que le module Compétences n'existe pas), technologies et outils envisagés (`project_technology`, déclarés dans le projet, hors catalogue) | M3b |
| 4 — Environnement technique | Langages, frameworks, bases de données, architecture, dépôt Git, déploiement, contraintes (tous facultatifs) | M3b |
| 5 — Méthodologie et plan | Plan proposé depuis un modèle ; chaque phase acceptée, modifiée ou rejetée | M4 |
| 3b — Analyse d'écart de compétences | Compétences manquantes et pistes d'acquisition | post-1.0 (P2) |

Après validation, les missions, phases et tâches sont créées **uniquement à partir des éléments acceptés ou modifiés** (E15-07).

### 6.4 Profil technique du projet

Chaque projet possède un **profil technique** figé sous forme d'instantané immuable (`project_profile_snapshot`, avec `sha256`) :

- compétences requises ;
- outils et technologies ;
- Skills associées **et leurs versions épinglées** ;
- documents de référence ;
- contraintes et conventions ;
- architecture ;
- plans de travail, missions et tâches.

`get_project_context` renvoie le dernier instantané et son empreinte ; chaque `ExecutionRecord` référence l'instantané utilisé. Un nouvel instantané est produit à la validation d'une proposition ou sur action explicite « figer le profil », **pas à chaque modification** (sinon on perdrait l'intérêt d'un contexte stable). Deux agents connectés au même projet lisent donc exactement le même contexte, et on peut le vérifier par l'empreinte.

### 6.5 Ce que l'application peut et ne peut pas imposer

| L'application peut imposer | Ce qui relève de l'agent |
|---|---|
| Allowlist de Skills par projet et versions épinglées | Respecter les conventions pendant l'exécution |
| Scopes et périmètre de projet des jetons ; refus des écritures hors périmètre | Ne pas exécuter de commandes non voulues |
| Conventions stockées sous forme structurée et vérifiable | Appliquer réellement le linter, les seuils de tests, etc. |
| Déclaration de conformité obligatoire dans chaque `ExecutionRecord` | Dire la vérité dans cette déclaration |
| Traçabilité de l'écart « convention ↔ conformité déclarée » | — |

L'application **détecte et trace** ; elle ne contraint pas l'exécution. Ce point doit rester explicite dans le cahier des charges plutôt qu'implicite.

---

## 7. Modèle de permissions

### 7.1 Scopes (granulaires, séparés lecture / écriture)

| Domaine | Lecture | Écriture |
|---|---|---|
| Projets | `projects:read` | `projects:write` |
| Tâches | `tasks:read` | `tasks:create`, `tasks:update_status` |
| Plans | `plans:read` | `plans:write` |
| Skills | `skills:read` | `skills:propose`, `skills:publish` (**humain uniquement par défaut**) |
| Documents | `docs:read` | `docs:write` |
| Outils | `tools:read` | `tools:write`, `tools:propose` ; `tools:publish` (scripts) **humain uniquement** |
| Propositions de structure | — | `projects:propose` (écrit uniquement des `Proposal` à l'état « proposé ») |
| Livrables | — | `deliverables:upload` |
| Exécution | `execution:read` | `execution:report` (dont blocages) |
| Admin | — | `integrations:manage`, `projects:delete` (**jamais** accordés aux jetons d'intégration par défaut) |

### 7.2 Règles

- **Contrôle d'accès par projet** : un jeton peut être restreint à une liste de projets (`token_project_scope`).
- Chaque requête résout un `Principal` (utilisateur ou intégration) ; l'autorisation est vérifiée dans la couche `application`, **jamais** dans les routers.
- Chaque action d'écriture produit une ligne d'`audit_log` dans la même transaction.
- Jetons : affichés une seule fois, stockés hachés, expiration optionnelle, révocation immédiate, `last_used_at` tracé.
- Journalisation : aucun secret ni contenu complet de Skill dans les logs.

### 7.3 Menaces spécifiques à surveiller

| Menace | Contre-mesure |
|---|---|
| Injection de prompt via Skill/tâche/document modifié | Contenu d'origine externe marqué `origin=integration`, jamais publié sans revue ; hash affiché lors des diffs |
| Jeton volé | Scopes minimaux, expiration, révocation, alerte sur usage anormal |
| Path traversal à l'import de Skill (zip/tar) | Extraction sécurisée, validation de chemin, limites de taille (anti zip-bomb) |
| IDOR sur l'API | Tests de permissions systématiques par ressource et par principal |
| Course sur publication de versions | Verrouillage optimiste + contrainte `UNIQUE(skill_id, semver)` |
| Exposition publique du MCP HTTP | Bind local par défaut ; TLS + jetons si exposé |
| Chaîne d'approvisionnement via les packages déclarés (typosquatting, version compromise) | Skill revue par un humain avant publication ; avertissement sur les noms proches de packages populaires (P2) ; contrainte, épinglage et hashes facultatifs ; l'agent décide d'installer sous sa politique de confirmation ; résolution réelle consignée dans l'`ExecutionRecord` |
| Script importé malveillant ou falsifié | Copie (pas de référence distante), SHA-256 vérifié à la livraison, analyse statique des effets, publication humaine uniquement, aucune exécution côté serveur |
| Exécution non voulue d'une installation | L'application ne fournit aucune commande d'installation et n'exécute rien ; l'agent décide et installe dans le projet en cours, sous la politique de confirmation de son environnement |

---

## 8. Roadmap et jalons

Estimation en **jours de travail** (1 j ≈ une session de ~4 h effectives). Taille : **S** = 0,5 j, **M** = 1 j, **L** = 2–3 j, **XL** = 4–5 j.

| Jalon | Semaines | Contenu | Livrable démontrable |
|---|---|---|---|
| **M0 — Fondations** | 1–2 | Dépôt, CI, Docker, IAM de base, ADR, schéma | `docker compose up` → login fonctionnel, CI verte |
| **M1 — Skills core + exigences déclaratives** | 3–7 | Blobs, brouillons, versions immuables, SemVer, manifeste avec `requirements`, déclaration des exigences (packages / système), import/export, API | Créer, publier, exporter `web-pentest` v1.0.0 → v1.1.0 (**Scénario C**) |
| **M2 — Jetons + MCP lecture + CLI minimale** | 8–9 | Intégrations, scopes, MCP read-only dont `get_skill_requirements` (exigences déclarées), `workhub skills ...` | **Démo : Claude Code/OpenCode récupère une Skill et ses exigences via MCP** |
| **M3 — Projets, missions, tâches, exécution** | 10–13 | Projets/missions, pins de Skills, tâches, statuts, livrables, MCP écriture, audit | **Scénarios B, E, G, H** |
| **M3b — Scripts, propositions, profil technique, assistant** | 14–17 | Catalogue de scripts + signatures, `tool_version`, `Proposal`, profil technique, assistant étapes 1-2-3a-4, conventions | **Scénario I** ; début du **Scénario J** |
| **M4 — Plans de travail** | 18–21 | Templates, versions, instances, nœuds, overrides ; `propose_project_structure`, génération missions/tâches, étape 5 de l'assistant | Un modèle réutilisé par 2 projets sans fuite d'état ; **Scénario J** complet |
| **M5 — Compétences, rôles, dashboard** | 22–23 | CRUD, preuves, rôles ↔ compétences, dashboard | **Scénario A** |
| **M6 — Sync, knowledge, durcissement** | 24–26 | Déploiements, propositions de Skills, conflits, documents, tests sécurité, sauvegardes, release | **Scénarios D, F**, version stable |

> **Estimation révisée.** L'ajout des exigences et du catalogue de scripts (~13 j) et des propositions / assistant de création (~14 j hors tâches P2) représente ~27 jours de travail, soit environ **6 semaines** à 4–5 sessions par semaine. Mon estimation précédente (+2 semaines) sous-évaluait cet impact. Levier si le calendrier glisse : reporter E15-06 à E15-08 après la 1.0 (≈ −1 semaine). E15-09 et E15-10 sont déjà hors MVP.

> **Pourquoi cet ordre diffère du cahier des charges.** Le cahier des charges propose Compétences → Projets → Plans → Skills. Avec cet ordre, le premier moment où un agent externe touche le système arrive après ~60 % du budget — c'est-à-dire trop tard pour découvrir qu'un choix MCP/versionnage est mauvais. Ici, le risque principal est mis à l'épreuve dès la semaine 8.

---

## 9. Backlog détaillé

Convention : `E<epic>-<n>`. **Dép.** = dépendances. Toutes les tâches incluent leurs tests unitaires ; les critères de fin sont vérifiables.

### E0 — Fondations (M0)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E0-01 | Initialiser le monorepo (backend, cli, frontend, deploy, docs), licence, README, CONTRIBUTING | S | — | Arborescence §3.2 en place |
| E0-02 | Config Python : uv, ruff, pyright strict, pytest, pre-commit | S | E0-01 | `uv run pytest` et lint passent |
| E0-03 | Configurer **import-linter** avec les 5 règles §3.3 + test qui échoue si une règle est violée | M | E0-02 | Violation volontaire détectée en CI |
| E0-04 | Docker Compose : Postgres + API + web ; healthchecks ; `.env.example` | M | E0-01 | `docker compose up` sain |
| E0-05 | CI GitHub Actions : lint, types, tests (Postgres service), import-linter, pip-audit, build | M | E0-03 | PR bloquée si rouge |
| E0-06 | Modèle de données v0 (diagramme + DDL des tables MVP) | L | — | Revu, cohérent avec §4 |
| E0-07 | Rédiger les ADR 001–009 (1 page chacun) | M | E0-06 | Fichiers dans `docs/adr/` |
| E0-08 | Noyau partagé : `Principal`, erreurs métier, horloge injectable, génération d'IDs, pagination, enveloppe d'erreur API | M | E0-02 | Utilisé par les 2 premiers modules |
| E0-09 | Alembic + base de test avec testcontainers + fixtures | M | E0-04 | Tests d'intégration sur vrai Postgres |
| E0-10 | Logging structuré + `request_id` + middleware d'erreurs | S | E0-08 | Chaque requête loguée en JSON |
| E0-11 | Squelette frontend : Vite, TS strict, Tailwind, shadcn, TanStack Router/Query, génération du client OpenAPI | M | E0-01 | Page vide appelle `/api/v1/health` typé |

### E1 — IAM : authentification et autorisations (M0 → M2)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E1-01 | Entité `User`, hash argon2id, création du premier admin via commande CLI d'amorçage | M | E0-09 | Pas de compte par défaut |
| E1-02 | Login : JWT d'accès court + refresh cookie `HttpOnly`, rotation, logout, expiration | L | E1-01 | Tests de session, de rotation, de rejet de token expiré |
| E1-03 | Protection brute-force (limitation de tentatives par IP/compte) | S | E1-02 | Verrouillage temporaire testé |
| E1-04 | Entités `Integration`, `ApiToken` (haché), scopes, expiration, révocation | L | E1-01 | Création → affichage unique → révocation |
| E1-05 | Résolution du `Principal` (session ou jeton) + décorateur d'autorisation côté `application` | M | E1-04 | 100 % des cas d'usage d'écriture déclarent un scope |
| E1-06 | Restriction de jeton par projet (`token_project_scope`) | M | E3-01 | Test d'accès refusé hors périmètre |
| E1-07 | **Matrice de tests de permissions** générée (ressource × scope × principal) | L | E1-05 | Tout nouvel endpoint sans test de permission fait échouer la CI |
| E1-08 | Journal d'audit append-only + trigger SQL + service `audit.record()` | M | E0-09 | `UPDATE`/`DELETE` sur `audit_log` échoue |
| E1-09 | Écrans login, gestion de session, page Intégrations (création/révocation de jetons) | L | E1-02, E1-04, E0-11 | Parcours E2E Playwright |

### E2 — Skills : cœur (M1) — **module prioritaire**

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E2-01 | Magasin de **blobs** adressés par SHA-256 (insert idempotent, lecture, trigger d'immutabilité) | M | E0-09 | Même contenu = 1 seul blob ; `UPDATE` impossible |
| E2-02 | Entités `Skill`, `SkillDraft`, `SkillDraftFile` ; CRUD de brouillon (fichiers, arborescence) | L | E2-01 | Lecture/écriture de fichiers d'un brouillon |
| E2-03 | **Validateur de structure** (SKILL.md, frontmatter, chemins sûrs, limites, détection de secrets) | L | E2-02 | Suite de cas invalides (path traversal, UTF-8, symlink, taille) |
| E2-04 | **Manifeste canonique + hash** (module pur, sans I/O), **bloc `requirements` inclus** | M | E2-01 | Tests property-based (`hypothesis`) : ordre des fichiers sans effet, 1 octet modifié = hash différent |
| E2-05 | `SkillVersion` immuable + `SkillVersionFile` + triggers SQL (interdits UPDATE/DELETE hors statut) | L | E2-04 | Tentative de modification directe en SQL rejetée |
| E2-06 | Cas d'usage **publier** : SemVer (MAJOR/MINOR/PATCH), changelog obligatoire, parent, empreinte | L | E2-05 | Scénario C : v1.0.0 puis v1.1.0 coexistent |
| E2-07 | Machine à états du cycle de vie (Draft/Review/Published/Deprecated/Archived) + transitions autorisées | M | E2-06 | Transitions interdites rejetées, testées |
| E2-08 | Comparaison de deux versions (diff fichiers ajoutés/modifiés/supprimés + diff texte) | M | E2-05 | Endpoint `GET /skills/{slug}/diff?from=&to=` |
| E2-09 | **Export** d'une version (archive `tar.gz`/zip + `manifest.json`) avec vérification d'empreinte | M | E2-05 | Export → ré-import = même hash |
| E2-10 | **Import** d'une Skill existante (dossier/zip) : extraction sécurisée, validation, création de brouillon | L | E2-03 | Import d'une Skill réelle (celles déjà utilisées dans Claude Code) |
| E2-11 | Dépendances entre Skills (déclaration, résolution, détection de cycle) | M | E2-06 | Cycle rejeté ; contrainte SemVer évaluée |
| E2-12 | Rollback = nouvelle version à partir du contenu d'une ancienne | S | E2-06 | Historique intact, nouvel SemVer |
| E2-13 | Recherche et filtres (FTS + `pg_trgm`, domaine, statut, tags) | M | E2-02 | Résultats pertinents sur 50 Skills de test |
| E2-14 | Contrat REST `/api/v1/skills/*` + OpenAPI + `ETag`/`If-Match` sur brouillons | L | E2-06 | Client TS régénéré, tests de contrat |
| E2-15 | **Skills Studio** (UI) : liste, arborescence, éditeur Monaco, validation, publication | XL | E2-14, E0-11 | Créer et publier une Skill depuis l'UI |
| E2-16 | Skills Studio : historique de versions, diff Monaco, export, rollback | L | E2-15, E2-08 | Parcours E2E |

### E3 — Projets et missions (M3)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E3-01 | Entité `Project` (champs du §Module 4 : objectifs, périmètre, contraintes, exigences FR/NFR, statut, priorité, type) + soft delete | L | E0-09 | CRUD API + tests |
| E3-02 | Historique des modifications d'un projet (via audit + vue chronologique) | M | E1-08, E3-01 | Chaque changement visible avec auteur |
| E3-03 | Entité `Mission` (objectif, contexte, périmètre, prérequis, livrables, critères de réussite, risques) | L | E3-01 | CRUD + rattachement projet ou rôle |
| E3-04 | **Épinglage de Skills** par projet (`project_skill_pin`) + règle « jamais de résolution implicite » | M | E2-06, E3-01 | **Scénario G** : publication v2.0.0 sans effet sur un projet épinglé |
| E3-05 | Détection des projets utilisant une version obsolète + proposition de migration explicite et journalisée | M | E3-04 | Liste « projets concernés » par version |
| E3-06 | Modèles de projets réutilisables (clone structurel) | M | E3-03 | Création d'un projet depuis un modèle |
| E3-07 | Contrat REST projets/missions | M | E3-03 | OpenAPI + tests de permissions |
| E3-08 | UI : liste, Project Workspace (présentation, spécifications, missions, Skills utilisées, historique) | XL | E3-07 | Parcours E2E « structurer un projet » (**Scénario B**) |

### E4 — Plans de travail (M4)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E4-01 | Schéma JSON du contenu d'un plan (Phase → Activité → Tâche → Sous-tâche ; champs §6.2/6.3 du cahier des charges : objectif, *pourquoi*, *comment*, erreurs à éviter, critères d'acceptation, estimation, contrôles qualité) | L | E0-06 | Schéma Pydantic + JSON Schema versionné |
| E4-02 | `WorkPlanTemplate` + `WorkPlanVersion` immuable + catégories A/B/C/D | L | E4-01, E2-05 (réutiliser le pattern) | Publication d'une version de plan |
| E4-03 | Validation d'un plan : dépendances sans cycle, références de Skills valides | M | E4-02 | Graphe de dépendances testé |
| E4-04 | **Instanciation** : `WorkPlanInstance` référençant une version figée, nœuds d'exécution avec statut propre | L | E4-02, E3-03 | Même modèle utilisé par 2 projets : états indépendants (**critère Phase 6**) |
| E4-05 | **Overrides** locaux d'instance (adaptations sans modifier le modèle) | M | E4-04 | Modification locale invisible pour le modèle et les autres instances |
| E4-06 | Migration d'instance vers une nouvelle version de modèle (explicite, avec diff, journalisée) | M | E4-04 | Pas de migration silencieuse (test) |
| E4-07 | Calcul de progression (agrégation par phase/mission/projet) | M | E4-04 | Pourcentages corrects, testés |
| E4-08 | Bibliothèque initiale de plans (catégories A à D) à partir du document `plans-de-travail.pdf` | L | E4-02 | ≥1 plan réel par catégorie importé |
| E4-09 | UI : éditeur de plan (arbre), vue instance avec statuts, progression | XL | E4-07 | Parcours E2E |

### E5 — Compétences et rôles (M5)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E5-01 | `Competency` + catégories/domaines + niveau (théorique/pratique/opérationnel) + historique d'évolution | L | E0-09 | CRUD + historique |
| E5-02 | Preuves de maîtrise (liens vers projets, livrables, certifications) | M | E5-01, E3-01 | Preuve rattachée à une compétence |
| E5-03 | `ProfessionalRole` + `RoleCompetency` (niveau attendu) | L | E5-01 | Rôle ↔ compétences |
| E5-04 | Analyse d'écart rôle/compétences (compétences manquantes, niveau insuffisant) | M | E5-03 | Écran « écart » pour un rôle |
| E5-05 | Associations compétences ↔ Skills / projets / plans de développement | M | E5-01, E2-06, E4-02 | Navigation croisée |
| E5-06 | UI My Competencies + Professional Roles | L | E5-04 | **Scénario A** en E2E |

### E6 — API REST (transversal)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E6-01 | Conventions : `/api/v1`, pagination par curseur, filtres, tri, erreurs RFC 9457 (Problem Details), idempotence (`Idempotency-Key` sur écritures d'intégrations) | M | E0-08 | Document + tests |
| E6-02 | Stratégie de dépréciation d'API et politique de compatibilité | S | E6-01 | Documenté |
| E6-03 | Tests de contrat OpenAPI (schemathesis ou équivalent) en CI | M | E2-14 | Fuzzing de contrat vert |
| E6-04 | Limitation de débit par principal | S | E1-05 | 429 testé |

### E7 — Serveur MCP (M2 lecture → M3 écriture)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E7-01 | Squelette MCP (SDK Python), transport stdio + Streamable HTTP, authentification par jeton | L | E1-05 | Client MCP de test se connecte |
| E7-02 | Outils **lecture seule** v1 : `search_skills`, `get_skill`, `get_skill_version`, `compare_skill_versions` | L | E2-14, E7-01 | **Démo M2 : agent récupère une Skill** |
| E7-03 | Ressources MCP (`skill://slug@version`, `project://id`) | M | E7-02 | Lecture via resources |
| E7-04 | Outils lecture projet : `list_projects`, `get_project`, `get_project_context`, `get_project_tasks`, `get_task_details`, `get_work_plan`, `get_project_documents`, `get_execution_history` | L | E3-07, E4-04, E15-03 | `get_project_context` renvoie le profil technique figé (E15-03) ; retours bornés en taille |
| E7-05 | Outils **écriture** (module séparé, scopes distincts) : `create_task`, `update_task_status`, `upload_deliverable`, `add_project_note`, `report_blocker`, `propose_skill_update` | L | E7-04, E9-02 | Refus clair si scope manquant |
| E7-06 | Descriptions d'outils et schémas d'entrée rédigés pour être utilisables par un LLM (exemples, contraintes) | M | E7-05 | Test manuel avec Claude Code et OpenCode |
| E7-07 | Tests MCP automatisés (client scripté) : permissions, erreurs, bornes de taille | L | E7-05 | Suite en CI |
| E7-08 | Limite de taille/troncature des réponses et pagination côté outils | S | E7-04 | Aucune réponse > seuil configurable |

### E8 — Intégrations et synchronisation (M6)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E8-01 | `SkillDeployment` : enregistrer quelle version est consommée par quel environnement (via `get_skill_version` et heartbeat) | M | E7-02 | **Scénario D** : l'application sait que OpenCode utilise v1.1.0 |
| E8-02 | « Mise à jour disponible » + demande de validation humaine avant resynchronisation | M | E8-01 | Notification dans l'UI |
| E8-03 | Soumission d'une modification externe → `Proposal` de type `skill_update` (E15-01) basé sur une version parente | L | E2-10, E7-05, E15-01 | Une modification externe ne remplace jamais une version publiée |
| E8-04 | Détection de conflits (parent obsolète) + écran de comparaison + création d'une nouvelle version après validation | L | E8-03, E2-16 | Test de conflit à deux sources |
| E8-05 | Guides d'intégration et fichiers de configuration pour **OpenCode**, **Claude Code**, **Codex** (`docs/integrations/`) | L | E7-07 | Un tiers peut se connecter en <10 min |
| E8-06 | Test d'interopérabilité : 2 environnements simultanés sur le même projet (**Scénario F**) | M | E8-05, E9-02 | Pas de duplication de données |
| E8-07 | UI Integrations Workspace (identité, permissions, état, ressources visibles, historique, versions synchronisées) | L | E8-01, E1-09 | Parcours E2E |

### E9 — Suivi d'exécution et livrables (M3)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E9-01 | Entité `Task` (statuts : à faire, en cours, terminée, bloquée, en validation), assignation, commentaires, temps passé | L | E3-03 | Transitions valides testées |
| E9-02 | `ExecutionRecord` : exécutant (humain/intégration), version de plan, versions de Skills utilisées, **résolution des exigences déclarée par l'agent (présent / installé + version / ignoré / indisponible)**, résultat, validation des critères | L | E9-01, E2-05 | **Scénario H** : traçabilité complète |
| E9-03 | `Deliverable` : stockage (blobs), métadonnées, rattachement tâche/plan/projet, scan taille/type | L | E2-01, E9-01 | Upload via API et MCP |
| E9-04 | Blocages (`report_blocker`) + file « en attente de validation » | M | E9-01 | Visible dans le dashboard |
| E9-05 | Validation humaine des livrables (accepter/rejeter avec motif) | M | E9-03 | Statut tâche mis à jour |
| E9-06 | UI Execution Tracking | L | E9-05 | Parcours E2E |

### E10 — Knowledge (M6)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E10-01 | `KnowledgeResource` (types : note, spec, ADR, rapport, lien, retour d'expérience) + tags + versionnage documentaire | L | E0-09 | CRUD + historique |
| E10-02 | Relations N-N avec projets, missions, compétences, plans, Skills | M | E10-01 | Navigation bidirectionnelle |
| E10-03 | Recherche globale (FTS transverse sur Skills, documents, projets, tâches) | L | E2-13, E10-01 | Un seul champ de recherche |
| E10-04 | Import/export Markdown + front-matter | M | E10-01 | Aller-retour sans perte |
| E10-05 | UI Knowledge Base | L | E10-03 | Parcours E2E |

### E11 — CLI (itératif, minimum à M2)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E11-01 | Squelette Typer, config (`~/.config/workhub`), authentification par jeton, sortie `--json` | M | E1-04 | `workhub auth login` |
| E11-02 | `workhub skills list/get/export/import/diff` | M | E2-14, E11-01 | Export d'une version vérifié par empreinte |
| E11-03 | `workhub projects`, `tasks`, `plans` | M | E3-07, E9-01 | Exemples du cahier des charges exécutables |
| E11-04 | `workhub deliverables upload` | S | E9-03 | — |
| E11-05 | Distribution (`pipx`/`uv tool`) + autocomplétion | S | E11-03 | Installation documentée |

### E12 — Dashboard et coque frontend (M5)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E12-01 | Layout, navigation (12 espaces du cahier des charges), thème, états de chargement/erreur | L | E0-11 | Coque utilisable |
| E12-02 | Gestion d'erreurs UI + accessibilité de base (clavier, contrastes) | M | E12-01 | Audit axe sans erreur critique |
| E12-03 | Dashboard : projets par statut, tâches prioritaires, progression des plans, Skills récentes, activité des intégrations, blocages | L | E3-08, E9-06, E4-09 | Données réelles |
| E12-04 | Reports & Analytics (v1 : progression, activité par environnement) | M | E12-03 | Exports CSV |

### E13 — Qualité, sécurité, déploiement (M6, en continu)

| ID | Tâche | Taille | Dép. | Critère de fin |
|---|---|---|---|---|
| E13-01 | Revue sécurité guidée par **OWASP ASVS niveau 2** (checklist ciblée) | L | E1-07 | Rapport + corrections |
| E13-02 | Tests de concurrence : deux publications simultanées, deux modifications de brouillon, import concurrent | M | E2-06 | Aucun état incohérent |
| E13-03 | Tests d'intégrité : corrompre un blob en base → détection à l'export | S | E2-09 | Alerte d'intégrité |
| E13-04 | Tests de restauration automatisés (dump → restore → vérification des empreintes) | M | E0-04 | Job hebdomadaire vert |
| E13-05 | Tests de charge adaptés (k6/locust, 50 clients MCP simultanés) | M | E7-07 | Seuils définis et tenus |
| E13-06 | Durcissement : en-têtes de sécurité, CORS strict, secrets, limites de requête, dépendances auditées | M | E13-01 | Scan sans critique |
| E13-07 | Observabilité : métriques (Prometheus) et alertes minimales | M | E0-10 | Tableau de bord opérationnel |
| E13-08 | Documentation utilisateur + technique + procédures d'installation, de sauvegarde et de restauration | L | — | Un tiers installe en suivant la doc |
| E13-09 | Release 1.0 : changelog, tag, images Docker versionnées | S | tout | Version stable |

### E14 — Catalogue d'outils et exigences des Skills (M1 → M3)

> Principe : les exigences sont rattachées aux Skills. Les **packages et outils système sont seulement déclarés** dans la Skill ; le **catalogue ne contient que des scripts**, versionnés. L'application n'installe ni n'exécute jamais : l'agent décide, dans le projet en cours (D7).

| ID | Tâche | Taille | Dép. | Jalon | Critère de fin |
|---|---|---|---|---|---|
| E14-01 | Déclaration inline des exigences (package / système / service) dans les brouillons de Skill ; autocomplétion à partir des exigences déjà utilisées (index dérivé, sans entité supplémentaire) | M | E2-02 | M1 | Un package se déclare avec écosystème + nom, sans passer par le catalogue |
| E14-02 | `skill_requirement` dans le manifeste et dans le calcul d'empreinte (coordonné avec E2-04) | M | E2-04, E14-01 | M1 | Changer une exigence change le hash ; test property-based |
| E14-03 | Règles de publication : package = écosystème + nom valides (contrainte facultative) ; script référencé = `tool_version` publiée ; outil système = commande `check` obligatoire | S | E2-06, E14-02 | M1 | Publication refusée avec message clair, brouillon toléré |
| E14-07 | Outil MCP `get_skill_requirements` + route REST équivalente (déclarations de packages et d'outils système à ce stade) | M | E14-02, E7-02 | M2 | La démo M2 renvoie les exigences structurées |
| E14-04 | Catalogue de scripts : CRUD, **import (copie)** ou **création directe** ; blobs, SHA-256, origine (URL + commit) ; génération de la signature (interface) et détection des effets (imports réseau, sous-processus, secrets) | L | E2-01, E14-01 | M3 | Avertissement si écart entre effets déclarés et détectés |
| E14-05 | `tool_version` : scripts **versionnés (SemVer)**, brouillon mutable → version publiée immuable ; référence `(slug, version, sha256)` depuis les Skills | L | E14-04, E2-05 | M3 | Un script réutilisé par 2 Skills = 1 seul contenu versionné ; modifier = nouvelle version |
| E14-06 | Avertissement à la saisie d'un package : existence sur le registre et nom proche d'un package populaire (asynchrone, facultatif) — **P2** | M | E14-01 | post-1.0 | Nom proche d'un package connu → avertissement |
| E14-08 | Téléchargement de script par empreinte (`tool://slug@version`) avec en-tête de vérification | S | E14-05, E7-02 | M3 | Script falsifié rejeté par le client de test |
| E14-09 | UI : catalogue de scripts + saisie des exigences dans Skills Studio (package inline ; script à sélectionner ou à créer/importer sur place) | L | E14-05, E2-15 | M3 | Ajouter une exigence sans quitter l'éditeur |
| E14-10 | Tests : manipulation du hash, script falsifié, script modifié sans nouvelle version | M | E14-05 | M3 | Suite verte en CI |
| E14-11 | Export d'une Skill : scripts référencés inclus dans `scripts/` ; import d'une Skill avec `scripts/` : chaque script importé dans le catalogue puis référencé | M | E14-05, E2-09, E2-10 | M3 | Export → ré-import = mêmes SHA-256 de scripts |
| E14-12 | Déclaration facultative de la résolution des exigences (déjà présent / installé + version / ignoré / indisponible) dans l'`ExecutionRecord`, via REST et MCP | S | E9-02, E14-07 | M3 | Visible dans l'historique d'exécution |

### E15 — Propositions, profil technique et assistant de création de projet (M3b → M4)

| ID | Tâche | Taille | Dép. | Jalon | Critère de fin |
|---|---|---|---|---|---|
| E15-01 | Mécanisme générique `Proposal` (4 états, décision journalisée, `proposed_by ≠ decided_by`) ; E8-03 s'appuie dessus | L | E1-08 | M3b | Une proposition ne devient jamais « validée » sans décision humaine |
| E15-02 | `project_technology` (états proposé/accepté/modifié/rejeté ; déclaré dans le projet, hors catalogue) + allowlist de Skills par projet + héritage des exigences des Skills épinglées | M | E15-01, E3-04 | M3b | Technologies d'un projet = déclarées ∪ héritées des Skills épinglées, source visible |
| E15-03 | **Profil technique** : instantané immuable et versionné (compétences requises, outils, Skills épinglées, documents, contraintes, architecture, plans), servi par `get_project_context` | L | E15-02, E3-01 | M3b | Deux agents lisent le même snapshot (même `sha256`) |
| E15-04 | Assistant de création, étapes 1, 2, 3a et 4 (infos générales, objectifs/livrables, compétences et outils déclarés, environnement technique) ; sauvegarde à tout moment ; champs techniques facultatifs | L | E15-02, E3-07 | M3b | Projet créable en 2 étapes minimum (nom seul) |
| E15-05 | Conventions structurées vérifiables par projet + déclaration de conformité obligatoire dans `ExecutionRecord` | M | E15-03, E9-02 | M3b | Écart « convention ↔ rapport de conformité » tracé |
| E15-06 | Outil MCP `propose_project_structure` (écrit uniquement des `Proposal`, scope `projects:propose`) | M | E15-01, E7-05 | M4 | Aucun effet sur les données validées |
| E15-07 | Génération des missions, phases et tâches à partir des propositions acceptées | L | E15-06, E4-04 | M4 | Éléments créés = uniquement ceux acceptés ou modifiés |
| E15-08 | Étape 5 de l'assistant : plan proposé depuis un modèle de la bibliothèque (E4-08) | M | E15-07 | M4 | Accepter, modifier ou rejeter chaque phase |
| E15-09 | Moteur de règles de recommandation (technologies, Skills et modèles de plan selon type et tags) — **P2, après 1.0** | L | E15-01 | post-1.0 | Règles déclaratives, testées, sans appel à un modèle |
| E15-10 | Étape 3b : analyse des compétences disponibles / manquantes pour un projet (réutilise E5-04) — **P2** | M | E5-04, E15-04 | post-1.0 | Liste d'écarts affichée dans l'assistant |

---

## 10. Stratégie de tests

| Niveau | Outil | Cible | Exemple concret |
|---|---|---|---|
| Unitaire domaine | pytest + hypothesis | Règles pures (manifeste, SemVer, machine à états, graphes de plans) | « L'ordre des fichiers ne change jamais l'empreinte » |
| Intégration | pytest + testcontainers | Dépôts SQLAlchemy, **triggers et contraintes** | « `UPDATE skill_version` sur une version publiée lève une erreur SQL » |
| API / contrat | schemathesis + httpx | Conformité OpenAPI, erreurs, pagination | Fuzzing automatique de tous les endpoints |
| Permissions | matrice générée | Chaque endpoint × chaque scope | Un jeton `skills:read` ne peut pas publier |
| MCP | client MCP scripté | Outils, scopes, bornes | `update_task_status` refusé sans `tasks:update_status` |
| Concurrence | pytest + tâches parallèles | Publications simultanées | Une seule v1.2.0 existe |
| Outils / scripts | pytest + hypothesis | Hash des exigences, script falsifié, effets déclarés vs détectés | Un octet modifié dans un script → rejet à la livraison |
| Propositions | pytest | Machine à états, séparation proposeur/décideur | Un jeton ne peut pas valider sa propre proposition |
| Frontend | Vitest + Testing Library | Composants, hooks | — |
| E2E | Playwright | 5 parcours : login, créer/publier Skill, créer projet, instancier plan, révoquer jeton | Exécutés en CI sur PR |
| Sécurité | pip-audit, npm audit, bandit, revue ASVS | Dépendances et code | Aucune vulnérabilité critique ouverte |
| Restauration | job CI | Sauvegarde exploitable | Dump → restore → empreintes identiques |

**Seuils CI proposés** : couverture domaine ≥ 90 %, couverture globale ≥ 80 %, zéro erreur pyright strict, zéro violation import-linter.

---

## 11. Risques et plan de réponse

| # | Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Périmètre trop large pour un développeur seul** | Élevée | Élevé | Jalons livrables, D1, règle « rien de nouveau avant que le jalon précédent soit vert », backlog P2 coupable sans casser la vision |
| R2 | Le protocole MCP et les clients (Claude Code, OpenCode, Codex) évoluent | Moyenne | Moyen | Adaptateur mince (D4), tests de client scriptés, ne pas dépendre d'un comportement spécifique à un client |
| R3 | Format Agent Skills qui évolue | Moyenne | Moyen | Validation isolée dans un module unique ; le manifeste interne ne dépend pas du frontmatter |
| R4 | Sur-ingénierie du modèle de plans | Élevée | Moyen | E4-01 : schéma JSON volontairement minimal d'abord ; enrichir à l'usage avec de vrais plans (E4-08) |
| R5 | Injection de prompt via contenu éditable | Moyenne | Élevé | §7.3 : revue obligatoire, `origin` tracée, hash visible |
| R6 | Perte de données | Faible | Critique | Sauvegardes chiffrées + test de restauration automatisé (E13-04) |
| R7 | Dérive des règles d'architecture avec l'usage d'agents de code | Moyenne | Moyen | E0-03 (CI bloquante) ; fichier `AGENTS.md`/`CLAUDE.md` à la racine rappelant les règles |
| R8 | UI sous-estimée (Skills Studio, éditeur de plans) | Élevée | Moyen | Tâches XL explicites ; livrer d'abord API + CLI + MCP utilisables, UI en parallèle |
| R9 | Dérive de l'assistant de création vers un agent (appel LLM embarqué) | Moyenne | Élevé | D8 : moteur de règles ou propositions d'agents externes uniquement ; test CI vérifiant l'absence de SDK de modèle dans les dépendances |
| R10 | Le catalogue d'outils devient un gestionnaire de paquets | Moyenne | Moyen | Périmètre fixé : le catalogue ne contient que des scripts ; les packages sont seulement déclarés dans les Skills ; rien n'est installé ni exécuté par l'application (D7) |
| R11 | Mon estimation initiale était trop optimiste (20 semaines) | Élevée | Moyen | Recalibrage à la fin de M1 ; leviers : reporter E15-06 → E15-08, E15-09/10 déjà en P2 |

---

## 12. Traçabilité : scénarios d'acceptation → jalons et tâches

| Scénario | Jalon | Tâches déterminantes | Test d'acceptation |
|---|---|---|---|
| A — Compétences | M5 | E5-01 → E5-06 | E2E : créer compétence, preuve, associer à un rôle |
| B — Projet | M3 | E3-01 → E3-08 | E2E : projet + missions + plan |
| C — Skills | M1 | E2-05, E2-06, E2-08 | Publier v1.0.0 puis v1.1.0 ; les deux restent lisibles, historique conservé |
| D — Sync Skills | M6 | E8-01, E8-02 | OpenCode lit v1.1.0 ; publication v1.2.0 → « mise à jour disponible » |
| E — Travail externe | M3 | E7-04, E7-05, E9-02, E9-03 | Client MCP : contexte → tâches → livrable → statut mis à jour |
| F — Interopérabilité | M6 | E8-05, E8-06 | 2 clients, même projet, aucune duplication |
| G — Protection des versions | M3 | E3-04, E3-05 | Publier v2.0.0 : le projet épinglé reste sur v1.2.0 |
| H — Traçabilité | M3 | E1-08, E9-02 | Modification de tâche par intégration : identité, date, action, références dans `audit_log` et `execution_record` |
| I — Outils et exigences *(nouveau)* | M2 → M3 | E14-02, E14-04, E14-07, E14-08 | Une Skill requiert un package et un script : l'agent récupère les exigences, **décide** d'installer le package dans le projet en cours, télécharge le script, **le hash correspond** ; un script falsifié est rejeté |
| J — Création de projet assistée *(nouveau)* | M3b → M4 | E15-01, E15-03, E15-04, E15-07 | Un agent propose une structure (proposée) ; l'utilisateur accepte/modifie/rejette ; missions créées = éléments acceptés ; Codex récupère le même profil technique (même `sha256`) |

### Définition de « Terminé » (DoD) — valable pour chaque tâche

1. Code sous les règles d'architecture (CI verte, import-linter inclus).
2. Tests écrits et passants ; si endpoint : test de permission inclus.
3. Migration Alembic fournie et réversible quand c'est possible.
4. Toute écriture d'intégration produit une ligne d'audit.
5. OpenAPI à jour ; client TypeScript régénéré sans diff manuel.
6. Documentation (ADR ou doc) mise à jour si une décision a changé.

---

## 13. Les 10 premières actions (semaine 1)

1. Valider les points de la §1 (surtout : mono-utilisateur, brouillon vs version, contenu du manifeste).
2. Créer le dépôt et exécuter E0-01 → E0-05 (CI verte avant la première ligne métier).
3. Rédiger les ADR 002, 003 et 006 (stockage, manifeste **avec le bloc `requirements`**, brouillon/version) : ce sont les trois décisions les plus coûteuses à changer. Ajouter `requirements` au manifeste après coup changerait tous les hashs déjà calculés.
4. Écrire le module pur de manifeste + hash (E2-04, `requirements` inclus) avec ses tests property-based : il n'a aucune dépendance et valide ton modèle d'intégrité.
5. Poser les triggers d'immutabilité dès la première migration Skills (E2-01, E2-05).
6. Rédiger le fichier `AGENTS.md` / `CLAUDE.md` : règles d'architecture, commandes de test, conventions — pour que les agents qui t'aident à coder respectent le cadre.
7. Importer **une Skill réelle** (par exemple `web-pentest`) comme jeu de test de référence pour tout le module.
8. Prototyper un serveur MCP de 2 outils (`search_skills`, `get_skill`) contre des données factices pour valider tôt la connexion avec Claude Code et OpenCode.
9. Écrire le plan de test de permissions (E1-07) avant les premiers endpoints.
10. Fixer les critères « go/no-go » de la démo M2 : un agent externe récupère une Skill par son SemVer et la hash vérifie.

---

*Fin du document. Chaque tâche est dimensionnée pour être exécutée sans fragmentation artificielle ; les estimations seront recalibrées à la fin de M1 sur la base du rythme réel.*
