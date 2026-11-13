-- WorkHub — schéma v0 (PostgreSQL 16)
-- Source de vérité documentaire : docs/specs/schema-v0.md
-- Ce fichier est exécutable tel quel sur une base vide (extension pgcrypto requise).
-- Il sera traduit en migration Alembic lors de E0-09.

begin;

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Fonctions utilitaires
-- ---------------------------------------------------------------------------

create function workhub_reject_mutation() returns trigger
language plpgsql as $$
begin
    raise exception 'workhub: % est en ajout seul (opération % interdite)', tg_table_name, tg_op
        using errcode = '23514';
end;
$$;

create function workhub_touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create function workhub_blob_guard() returns trigger
language plpgsql as $$
begin
    if tg_op = 'UPDATE' then
        raise exception 'workhub: un blob est immuable' using errcode = '23514';
    end if;
    if tg_op = 'DELETE'
       and coalesce(current_setting('workhub.allow_blob_gc', true), 'off') <> 'on' then
        raise exception 'workhub: suppression de blob réservée au GC (workhub.allow_blob_gc=on)'
            using errcode = '23514';
    end if;
    return old;
end;
$$;

create function workhub_version_guard() returns trigger
language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'workhub: % est immuable (suppression interdite)', tg_table_name
            using errcode = '23514';
    end if;
    if (to_jsonb(new) - 'status') is distinct from (to_jsonb(old) - 'status') then
        raise exception 'workhub: % est immuable hors changement de statut', tg_table_name
            using errcode = '23514';
    end if;
    if new.status is distinct from old.status
       and not (
           (old.status = 'published' and new.status = 'deprecated')
           or (old.status = 'deprecated' and new.status = 'archived')
       ) then
        raise exception 'workhub: transition de statut % → % interdite', old.status, new.status
            using errcode = '23514';
    end if;
    return new;
end;
$$;

create function workhub_work_plan_version_guard() returns trigger
language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        if old.status <> 'draft' then
            raise exception 'workhub: une version de plan publiée est immuable'
                using errcode = '23514';
        end if;
        return old;
    end if;
    if old.status = 'draft' then
        if new.status is distinct from old.status and new.status <> 'published' then
            raise exception 'workhub: transition de statut draft → % interdite', new.status
                using errcode = '23514';
        end if;
        return new;
    end if;
    if (to_jsonb(new) - 'status') is distinct from (to_jsonb(old) - 'status') then
        raise exception 'workhub: une version de plan publiée est immuable'
            using errcode = '23514';
    end if;
    if new.status is distinct from old.status
       and not (
           (old.status = 'published' and new.status = 'deprecated')
           or (old.status = 'deprecated' and new.status = 'archived')
       ) then
        raise exception 'workhub: transition de statut % → % interdite', old.status, new.status
            using errcode = '23514';
    end if;
    return new;
end;
$$;

create function workhub_instance_guard() returns trigger
language plpgsql as $$
begin
    if new.template_version_id is distinct from old.template_version_id then
        raise exception 'workhub: template_version_id est figé (migration explicite requise)'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

create function workhub_proposal_guard() returns trigger
language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.status <> 'proposed' then
            raise exception 'workhub: une proposition est créée avec le statut proposed'
                using errcode = '23514';
        end if;
        return new;
    end if;
    if old.status <> 'proposed'
       and (to_jsonb(new) - 'status') is distinct from (to_jsonb(old) - 'status') then
        raise exception 'workhub: une proposition décidée est figée' using errcode = '23514';
    end if;
    if new.status is distinct from old.status
       and not (old.status = 'proposed'
                and new.status in ('accepted', 'modified', 'rejected')) then
        raise exception 'workhub: transition de proposition % → % interdite', old.status, new.status
            using errcode = '23514';
    end if;
    return new;
end;
$$;

create function workhub_snapshot_guard() returns trigger
language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        new.sha256 := digest(new.content::text, 'sha256');
        return new;
    end if;
    raise exception 'workhub: un instantané de profil est immuable' using errcode = '23514';
