#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/models/df_schemes/ragapp/
alembic upgrade head
cd /app
echo "Starting application server..."
exec "$@"