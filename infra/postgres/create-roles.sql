-- Create or update the three database roles. Safe to run repeatedly; it runs
-- the same way on first container start, from `make db-roles`, and in CI.
--
-- Run with psql, passing the passwords as variables:
--   psql -v owner_password=... -v app_password=... -v analyst_password=... -f create-roles.sql
--
-- Table-level grants live in a Django migration, so this file only creates
-- roles, sets their session defaults, and controls who may connect.

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I LOGIN', r)
FROM unnest(ARRAY['tallyproof_owner', 'tallyproof_app', 'tallyproof_analyst']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

ALTER ROLE tallyproof_owner WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_password';
ALTER ROLE tallyproof_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER ROLE tallyproof_analyst WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'analyst_password';

-- The analyst only ever reads curated views, inside short read-only transactions.
ALTER ROLE tallyproof_analyst SET default_transaction_read_only = on;
ALTER ROLE tallyproof_analyst SET statement_timeout = '3s';
ALTER ROLE tallyproof_analyst SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE tallyproof_analyst SET search_path = analyst;

-- Only these three roles may connect, and only the owner may create objects.
SELECT format('ALTER DATABASE %I OWNER TO tallyproof_owner', current_database()) \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO tallyproof_owner, tallyproof_app, tallyproof_analyst', current_database()) \gexec
ALTER SCHEMA public OWNER TO tallyproof_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO tallyproof_app;
