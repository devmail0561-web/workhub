-- WorkHub — vérifications comportementales du schéma v0
-- À exécuter sur une base où docs/specs/schema-v0.sql vient d'être appliqué.
-- Chaque bloc lève une exception si l'invariant attendu n'est pas respecté.
-- Tout est annulé en fin de script (rollback).

\set ON_ERROR_STOP on

begin;

insert into app_user (id, email, password_hash, display_name)
values ('00000000-0000-0000-0000-000000000001', 'admin@example.test', 'x', 'Admin');

insert into integration (id, name, kind, owner_id)
values (
    '00000000-0000-0000-0000-000000000002', 'agent-test', 'opencode',
    '00000000-0000-0000-0000-000000000001'
);

insert into project (id, slug, name, owner_id)
values (
    '00000000-0000-0000-0000-000000000003', 'demo', 'Démo',
    '00000000-0000-0000-0000-000000000001'
);

insert into mission (id, project_id, name)
values (
    '00000000-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000003', 'Mission démo'
);

insert into skill (id, slug, owner_id, domain, status_logical)
values (
    '00000000-0000-0000-0000-000000000010', 'skill-a',
    '00000000-0000-0000-0000-000000000001', 'backend', 'published'
), (
    '00000000-0000-0000-0000-000000000011', 'skill-b',
    '00000000-0000-0000-0000-000000000001', 'backend', 'published'
);

insert into blob (sha256, size, content)
values (digest('hello', 'sha256'), 5, 'hello');

insert into skill_version (
    id, skill_id, semver, manifest, manifest_sha256, changelog,
    author_principal_id, status
)
values (
    '00000000-0000-0000-0000-000000000020',
    '00000000-0000-0000-0000-000000000010', '1.0.0', '{"name":"skill-a"}'::jsonb,
    digest('{"name":"skill-a"}', 'sha256'), 'Version initiale',
    '00000000-0000-0000-0000-000000000001', 'published'
);

insert into skill_version (
    id, skill_id, semver, manifest, manifest_sha256, changelog,
    author_principal_id, status
)
values (
    '00000000-0000-0000-0000-000000000021',
    '00000000-0000-0000-0000-000000000011', '1.0.0', '{"name":"skill-b"}'::jsonb,
    digest('{"name":"skill-b"}', 'sha256'), 'Version initiale',
    '00000000-0000-0000-0000-000000000001', 'published'
);

insert into skill_draft (id, skill_id, base_version_id)
values (
    '00000000-0000-0000-0000-000000000030',
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000020'
);

insert into skill_draft_file (draft_id, path, blob_sha256)
values (
    '00000000-0000-0000-0000-000000000030', 'SKILL.md',
    digest('hello', 'sha256')
);

insert into skill_version_file (version_id, path, blob_sha256, size)
values (
    '00000000-0000-0000-0000-000000000020', 'SKILL.md',
    digest('hello', 'sha256'), 5
);

insert into skill_dependency (version_id, depends_on_skill_id, version_constraint)
values (
    '00000000-0000-0000-0000-000000000020',
    '00000000-0000-0000-0000-000000000011', '^1.0.0'
);

insert into audit_log (
    principal_type, principal_id, action, resource_type, resource_id, outcome
)
values (
    'user', '00000000-0000-0000-0000-000000000001', 'skill.publish', 'skill',
    '00000000-0000-0000-0000-000000000010', 'success'
);

insert into work_plan_template (id, category, slug, owner_id)
values (
    '00000000-0000-0000-0000-000000000040', 'A', 'plan-a',
    '00000000-0000-0000-0000-000000000001'
);

insert into work_plan_version (id, template_id, semver, content, status)
values (
    '00000000-0000-0000-0000-000000000041',
    '00000000-0000-0000-0000-000000000040', '1.0.0', '{"phases":[]}'::jsonb, 'draft'
);

insert into work_plan_version (id, template_id, semver, content, status)
values (
    '00000000-0000-0000-0000-000000000044',
    '00000000-0000-0000-0000-000000000040', '1.1.0', '{"phases":[]}'::jsonb, 'draft'
);

