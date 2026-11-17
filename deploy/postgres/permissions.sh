#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB requis}"
: "${WORKHUB_OWNER_PASSWORD:?WORKHUB_OWNER_PASSWORD requis}"

export PGPASSWORD="$WORKHUB_OWNER_PASSWORD"

psql --set=ON_ERROR_STOP=1 \
    --username workhub_owner --dbname "$POSTGRES_DB" <<'SQL'
revoke create on schema public from public;
revoke create on schema public from workhub_app;
grant usage on schema public to workhub_app;

grant select, insert, update, delete on all tables in schema public to workhub_app;
grant usage, select on all sequences in schema public to workhub_app;

alter default privileges for role workhub_owner in schema public
    grant select, insert, update, delete on tables to workhub_app;
alter default privileges for role workhub_owner in schema public
    grant usage, select on sequences to workhub_app;

do $$
begin
    if to_regclass('public.audit_log') is not null then
        execute 'revoke update, delete, truncate on public.audit_log from workhub_app';
    end if;
end
$$;
SQL

printf 'Privilèges runtime accordés à workhub_app.\n'
