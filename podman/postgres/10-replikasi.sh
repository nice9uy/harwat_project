#!/bin/sh
# Runs once, when the primary's data directory is first created: the role the
# replicas stream with, and permission for it to connect. (prod.sh repeats the
# role for a primary whose data directory already existed, and primary.sh the
# pg_hba line.)
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE ROLE "${REPLIKASI_USER}" WITH REPLICATION LOGIN PASSWORD '${REPLIKASI_PASSWORD}';
SQL
echo "host replication ${REPLIKASI_USER} all scram-sha-256" >> "$PGDATA/pg_hba.conf"
