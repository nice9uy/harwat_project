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
# Memory and parallelism come from prod.sh, which sizes them to the machine.
# max_connections and max_worker_processes stay at their defaults on purpose:
# a standby refuses to start when its own are lower than the primary's.
exec docker-entrypoint.sh postgres -c wal_level=replica -c max_wal_senders=10 -c wal_keep_size=1GB -c hot_standby=on \
    -c shared_buffers="${PG_SHARED_BUFFERS_MB:-128}MB" \
    -c effective_cache_size="${PG_EFFECTIVE_CACHE_MB:-4096}MB" \
    -c work_mem="${PG_WORK_MEM_MB:-4}MB" \
    -c maintenance_work_mem="${PG_MAINTENANCE_MB:-64}MB" \
    -c max_parallel_workers_per_gather="${PG_PARALEL:-2}" \
    -c random_page_cost=1.1 -c effective_io_concurrency=200 \
    -c checkpoint_completion_target=0.9 -c wal_compression=on
