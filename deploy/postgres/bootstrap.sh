#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER requis}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD requis}"
: "${POSTGRES_DB:?POSTGRES_DB requis}"
: "${WORKHUB_OWNER_PASSWORD:?WORKHUB_OWNER_PASSWORD requis}"
: "${WORKHUB_APP_PASSWORD:?WORKHUB_APP_PASSWORD requis}"

owner_user="workhub_owner"
app_user="workhub_app"

export PGPASSWORD="$POSTGRES_PASSWORD"

psql --set=ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname postgres \
    --variable=owner_password="$WORKHUB_OWNER_PASSWORD" \
    --variable=app_password="$WORKHUB_APP_PASSWORD" \
    --variable=database="$POSTGRES_DB" <<'SQL'
select format('create role workhub_owner login password %L', :'owner_password')
where not exists (select 1 from pg_roles where rolname = 'workhub_owner');
\gexec
select format('alter role workhub_owner with login password %L', :'owner_password');
\gexec
select format('create role workhub_app login password %L', :'app_password')
where not exists (select 1 from pg_roles where rolname = 'workhub_app');
\gexec
select format('alter role workhub_app with login password %L', :'app_password');
\gexec

alter role workhub_owner nosuperuser nocreatedb nocreaterole nobypassrls;
alter role workhub_app nosuperuser nocreatedb nocreaterole nobypassrls;

alter database :"database" owner to workhub_owner;
revoke all on database :"database" from workhub_app;
grant connect on database :"database" to workhub_app;
SQL

psql --set=ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
create extension if not exists pgcrypto;
alter schema public owner to workhub_owner;

do $$
declare
    obj record;
begin
    for obj in
        select c.relname, c.relkind
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
          and c.relowner <> 'workhub_owner'::regrole
          and not (
              c.relkind = 'S'
              and exists (
                  select 1
                  from pg_depend d
                  where d.classid = 'pg_class'::regclass
                    and d.objid = c.oid
                    and d.deptype = 'i'
              )
          )
    loop
        if obj.relkind in ('r', 'p') then
            execute format('alter table public.%I owner to workhub_owner', obj.relname);
        elsif obj.relkind = 'S' then
            execute format('alter sequence public.%I owner to workhub_owner', obj.relname);
        elsif obj.relkind = 'v' then
            execute format('alter view public.%I owner to workhub_owner', obj.relname);
        elsif obj.relkind = 'm' then
            execute format('alter materialized view public.%I owner to workhub_owner', obj.relname);
        elsif obj.relkind = 'f' then
            execute format('alter foreign table public.%I owner to workhub_owner', obj.relname);
        end if;
    end loop;

    for obj in
        select p.oid, p.proname, pg_get_function_identity_arguments(p.oid) as args
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proowner <> 'workhub_owner'::regrole
          and not exists (
              select 1
              from pg_depend d
              where d.classid = 'pg_proc'::regclass
                and d.objid = p.oid
                and d.deptype = 'e'
          )
    loop
        execute format(
            'alter function public.%I(%s) owner to workhub_owner',
            obj.proname,
            obj.args
        );
    end loop;
end
$$;
SQL

printf 'Rôles %s/%s initialisés et objets transférés.\n' "$owner_user" "$app_user"
