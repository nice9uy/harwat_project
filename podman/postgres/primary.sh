#!/bin/sh
# Entry point of the primary: lets the replication role in (also on a data
# directory made before replication was set up), then starts PostgreSQL the
# stock way, keeping enough WAL for a replica that was away for a while.
set -eu
HBA="$PGDATA/pg_hba.conf"
BARIS="host replication ${REPLIKASI_USER} all scram-sha-256"
if [ -f "$HBA" ] && ! grep -qF "$BARIS" "$HBA"; then
    echo "$BARIS" >> "$HBA"
fi
exec docker-entrypoint.sh postgres -c wal_level=replica -c max_wal_senders=10 -c wal_keep_size=1GB -c hot_standby=on
