#!/bin/sh
set -eu

# Named volumes created by earlier releases can be root-owned. Normalize the
# dedicated data directory before starting, then run the web process as an
# unprivileged account. /data is the only mutable path in the production image.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data/uploads
    chown -R --no-dereference appuser:appuser /data
    exec setpriv --reuid=10001 --regid=10001 --init-groups -- "$@"
fi

exec "$@"
