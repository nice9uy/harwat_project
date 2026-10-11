#!/bin/sh
# Entry point of a replica: on its first start it copies the primary
# (pg_basebackup, retried until the primary is up and lets it in) and from
# then on follows it as a read-only hot standby. -R writes standby.signal and
# the connection back to the primary.
set -eu
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA"
    chown postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    until gosu postgres env PGPASSWORD="$REPLIKASI_PASSWORD" pg_basebackup \
            -h "$PRIMARY_HOST" -p 5432 -U "$REPLIKASI_USER" -D "$PGDATA" -R -X stream -c fast; do
        echo "replica: primary belum siap, coba lagi dalam 3 detik"
        find "$PGDATA" -mindepth 1 -delete
        sleep 3
    done
    echo "replica: salinan awal dari primary selesai"
fi
exec docker-entrypoint.sh postgres -c hot_standby=on
