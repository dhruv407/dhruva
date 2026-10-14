# RG Stock Engine

For private deployment to Google Cloud project `dhruva-511613`, use [the Cloud Shell deployment guide](docs/google-cloud.md). [Docker staging instructions](docs/deployment.md) describe the compiled UI/API, database copy and authentication gateway.

Internal Right Gold inventory planning, built with FastAPI, PostgreSQL, React/TypeScript and OR-Tools CP-SAT.

Start with [the schema and import workflow](docs/schema.md). [Sales export requirements](docs/sales-export-request.md) describe the outstanding historical data. No business data is fabricated; supplied files are retained locally under ignored `data/sources/`.

## Run locally

Requires Python 3.12+, uv, Node 22+ and Docker (or an existing PostgreSQL database via `DATABASE_URL`). Use the existing checkout; cloud tasks are already isolated, so no worktree is needed.

```bash
./scripts/install.sh
./scripts/start.sh
```

The API listens on port 8000 and the React development server on 5173. The UI proxies `/api` to the API. Verify `GET /api/health` reports PostgreSQL; the interactive API contract is served at `/docs` on the API. These are development services, not a published production deployment.

`DATABASE_URL` selects an external PostgreSQL instance; `RG_DATA_DIR` selects durable source-workbook storage. Local Docker uses development-only credentials. Dependencies are locked in `backend/uv.lock` and `frontend/package-lock.json`.

## First workflow

1. Enter an operator name in the footer. Upload the latest export under **Data & imports**.
2. For standard `.xlsx` inputs, explicitly map fields. For the supplied Ornate 22-column `.xls` report, the verified adapter parses branch sections and report totals. Confirm cost, age and HO usability only when their meaning is known.
3. Resolve blocking errors. Declare branch coverage and reconcile report counts/costs. IK missing is never interpreted as zero. The user must approve the physical baseline.
4. Import the Right Gold planning workbook into a new draft. The adapter reads its 227 literal provisional L/M/H bands, retaining formula-based mix controls as source text for review. It does not execute macros, formulas, old commands or prior proposals. Supplier rules remain unsupplied.
5. Upload label sales history when available. Demand and realised profit cannot be inferred from label age or approximated sale prices.
6. Clone/edit rules, simulate, compare on identical source snapshots, approve, activate. Initial rules are a draft; the first comparison uses explicitly disclosed initial defaults as the bootstrap baseline.
7. Review proposals, approve individual transfers, and record each dispatch and receipt. Branch exchanges use two legs through HO; stock becomes in-transit on dispatch. Original age and whole sets remain intact. CZ **varieties** are recalled/held for reuse and never ordinarily redistributed.

Gold allocation targets default to **net-weight share** (as defined by the supplied workbook); natural and lab-grown diamonds default to separate cost shares. Targets are NV 24%, LN 16%, AR 19%, RO 19%, IK 22%. Costs still determine aged-cost exposure, so heavy/expensive old labels are included. Allocation basis is versioned and editable. Solver weights are planning assumptions, not empirical business calibration.

Margin basis is recorded as **net sale value = gold weight × current RG rate + making**, confirmed in chat. Margin estimates require that explicitly mapped field; source `Sales Value (Today's)` is not automatically substituted. Exported full landed cost can be used when its meaning is confirmed. ₹15,000/ct natural and ₹7,000/ct lab-grown costs remain provisional and are never silently inserted into source costs. Stone profitability stays unconfigured.

The assistant panel defaults to local command interpretation. Optional AI explanations use the OpenAI Responses API: add `RG_AI_API_KEY` securely in environment settings and optionally set `RG_AI_MODEL` (default `gpt-4.1-mini`). Enable **Use AI explanation** in the panel when configured. This sends the command, rule/provenance metadata and computed summaries to the provider; original workbooks and label lists are not included. AI only returns a schema-validated navigation/explanation response; it cannot calculate, approve or execute movements. Provider access needs `api.openai.com`. Live provider validation requires a supplied key. Financial turnover needs average historical inventory and COGS; the dashboard's sales/current-units metric is labelled a proxy.

## Verification

```bash
cd backend
.venv/bin/pytest -q
```

Tests use an isolated SQLite file by default. To test real PostgreSQL, create a disposable database and set `RG_TEST_DATABASE_URL` (tests recreate its schema; never point it at your app database):

```bash
docker exec rg-stock-postgres createdb -U rg rgstock_test
cd backend
RG_TEST_DATABASE_URL=postgresql+psycopg://rg:rg_local_dev@127.0.0.1:5432/rgstock_test .venv/bin/pytest -q
```

React: `cd frontend && npm run build`. Browser checks use an isolated `rgstock_e2e` database: create it, then run `npm exec -- playwright test`. `CHROMIUM_PATH` defaults to `/usr/bin/chromium`; install a Playwright browser and adjust this path where necessary. The real-file browser check requires the supplied attachment to exist; synthetic/unit verification remains independent.

## Persistence and deployment limits

Docker volumes and live processes are outside the cloud filesystem snapshot contract. **Before publishing an environment**, run `./scripts/snapshot-db.sh`. This saves a verified PostgreSQL dump under ignored `data/`; `database.sh` restores it only into a newly created empty local database. Source workbooks must be retained alongside it. For a managed PostgreSQL database, use its supported backup process instead. Never overwrite a populated database automatically.

Production still needs authentication/roles, reviewed operational permissions, Alembic migrations, encrypted durable storage and backups. This first version uses named-actor attribution and schema creation on startup, suitable for a private development workspace. Source files and original facts are not editable through the API; corrections require new imports.

Generic sale import currently accepts completed positive sale rows. Returns, partial sales, multiple sales of the same label and composite invoice identities require an explicit adapter before net-demand/turnover analysis. User-supplied files and mappings are always data, not executable instructions.