insert into work_plan_instance (id, template_version_id, project_id, state)
values (
    '00000000-0000-0000-0000-000000000042',
    '00000000-0000-0000-0000-000000000041',
    '00000000-0000-0000-0000-000000000003', 'active'
);

insert into instance_node (id, instance_id, path, node_type)
values (
    '00000000-0000-0000-0000-000000000043',
    '00000000-0000-0000-0000-000000000042', '1.1', 'task'
);

insert into proposal (
    id, target_type, payload, status, proposed_by_type, proposed_by_principal_id
)
values (
    '00000000-0000-0000-0000-000000000050', 'project_technology',
    '{"name":"python"}'::jsonb, 'proposed', 'user',
    '00000000-0000-0000-0000-000000000001'
);

insert into project_profile_snapshot (id, project_id, content)
values (
    '00000000-0000-0000-0000-000000000060',
    '00000000-0000-0000-0000-000000000003', '{"stack":["python"]}'::jsonb
);

-- 1. Un blob ne peut être modifié ni supprimé sans GC explicite.
do $$
begin
    begin
        update blob set created_at = now() where sha256 = digest('hello', 'sha256');
        raise exception 'FAIL: modification de blob acceptée';
    exception when check_violation then null;
    end;
    begin
        delete from blob where sha256 = digest('hello', 'sha256');
        raise exception 'FAIL: suppression de blob acceptée sans GC';
    exception when check_violation then null;
    end;
end $$;

-- 2. L'empreinte d'un blob est vérifiée.
do $$
begin
    begin
        insert into blob (sha256, size, content)
        values (digest('autre', 'sha256'), 5, 'hello');
        raise exception 'FAIL: hash de blob incohérent accepté';
    exception when check_violation then null;
    end;
end $$;

-- 3. audit_log est append-only.
do $$
begin
    begin
        update audit_log set action = 'forged';
        raise exception 'FAIL: modification de audit_log acceptée';
    exception when check_violation then null;
    end;
    begin
        delete from audit_log;
        raise exception 'FAIL: suppression de audit_log acceptée';
    exception when check_violation then null;
    end;
end $$;

-- 4. Une version publiée est immuable hors cycle de vie.
do $$
begin
    begin
        update skill_version set changelog = 'forged'
        where id = '00000000-0000-0000-0000-000000000020';
        raise exception 'FAIL: modification de skill_version acceptée';
    exception when check_violation then null;
    end;
    begin
        update skill_version set status = 'archived'
        where id = '00000000-0000-0000-0000-000000000020';
        raise exception 'FAIL: transition published → archived acceptée';
    exception when check_violation then null;
    end;
    begin
        delete from skill_version where id = '00000000-0000-0000-0000-000000000020';
        raise exception 'FAIL: suppression de skill_version acceptée';
    exception when check_violation then null;
    end;
    update skill_version set status = 'deprecated'
    where id = '00000000-0000-0000-0000-000000000020';
    update skill_version set status = 'archived'
    where id = '00000000-0000-0000-0000-000000000020';
end $$;

-- 5. Les fichiers de version sont immuables.
do $$
begin
    begin
        update skill_version_file set mode = '0755';
        raise exception 'FAIL: modification de skill_version_file acceptée';
    exception when check_violation then null;
    end;
    begin
        delete from skill_version_file;
        raise exception 'FAIL: suppression de skill_version_file acceptée';
    exception when check_violation then null;
    end;
end $$;

-- 6. Une version épinglée doit appartenir à la Skill épinglée (FK composite).
do $$
begin
    begin
        insert into project_skill_pin (project_id, skill_id, version_id)
        values (
            '00000000-0000-0000-0000-000000000003',
            '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000021'
        );
        raise exception 'FAIL: épinglage d''une version d''une autre Skill accepté';
    exception when foreign_key_violation then null;
    end;
end $$;

-- 7. La version de modèle d'une instance est figée.
do $$
begin
    begin
        update work_plan_instance
        set template_version_id = '00000000-0000-0000-0000-000000000044'
        where id = '00000000-0000-0000-0000-000000000042';
        raise exception 'FAIL: template_version_id modifié';
    exception when check_violation then null;
    end;
