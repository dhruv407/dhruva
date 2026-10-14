#!/usr/bin/env bash
set -euo pipefail
RG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Local development credentials only. Production credentials belong in environment settings.
if docker inspect rg-stock-postgres >/dev/null 2>&1; then
  docker start rg-stock-postgres >/dev/null
  RG_NEW_DATABASE=false
else
  docker run -d --name rg-stock-postgres --restart unless-stopped \
    -e POSTGRES_USER=rg -e POSTGRES_PASSWORD=rg_local_dev -e POSTGRES_DB=rgstock \
    -p 127.0.0.1:5432:5432 \
    -v rg-stock-postgres-data:/var/lib/postgresql/data \
    postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea >/dev/null
  RG_NEW_DATABASE=true
fi
for attempt in {1..30}; do
  if docker exec rg-stock-postgres pg_isready -U rg -d rgstock >/dev/null; then break; fi
  sleep 1
done
docker exec rg-stock-postgres pg_isready -U rg -d rgstock
if "$RG_NEW_DATABASE" && [[ -f "$RG_ROOT/data/rgstock.dump" ]]; then
  RG_TABLE_COUNT="$(docker exec rg-stock-postgres psql -U rg -d rgstock -Atc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
  if [[ "$RG_TABLE_COUNT" == 0 ]]; then
    docker exec -i rg-stock-postgres pg_restore -U rg -d rgstock --exit-on-error < "$RG_ROOT/data/rgstock.dump"
  fi
fi
