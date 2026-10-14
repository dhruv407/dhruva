"""Create a private Cloud Shell bundle without caches, Git metadata or credentials."""

import gzip
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "deployment"
OUT.mkdir(parents=True, exist_ok=True)
bootstrap = DATA / "bootstrap.sql.gz"
with gzip.open(bootstrap, "wb") as stream:
    process = subprocess.Popen(
        [
            "docker",
            "exec",
            "rg-stock-postgres",
            "pg_dump",
            "-U",
            "rg",
            "-d",
            "rgstock",
            "--no-owner",
            "--no-acl",
        ],
        stdout=subprocess.PIPE,
    )
    assert process.stdout is not None
    with process.stdout:
        while chunk := process.stdout.read(1024 * 1024):
            stream.write(chunk)
    if process.wait() != 0:
        raise RuntimeError("Database export failed; no deployable archive was produced")
    stream.write(
        b"\nGRANT CONNECT ON DATABASE rgstock TO rg;\nGRANT USAGE, CREATE ON SCHEMA public TO rg;\nGRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO rg;\nGRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO rg;\nALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO rg;\nALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO rg;\n"
    )

with gzip.open(bootstrap, "rb") as stream:
    header = stream.read(1024)
    assert b"PostgreSQL database dump" in header
    while stream.read(1024 * 1024):
        pass  # Validate the entire compressed stream and its checksum.

skip = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "test-results",
    "playwright-report",
    "staging-data",
}
archive = OUT / "rg-stock-google-cloud.tar.gz"
with tarfile.open(archive, "w:gz") as tar:
    for folder in ["backend", "frontend", "deploy", "docs", "scripts"]:
        for file in sorted((ROOT / folder).rglob("*")):
            relative = file.relative_to(ROOT)
            if (
                not file.is_file()
                or file.is_symlink()
                or any(p in skip for p in relative.parts)
            ):
                continue
            if (
                file.name == ".env"
                or file.suffix in (".log", ".pyc")
                or file.name.endswith(".tsbuildinfo")
            ):
                continue
            tar.add(file, arcname=str(Path("rg-stock-google-cloud") / relative))
    for name in [
        "Dockerfile",
        ".dockerignore",
        ".gcloudignore",
        ".gitignore",
        "README.md",
    ]:
        tar.add(ROOT / name, arcname="rg-stock-google-cloud/" + name)
    tar.add(bootstrap, arcname="rg-stock-google-cloud/data/bootstrap.sql.gz")
    for file in sorted((DATA / "sources").iterdir()):
        if file.is_file() and file.suffix in (".xls", ".xlsx"):
            tar.add(file, arcname="rg-stock-google-cloud/data/sources/" + file.name)
with tarfile.open(archive, "r:gz") as tar:
    names = tar.getnames()
    assert "rg-stock-google-cloud/data/bootstrap.sql.gz" in names
    assert not any(
        "/.env" == name[-5:] or "/node_modules/" in name or "/.venv/" in name
        for name in names
    )
print("Private deployment bundle:", archive)
print("Files:", len(names), "Bytes:", archive.stat().st_size)
