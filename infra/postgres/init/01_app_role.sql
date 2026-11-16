-- Local development only. Creates the least-privilege login the API uses, so row-level
-- security is actually exercised (the POSTGRES_USER superuser would bypass it).
-- Never reuse this password outside a developer machine.
CREATE ROLE feeltriva_app LOGIN PASSWORD 'feeltriva_app_dev';
CREATE DATABASE feeltriva_test OWNER feeltriva;
