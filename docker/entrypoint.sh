#!/bin/sh
# Bring the schema up to date, then hand PID 1 to the server.
set -e

echo "[entrypoint] applying migrations"
alembic upgrade head

# `exec` replaces this shell, so the server becomes PID 1 and receives SIGTERM
# directly. Without it, stopping the container waits out the full kill timeout.
echo "[entrypoint] starting: $*"
exec "$@"