end;
$$;

create function workhub_dependency_guard() returns trigger
language plpgsql as $$
begin
    if exists (
        select 1 from skill_version v
        where v.id = new.version_id and v.skill_id = new.depends_on_skill_id
    ) then
        raise exception 'workhub: une Skill ne peut pas dépendre d''elle-même'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Identité et intégrations (§4.3)
-- ---------------------------------------------------------------------------

create table app_user (
    id uuid primary key default gen_random_uuid(),
    email text not null,
    password_hash text not null,
    display_name text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_login_at timestamptz,
    constraint ck_app_user_email_non_vide check (length(btrim(email)) > 3)
);

create unique index ux_app_user_email_lower on app_user (lower(email));

create table integration (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    kind text not null,
    owner_id uuid not null references app_user (id),
    created_at timestamptz not null default now(),
    revoked_at timestamptz,
    constraint ck_integration_name_non_vide check (length(btrim(name)) > 0)
);

create table api_token (
    id uuid primary key default gen_random_uuid(),
    integration_id uuid not null references integration (id) on delete cascade,
    token_sha256 bytea not null,
    scopes text[] not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz,
    last_used_at timestamptz,
    revoked_at timestamptz,
    constraint ck_api_token_hash_taille check (octet_length(token_sha256) = 32),
    constraint ck_api_token_scopes check (cardinality(scopes) > 0)
);

create unique index ux_api_token_hash on api_token (token_sha256);

-- ---------------------------------------------------------------------------
-- Projets et missions (squelette v0, complétés en E3)
-- ---------------------------------------------------------------------------

