# Private testing deployment

The deployment image serves the compiled React UI and FastAPI on one origin. PostgreSQL is isolated on the Docker network, source workbooks live in durable storage, and Caddy protects **all UI/API routes** with a login. For a real hostname Caddy provisions HTTPS automatically. No app or database port is published directly.

The deployment is a **separate test copy** of the inventory database and sources. Testing approvals, dispatches and receipts must stay in that copy. The original development database is not modified by deployment.

## Target required

A server with Docker Compose and a DNS hostname pointing to it is needed to publish this stack. This chat currently has no hosting connection or deployment server. Choosing a provider can require provisioning and billing; do that in the provider's account and supply the resulting connection through a supported secure mechanism. Never send passwords or keys in chat.

## Prepare

1. Copy this repository to the chosen host, excluding `.venv`, `node_modules`, development caches and local secrets.
2. Copy `deploy/.env.example` to `deploy/.env`. Set the hostname, a unique URL-safe database password and login name. Set `RG_BIND_ADDRESS=0.0.0.0` on the selected public host. Keep `deploy/.env` private with mode 600.
3. Generate the login password hash interactively with `docker run --rm -it caddy:2-alpine caddy hash-password`. Put only the bcrypt hash in `RG_AUTH_HASH`, single-quoted in `.env`. Exchange the actual login password through your usual secure channel.
4. Refresh the source backup on the development machine with `./scripts/snapshot-db.sh`. Transfer the dump and `data/sources` securely to `deploy/staging-data` on the host. Retain original source file paths by mounting this directory at `/workspace/dhruva/data`. Grant this source directory to the application container's UID/GID 10001; do not make it world-writable.

## Start and restore

Run from the repository root:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml -p rg-stock-test up -d db
```

Wait for the DB to be healthy. Restore **only into a new empty staging database**, before starting the application (startup creates tables). First inspect:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml -p rg-stock-test exec -T db \
  psql -U rg -d rgstock -Atc "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
```

If the result is exactly zero:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml -p rg-stock-test exec -T db \
  pg_restore -U rg -d rgstock --exit-on-error < deploy/staging-data/rgstock.dump
docker compose --env-file deploy/.env -f deploy/compose.yaml -p rg-stock-test up -d --build
```

Never reset or overwrite a populated database to resolve an installation problem. Existing databases need a reviewed migration/restore procedure.

## Acceptance tests

- An anonymous request to the UI and `/api/dashboard` must return 401.
- Log in through HTTPS and open the compiled UI; its assets and API must load on the same origin.
- `/api/health` must report PostgreSQL and OR-Tools.
- Confirm snapshot #3, 14,151 labels, original ages, IK confirmed zero, saved simulation #1, 749 HO proposals, 434 CZ recalls and five HO CZ reuse labels.
- Gold, natural and lab-grown diamond tabs must remain separate.
- The tested source rule is compared, not active. Sales history is pending; demand/profit scores stay unavailable.
- Use the isolated database to test draft → simulate → compare → approve → activate and separate dispatch/receipt steps; retain audit references.
- Back up PostgreSQL and source storage together before changing or restarting the test deployment.

Local container validation uses an HTTP endpoint bound to loopback, a throwaway test login and a copied database. This proves the image/proxy/database workflow; it is not a public deployment or proof that DNS/HTTPS work on the eventual hosting target.
