#!/usr/bin/env bash
set -euo pipefail
RG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$RG_ROOT/data"
umask 077
docker exec rg-stock-postgres pg_dump -U rg -d rgstock -Fc > "$RG_ROOT/data/rgstock.dump.tmp"
mv "$RG_ROOT/data/rgstock.dump.tmp" "$RG_ROOT/data/rgstock.dump"
docker exec -i rg-stock-postgres pg_restore --list < "$RG_ROOT/data/rgstock.dump" >/dev/null
printf 'Verified database snapshot saved in data/rgstock.dump\n'