create table project (
    id uuid primary key default gen_random_uuid(),
    slug text not null,
    name text not null,
    status text not null default 'draft',
    owner_id uuid references app_user (id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    archived_at timestamptz,
    constraint ux_project_slug unique (slug),
    constraint ck_project_slug check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    constraint ck_project_status check (status in ('draft', 'active', 'archived'))
);

create table mission (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references project (id) on delete cascade,
    name text not null,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    archived_at timestamptz,
    constraint ck_mission_status check (status in ('draft', 'active', 'completed', 'archived'))
);

-- ---------------------------------------------------------------------------
-- Skills (§4.1)
-- ---------------------------------------------------------------------------

create table skill (
    id uuid primary key default gen_random_uuid(),
    slug text not null,
    owner_id uuid not null references app_user (id),
    domain text not null,
    status_logical text not null default 'draft',
    tags text[] not null default '{}',
    created_at timestamptz not null default now(),
    archived_at timestamptz,
    constraint ux_skill_slug unique (slug),
    constraint ck_skill_slug check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    constraint ck_skill_domain check (length(btrim(domain)) > 0),
    constraint ck_skill_status check (
        status_logical in ('draft', 'review', 'published', 'deprecated', 'archived')
    )
);

create table blob (
    sha256 bytea primary key,
    size bigint not null,
    content bytea not null,
    created_at timestamptz not null default now(),
    constraint ck_blob_hash_taille check (octet_length(sha256) = 32),
    constraint ck_blob_size check (size >= 0),
    constraint ck_blob_contenu check (
        octet_length(content) = size and digest(content, 'sha256') = sha256
    )
);

create table skill_version (
    id uuid primary key default gen_random_uuid(),
    skill_id uuid not null references skill (id),
    semver text not null,
    manifest jsonb not null,
    manifest_sha256 bytea not null,
    parent_version_id uuid,
    status text not null default 'published',
    changelog text not null,
    author_principal_id uuid not null,
    origin_kind text not null default 'app',
    origin_integration_id uuid references integration (id),
    created_at timestamptz not null default now(),
    published_at timestamptz not null default now(),
    test_results jsonb,
    constraint ux_skill_version_semver unique (skill_id, semver),
    constraint ux_skill_version_id_skill unique (id, skill_id),
    constraint fk_skill_version_parent foreign key (parent_version_id, skill_id)
        references skill_version (id, skill_id),
    constraint ck_skill_version_semver check (
        semver ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'
    ),
    constraint ck_skill_version_hash check (octet_length(manifest_sha256) = 32),
    constraint ck_skill_version_status check (status in ('published', 'deprecated', 'archived')),
    constraint ck_skill_version_changelog check (length(btrim(changelog)) > 0),
    constraint ck_skill_version_origin check (
        (origin_kind = 'app' and origin_integration_id is null)
        or (origin_kind = 'integration' and origin_integration_id is not null)
    )
);

create table skill_draft (
    id uuid primary key default gen_random_uuid(),
    skill_id uuid not null references skill (id) on delete cascade,
    base_version_id uuid,
    updated_at timestamptz not null default now(),
    lock_version integer not null default 0,
    constraint ux_skill_draft_skill unique (skill_id),
    constraint fk_skill_draft_base foreign key (base_version_id, skill_id)
        references skill_version (id, skill_id),
    constraint ck_skill_draft_lock_version check (lock_version >= 0)
);

create table skill_draft_file (
    draft_id uuid not null references skill_draft (id) on delete cascade,
    path text not null,
    blob_sha256 bytea not null references blob (sha256),
    mode text not null default '0644',
    primary key (draft_id, path),
    constraint ck_skill_draft_file_path check (
        path <> '' and length(path) <= 1024
        and path !~ '^/' and path !~ '(^|/)\.\.(/|$)' and path !~ '\\'
    ),
    constraint ck_skill_draft_file_mode check (mode ~ '^[0-7]{3,4}$')
);

create table skill_version_file (
    version_id uuid not null references skill_version (id),
    path text not null,
    blob_sha256 bytea not null references blob (sha256),
    size bigint not null,
    mode text not null default '0644',
    primary key (version_id, path),
    constraint ck_skill_version_file_path check (
        path <> '' and length(path) <= 1024
        and path !~ '^/' and path !~ '(^|/)\.\.(/|$)' and path !~ '\\'
    ),
    constraint ck_skill_version_file_mode check (mode ~ '^[0-7]{3,4}$'),
    constraint ck_skill_version_file_size check (size >= 0)
);

create table skill_dependency (
    version_id uuid not null references skill_version (id),
    depends_on_skill_id uuid not null references skill (id),
    version_constraint text not null,
    primary key (version_id, depends_on_skill_id),
    constraint ck_skill_dependency_constraint check (length(btrim(version_constraint)) > 0)
);

create table skill_deployment (
    integration_id uuid not null references integration (id) on delete cascade,
    skill_id uuid not null references skill (id),
    version_id uuid not null,
    deployed_at timestamptz not null default now(),
    last_seen_at timestamptz,
    primary key (integration_id, skill_id),
    constraint fk_skill_deployment_version foreign key (version_id, skill_id)
        references skill_version (id, skill_id)
);

create table project_skill_pin (
    project_id uuid not null references project (id) on delete cascade,
    skill_id uuid not null references skill (id),
    version_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (project_id, skill_id),
    constraint fk_project_skill_pin_version foreign key (version_id, skill_id)
        references skill_version (id, skill_id)
);

-- ---------------------------------------------------------------------------
-- Plans de travail (§4.2)
-- ---------------------------------------------------------------------------

create table work_plan_template (
    id uuid primary key default gen_random_uuid(),
    category text not null,
    slug text not null,
    owner_id uuid not null references app_user (id),
    created_at timestamptz not null default now(),
    constraint ux_work_plan_template_category_slug unique (category, slug),
    constraint ck_work_plan_template_category check (category in ('A', 'B', 'C', 'D')),
    constraint ck_work_plan_template_slug check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
);

create table work_plan_version (
    id uuid primary key default gen_random_uuid(),
    template_id uuid not null references work_plan_template (id),
    semver text not null,
    content jsonb not null,
    status text not null default 'draft',
    created_at timestamptz not null default now(),
    published_at timestamptz,
    constraint ux_work_plan_version_semver unique (template_id, semver),
    constraint ck_work_plan_version_semver check (
        semver ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'
    ),
    constraint ck_work_plan_version_status check (
        status in ('draft', 'published', 'deprecated', 'archived')
    )
);

create table work_plan_instance (
    id uuid primary key default gen_random_uuid(),
    template_version_id uuid not null references work_plan_version (id),
    project_id uuid references project (id) on delete cascade,
    mission_id uuid references mission (id) on delete cascade,
    state text not null default 'draft',
    started_at timestamptz,
    created_at timestamptz not null default now(),
    constraint ck_work_plan_instance_cible check (num_nonnulls(project_id, mission_id) = 1),
    constraint ck_work_plan_instance_state check (
        state in ('draft', 'active', 'paused', 'completed', 'abandoned')
    )
);

create table instance_node (
    id uuid primary key default gen_random_uuid(),
    instance_id uuid not null references work_plan_instance (id) on delete cascade,
    path text not null,
    node_type text not null,
    status text not null default 'pending',
    overrides jsonb not null default '{}',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint ux_instance_node_path unique (instance_id, path),
    constraint ck_instance_node_path check (
        path <> '' and length(path) <= 1024
        and path !~ '^/' and path !~ '(^|/)\.\.(/|$)' and path !~ '\\'
    ),
    constraint ck_instance_node_type check (
        node_type in ('phase', 'activity', 'task', 'subtask')
    ),
    constraint ck_instance_node_status check (
        status in ('pending', 'in_progress', 'done', 'blocked', 'skipped')
    )
);

-- ---------------------------------------------------------------------------
-- Audit et exécution (§4.3)
-- ---------------------------------------------------------------------------

create table audit_log (
    id bigint generated always as identity primary key,
    at timestamptz not null default now(),
    principal_type text not null,
    principal_id uuid,
    integration_id uuid references integration (id),
    action text not null,
    resource_type text not null,
    resource_id text,
    request_id text,
    outcome text not null,
    details jsonb not null default '{}',
    constraint ck_audit_log_principal_type check (
        principal_type in ('user', 'integration', 'system')
    ),
    constraint ck_audit_log_outcome check (outcome in ('success', 'failure', 'denied'))
);

create table execution_record (
    id uuid primary key default gen_random_uuid(),
    task_id uuid not null references instance_node (id),
    plan_version_id uuid not null references work_plan_version (id),
    executor_type text not null,
    executor_id uuid not null,
    skill_versions jsonb not null default '[]',
    requirement_resolution jsonb,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    outcome text not null default 'running',
    validation jsonb,
    constraint ck_execution_record_executor check (executor_type in ('human', 'integration')),
    constraint ck_execution_record_outcome check (
        outcome in ('running', 'success', 'failure', 'partial', 'abandoned')
    ),
    constraint ck_execution_record_dates check (
        finished_at is null or finished_at >= started_at
    )
);

-- ---------------------------------------------------------------------------
-- Outils, exigences, propositions (§4.4)
-- ---------------------------------------------------------------------------

create table tool (
    id uuid primary key default gen_random_uuid(),
    slug text not null,
    name text not null,
    kind text not null default 'script',
    origin text not null,
    origin_ref text,
    notes text,
    created_at timestamptz not null default now(),
    archived_at timestamptz,
    constraint ux_tool_slug unique (slug),
    constraint ck_tool_slug check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    constraint ck_tool_kind check (kind in ('script')),
    constraint ck_tool_origin check (origin in ('import', 'created')),
    constraint ck_tool_origin_ref check (origin = 'created' or origin_ref is not null)
);

create table tool_version (
    id uuid primary key default gen_random_uuid(),
    tool_id uuid not null references tool (id),
    semver text not null,
    manifest_sha256 bytea not null,
    signature jsonb not null default '{}',
    status text not null default 'published',
    created_at timestamptz not null default now(),
    published_at timestamptz not null default now(),
    constraint ux_tool_version_semver unique (tool_id, semver),
    constraint ck_tool_version_semver check (
        semver ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'
    ),
    constraint ck_tool_version_hash check (octet_length(manifest_sha256) = 32),
    constraint ck_tool_version_status check (status in ('published', 'deprecated', 'archived'))
);

create table tool_version_file (
    tool_version_id uuid not null references tool_version (id),
    path text not null,
    blob_sha256 bytea not null references blob (sha256),
    size bigint not null,
    mode text not null default '0644',
    primary key (tool_version_id, path),
    constraint ck_tool_version_file_path check (
        path <> '' and length(path) <= 1024
        and path !~ '^/' and path !~ '(^|/)\.\.(/|$)' and path !~ '\\'
    ),
    constraint ck_tool_version_file_mode check (mode ~ '^[0-7]{3,4}$'),
    constraint ck_tool_version_file_size check (size >= 0)
);

create table skill_requirement (
    id uuid primary key default gen_random_uuid(),
    skill_version_id uuid not null references skill_version (id),
    kind text not null,
    ecosystem text,
    name text,
    version_constraint text,
    pinned_version text,
    hashes jsonb,
    check_command text,
    tool_version_id uuid references tool_version (id),
    usage text not null default 'required',
    note text,
    constraint ck_skill_requirement_kind check (
        kind in ('package', 'system', 'service', 'script')
    ),
    constraint ck_skill_requirement_usage check (usage in ('required', 'optional')),
    constraint ck_skill_requirement_forme check (
        (kind = 'script' and tool_version_id is not null and name is null)
        or (kind = 'package' and ecosystem is not null and name is not null
            and tool_version_id is null)
        or (kind in ('system', 'service') and name is not null and tool_version_id is null)
    )
);

create table project_technology (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references project (id) on delete cascade,
    kind text not null,
    name text not null,
    ecosystem text,
    tool_id uuid references tool (id),
    status text not null default 'proposed',
    rationale text,
    created_at timestamptz not null default now(),
    decided_at timestamptz,
    constraint ux_project_technology unique (project_id, kind, name),
    constraint ck_project_technology_status check (
        status in ('proposed', 'accepted', 'modified', 'rejected')
    ),
    constraint ck_project_technology_decision check (
        status = 'proposed' or decided_at is not null
    )
);

create table project_skill_allowlist (
    project_id uuid not null references project (id) on delete cascade,
    skill_id uuid not null references skill (id),
    created_at timestamptz not null default now(),
    primary key (project_id, skill_id)
);

create table project_convention (
    project_id uuid not null references project (id) on delete cascade,
    key text not null,
    rule jsonb not null,
    verifiable boolean not null default true,
    primary key (project_id, key)
);

create table proposal (
    id uuid primary key default gen_random_uuid(),
    target_type text not null,
    target_id uuid,
    payload jsonb not null,
    status text not null default 'proposed',
    proposed_by_type text not null,
    proposed_by_principal_id uuid not null,
    decided_by_type text,
    decided_by_principal_id uuid,
    created_at timestamptz not null default now(),
    decided_at timestamptz,
    decision_note text,
    constraint ck_proposal_target_type check (
        target_type in (
            'skill_update', 'project_technology', 'project_skill',
            'competency', 'plan_structure'
        )
    ),
    constraint ck_proposal_status check (
        status in ('proposed', 'accepted', 'modified', 'rejected')
    ),
    constraint ck_proposal_proposer check (proposed_by_type in ('user', 'integration')),
    constraint ck_proposal_decider check (
        decided_by_type is null or decided_by_type in ('user', 'integration')
    ),
    constraint ck_proposal_decision check (
        (status = 'proposed'
            and decided_by_type is null and decided_by_principal_id is null and decided_at is null)
        or (status in ('accepted', 'modified', 'rejected')
            and decided_by_type is not null and decided_by_principal_id is not null
            and decided_at is not null)
    ),
    constraint ck_proposal_auto_decision check (
        not (proposed_by_type = 'integration'
             and decided_by_type = 'integration'
             and proposed_by_principal_id = decided_by_principal_id)
    )
);

create table project_profile_snapshot (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references project (id) on delete cascade,
    content jsonb not null,
    sha256 bytea not null,
    created_at timestamptz not null default now(),
    constraint ck_project_profile_snapshot_hash check (octet_length(sha256) = 32)
);

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------

create trigger trg_app_user_touch before update on app_user
    for each row execute function workhub_touch_updated_at();
create trigger trg_project_touch before update on project
    for each row execute function workhub_touch_updated_at();
create trigger trg_mission_touch before update on mission
    for each row execute function workhub_touch_updated_at();
create trigger trg_skill_draft_touch before update on skill_draft
    for each row execute function workhub_touch_updated_at();
create trigger trg_instance_node_touch before update on instance_node
    for each row execute function workhub_touch_updated_at();

create trigger trg_blob_guard before update or delete on blob
    for each row execute function workhub_blob_guard();
create trigger trg_skill_version_guard before update or delete on skill_version
    for each row execute function workhub_version_guard();
create trigger trg_tool_version_guard before update or delete on tool_version
    for each row execute function workhub_version_guard();
create trigger trg_work_plan_version_guard before update or delete on work_plan_version
    for each row execute function workhub_work_plan_version_guard();

create trigger trg_skill_version_file_guard before update or delete on skill_version_file
    for each row execute function workhub_reject_mutation();
create trigger trg_tool_version_file_guard before update or delete on tool_version_file
    for each row execute function workhub_reject_mutation();
create trigger trg_audit_log_guard before update or delete on audit_log
    for each row execute function workhub_reject_mutation();

create trigger trg_work_plan_instance_guard before update on work_plan_instance
    for each row execute function workhub_instance_guard();
create trigger trg_proposal_guard before insert or update on proposal
    for each row execute function workhub_proposal_guard();
create trigger trg_project_profile_snapshot_guard
    before insert or update or delete on project_profile_snapshot
    for each row execute function workhub_snapshot_guard();
create trigger trg_skill_dependency_guard before insert or update on skill_dependency
    for each row execute function workhub_dependency_guard();

-- ---------------------------------------------------------------------------
-- Index
-- ---------------------------------------------------------------------------

create index ix_skill_version_skill on skill_version (skill_id, published_at desc);
create index ix_skill_version_parent on skill_version (parent_version_id);
create index ix_skill_draft_base on skill_draft (base_version_id);
create index ix_skill_draft_file_blob on skill_draft_file (blob_sha256);
create index ix_skill_version_file_blob on skill_version_file (blob_sha256);
create index ix_tool_version_file_blob on tool_version_file (blob_sha256);
create index ix_skill_tags on skill using gin (tags);
create index ix_skill_requirement_version on skill_requirement (skill_version_id);
create index ix_project_mission on mission (project_id);
create index ix_instance_node_instance on instance_node (instance_id);
create index ix_execution_record_task on execution_record (task_id);
create index ix_execution_record_plan_version on execution_record (plan_version_id);
create index ix_audit_log_resource on audit_log (resource_type, resource_id, at desc);
create index ix_audit_log_principal on audit_log (principal_id, at desc);
create index ix_audit_log_at on audit_log (at desc);
create index ix_project_technology_project on project_technology (project_id);
create index ix_proposal_status on proposal (status, created_at desc);

comment on table app_user is 'Utilisateurs (nom app_user : user est réservé en SQL)';
comment on table audit_log is 'Journal append-only, alimenté par audit.record() (E1-08)';
comment on table blob is 'Magasin de contenus adressés par SHA-256, immuables';
comment on table skill_version is 'Version publiée d''une Skill, immuable hors cycle de vie';
comment on column skill_requirement.version_constraint is 'Contrainte de version (colonne « constraint » du plan)';
comment on column skill_requirement.pinned_version is 'Version figée optionnelle pour une exigence de paquet';

commit;
