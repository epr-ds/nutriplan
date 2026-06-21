-- Bootstraps the per-service databases on first Postgres init.
-- (Runs only when the data directory is empty.)
CREATE DATABASE identity;
CREATE DATABASE identity_test;