end $$;

-- 8. Une version de plan est modifiable en brouillon, immuable une fois publiée.
update work_plan_version set content = '{"phases":["a"]}'::jsonb
where id = '00000000-0000-0000-0000-000000000041';
update work_plan_version set status = 'published', published_at = now()
where id = '00000000-0000-0000-0000-000000000041';
do $$
begin
    begin
        update work_plan_version set content = '{"phases":["b"]}'::jsonb
        where id = '00000000-0000-0000-0000-000000000041';
        raise exception 'FAIL: version de plan publiée modifiée';
    exception when check_violation then null;
    end;
    update work_plan_version set status = 'deprecated'
    where id = '00000000-0000-0000-0000-000000000041';
end $$;

-- 9. Une proposition suit sa machine à états.
do $$
begin
    begin
        insert into proposal (
            target_type, payload, status, proposed_by_type, proposed_by_principal_id,
            decided_by_type, decided_by_principal_id, decided_at
        ) values (
            'project_technology', '{}'::jsonb, 'accepted', 'user',
            '00000000-0000-0000-0000-000000000001', 'user',
            '00000000-0000-0000-0000-000000000001', now()
        );
        raise exception 'FAIL: proposition créée déjà décidée';
    exception when check_violation then null;
    end;
    begin
        update proposal set status = 'accepted', decided_by_type = 'user',
            decided_by_principal_id = '00000000-0000-0000-0000-000000000001'
        where id = '00000000-0000-0000-0000-000000000050';
        raise exception 'FAIL: décision sans decided_at acceptée';
    exception when check_violation then null;
    end;
    update proposal set status = 'accepted', decided_by_type = 'user',
        decided_by_principal_id = '00000000-0000-0000-0000-000000000001',
        decided_at = now()
    where id = '00000000-0000-0000-0000-000000000050';
    begin
        update proposal set decision_note = 'forged'
        where id = '00000000-0000-0000-0000-000000000050';
        raise exception 'FAIL: proposition décidée modifiée';
    exception when check_violation then null;
    end;
    begin
        update proposal set status = 'proposed'
        where id = '00000000-0000-0000-0000-000000000050';
        raise exception 'FAIL: proposition décidée revenue à proposed';
    exception when check_violation then null;
    end;
end $$;

-- 10. Un instantané de profil calcule son empreinte et reste immuable.
do $$
begin
    if (
        select sha256 from project_profile_snapshot
        where id = '00000000-0000-0000-0000-000000000060'
    ) is distinct from (
        select digest(content::text, 'sha256') from project_profile_snapshot
        where id = '00000000-0000-0000-0000-000000000060'
    ) then
        raise exception 'FAIL: empreinte de snapshot incorrecte';
    end if;
    begin
        update project_profile_snapshot set content = '{}'::jsonb
        where id = '00000000-0000-0000-0000-000000000060';
        raise exception 'FAIL: snapshot modifié';
    exception when check_violation then null;
    end;
    begin
        delete from project_profile_snapshot
        where id = '00000000-0000-0000-0000-000000000060';
        raise exception 'FAIL: snapshot supprimé';
    exception when check_violation then null;
    end;
end $$;

-- 11. Une Skill ne peut pas dépendre d'elle-même.
do $$
begin
    begin
        insert into skill_dependency (version_id, depends_on_skill_id, version_constraint)
        values (
            '00000000-0000-0000-0000-000000000020',
            '00000000-0000-0000-0000-000000000010', '*'
        );
        raise exception 'FAIL: auto-dépendance acceptée';
    exception when check_violation then null;
    end;
end $$;

-- 12. Le GC explicite des blobs non référencés est autorisé.
insert into blob (sha256, size, content)
values (digest('unused', 'sha256'), 6, 'unused');
set local workhub.allow_blob_gc = 'on';
delete from blob where sha256 = digest('unused', 'sha256');

rollback;

\echo 'Vérifications du schéma v0 : OK'
