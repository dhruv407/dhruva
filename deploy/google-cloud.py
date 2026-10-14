"""First private staging deployment. Run in authenticated Google Cloud Shell.

Credentials stay in Google Cloud Shell/Secret Manager. No private keys are needed.
Existing Cloud SQL instances with this deployment name are never overwritten.
"""

import argparse
import gzip
import json
import os
import re
import secrets
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args, capture=False):
    command = ["gcloud", *args, "--project", PROJECT, "--quiet"]
    result = subprocess.run(
        command, check=True, text=True, stdout=subprocess.PIPE if capture else None
    )
    return result.stdout.strip() if capture else None


def sql_user(password):
    token = cli("auth", "print-access-token", capture=True)
    request = urllib.request.Request(
        f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances/{INSTANCE}/users",
        data=json.dumps({"name": "rg", "password": password}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            operation = json.load(response)["name"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Cloud SQL user creation failed with HTTP {error.code}; credentials were not logged"
        ) from None
    cli("sql", "operations", "wait", operation, "--timeout=300")


def main():
    global PROJECT, INSTANCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="dhruva-511613")
    parser.add_argument("--region", default="asia-south1")
    parser.add_argument(
        "--empty-data",
        action="store_true",
        help="Deploy a new empty inventory database; upload stock through the app after sign-in",
    )
    parser.add_argument(
        "--testers",
        default="",
        help="Comma-separated Google user emails; defaults to signed-in deployer",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create the declared staging resources and deploy",
    )
    args = parser.parse_args()
    PROJECT = args.project
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", PROJECT):
        raise ValueError("Provide a valid Google Cloud project ID")
    if not re.fullmatch(r"[a-z]+-[a-z]+\d", args.region):
        raise ValueError("Provide a valid Google Cloud region")
    service = "rg-stock-test"
    INSTANCE = service + "-db"
    bucket = PROJECT + "-rg-stock-test-sources"
    build_bucket = PROJECT + "-rg-stock-test-build"
    repository = "rg-stock"
    secret = service + "-database-url"
    runtime = service + "-app@" + PROJECT + ".iam.gserviceaccount.com"
    builder = service + "-build@" + PROJECT + ".iam.gserviceaccount.com"
    image = f"{args.region}-docker.pkg.dev/{PROJECT}/{repository}/app:staging"
    plan = {
        "project": PROJECT,
        "region": args.region,
        "service": service,
        "database": {
            "name": INSTANCE,
            "version": "PostgreSQL 16",
            "tier": "db-f1-micro",
            "storage_gb": 10,
            "availability": "single zone",
        },
        "cloud_run": {
            "cpu": 2,
            "memory": "2Gi",
            "min_instances": 0,
            "max_instances": 1,
            "concurrency": 4,
        },
        "source_bucket": bucket,
        "access": "Google IAP, named users only",
        "restore": "new empty test database; upload stock through the UI"
        if args.empty_data
        else "separate test database and source copy",
        "cost_note": "Cloud SQL has ongoing charges even while Cloud Run scales to zero.",
    }
    print(json.dumps(plan, indent=2))
    if not args.apply:
        return
    os.chdir(ROOT)
    account = cli(
        "auth",
        "list",
        "--filter=status:ACTIVE",
        "--format=value(account)",
        capture=True,
    )
    testers = [v.strip() for v in (args.testers or account).split(",") if v.strip()]
    if not testers or any(
        not re.fullmatch(r"[^\s@,]+@[^\s@,]+\.[^\s@,]+", v) for v in testers
    ):
        raise ValueError(
            "An authenticated account and valid Google tester emails are required"
        )
    cli("projects", "describe", PROJECT, "--format=value(projectId)")
    if (
        cli(
            "billing",
            "projects",
            "describe",
            PROJECT,
            "--format=value(billingEnabled)",
            capture=True,
        ).lower()
        != "true"
    ):
        raise RuntimeError(
            "Enable billing in the selected project before deployment; no billing account is attached automatically"
        )
    backup = ROOT / "data" / "bootstrap.sql.gz"
    empty_bootstrap = None
    if args.empty_data:
        empty_bootstrap = tempfile.TemporaryDirectory(prefix="rg-empty-bootstrap-")
        backup = Path(empty_bootstrap.name) / "bootstrap.sql.gz"
        with gzip.open(backup, "wb") as stream:
            stream.write(
                b"GRANT CONNECT ON DATABASE rgstock TO rg;\nGRANT USAGE, CREATE ON SCHEMA public TO rg;\n"
            )
    elif not backup.is_file() or not (ROOT / "data" / "sources").is_dir():
        raise RuntimeError(
            "The prepared database export and source files must be present in the deployment bundle"
        )
    # Validate the gzip before creating resources. Contents are never printed.
    with gzip.open(backup, "rb") as stream:
        while stream.read(1024 * 1024):
            pass
    cli(
        "services",
        "enable",
        "run.googleapis.com",
        "sqladmin.googleapis.com",
        "storage.googleapis.com",
        "artifactregistry.googleapis.com",
        "cloudbuild.googleapis.com",
        "secretmanager.googleapis.com",
        "iap.googleapis.com",
    )
    existing = cli(
        "sql",
        "instances",
        "list",
        "--filter=name=" + INSTANCE,
        "--format=value(name)",
        capture=True,
    )
    if existing:
        raise RuntimeError(
            "The staging SQL instance already exists. Stop and inspect the previous deployment; this script will not reset it or replay the restore."
        )
    cli(
        "iam",
        "service-accounts",
        "create",
        service + "-app",
        "--display-name=RG Stock test runtime",
    )
    cli(
        "iam",
        "service-accounts",
        "create",
        service + "-build",
        "--display-name=RG Stock test builder",
    )
    cli(
        "projects",
        "add-iam-policy-binding",
        PROJECT,
        "--member=serviceAccount:" + runtime,
        "--role=roles/cloudsql.client",
    )
    cli(
        "projects",
        "add-iam-policy-binding",
        PROJECT,
        "--member=serviceAccount:" + builder,
        "--role=roles/logging.logWriter",
    )
    for name in (bucket, build_bucket):
        cli(
            "storage",
            "buckets",
            "create",
            "gs://" + name,
            "--location=" + args.region,
            "--uniform-bucket-level-access",
            "--public-access-prevention",
        )
    cli(
        "storage",
        "buckets",
        "add-iam-policy-binding",
        "gs://" + bucket,
        "--member=serviceAccount:" + runtime,
        "--role=roles/storage.objectUser",
    )
    cli(
        "storage",
        "buckets",
        "add-iam-policy-binding",
        "gs://" + build_bucket,
        "--member=serviceAccount:" + builder,
        "--role=roles/storage.objectViewer",
    )
    cli(
        "artifacts",
        "repositories",
        "create",
        repository,
        "--repository-format=docker",
        "--location=" + args.region,
    )
    cli(
        "artifacts",
        "repositories",
        "add-iam-policy-binding",
        repository,
        "--location=" + args.region,
        "--member=serviceAccount:" + builder,
        "--role=roles/artifactregistry.writer",
    )
    cli(
        "sql",
        "instances",
        "create",
        INSTANCE,
        "--database-version=POSTGRES_16",
        "--edition=ENTERPRISE",
        "--tier=db-f1-micro",
        "--region=" + args.region,
        "--availability-type=zonal",
        "--storage-size=10",
        "--storage-auto-increase",
        "--deletion-protection",
    )
    cli("sql", "databases", "create", "rgstock", "--instance=" + INSTANCE)
    password = secrets.token_hex(32)
    database_url = f"postgresql+psycopg://rg:{password}@/rgstock?host=/cloudsql/{PROJECT}:{args.region}:{INSTANCE}"
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as file:
        file.write(database_url)
        credential_path = file.name
    try:
        os.chmod(credential_path, 0o600)
        cli(
            "secrets",
            "create",
            secret,
            "--replication-policy=automatic",
            "--data-file=" + credential_path,
        )
    finally:
        Path(credential_path).unlink(missing_ok=True)
    sql_user(password)
    del password, database_url
    cli(
        "secrets",
        "add-iam-policy-binding",
        secret,
        "--member=serviceAccount:" + runtime,
        "--role=roles/secretmanager.secretAccessor",
    )
    sql_account = cli(
        "sql",
        "instances",
        "describe",
        INSTANCE,
        "--format=value(serviceAccountEmailAddress)",
        capture=True,
    )
    cli(
        "storage",
        "buckets",
        "add-iam-policy-binding",
        "gs://" + bucket,
        "--member=serviceAccount:" + sql_account,
        "--role=roles/storage.objectViewer",
    )
    cli("storage", "cp", str(backup), "gs://" + bucket + "/bootstrap.sql.gz")
    if not args.empty_data:
        cli(
            "storage",
            "rsync",
            str(ROOT / "data" / "sources"),
            "gs://" + bucket + "/sources",
            "--recursive",
        )
    cli(
        "sql",
        "import",
        "sql",
        INSTANCE,
        "gs://" + bucket + "/bootstrap.sql.gz",
        "--database=rgstock",
        "--user=postgres",
    )
    cli("storage", "rm", "gs://" + bucket + "/bootstrap.sql.gz")
    if empty_bootstrap is not None:
        empty_bootstrap.cleanup()
    cli(
        "builds",
        "submit",
        "--config=deploy/cloudbuild.yaml",
        "--substitutions=_RG_IMAGE=" + image,
        "--service-account=projects/" + PROJECT + "/serviceAccounts/" + builder,
        "--gcs-source-staging-dir=gs://" + build_bucket + "/source",
        "--timeout=1200",
    )
    cli(
        "run",
        "deploy",
        service,
        "--image=" + image,
        "--region=" + args.region,
        "--service-account=" + runtime,
        "--execution-environment=gen2",
        "--port=8000",
        "--cpu=2",
        "--memory=2Gi",
        "--concurrency=4",
        "--timeout=300",
        "--min-instances=0",
        "--max-instances=1",
        "--iap",
        "--no-allow-unauthenticated",
        "--add-cloudsql-instances=" + PROJECT + ":" + args.region + ":" + INSTANCE,
        "--update-secrets=DATABASE_URL=" + secret + ":1",
        "--add-volume=name=stock-sources,type=cloud-storage,bucket="
        + bucket
        + ",mount-options=uid=10001;gid=10001;file-mode=0600;dir-mode=0700",
        "--add-volume-mount=volume=stock-sources,mount-path=/workspace/dhruva/data",
    )
    number = cli(
        "projects", "describe", PROJECT, "--format=value(projectNumber)", capture=True
    )
    cli(
        "run",
        "services",
        "add-iam-policy-binding",
        service,
        "--region=" + args.region,
        "--member=serviceAccount:service-"
        + number
        + "@gcp-sa-iap.iam.gserviceaccount.com",
        "--role=roles/run.invoker",
    )
    for tester in testers:
        cli(
            "iap",
            "web",
            "add-iam-policy-binding",
            "--resource-type=cloud-run",
            "--service=" + service,
            "--region=" + args.region,
            "--member=user:" + tester,
            "--role=roles/iap.httpsResourceAccessor",
        )
    url = cli(
        "run",
        "services",
        "describe",
        service,
        "--region=" + args.region,
        "--format=value(status.url)",
        capture=True,
    )
    print("Private testing URL:", url)
    print(
        "Sign in with an allowed Google account and run the acceptance checks in docs/google-cloud.md."
    )


if __name__ == "__main__":
    main()
