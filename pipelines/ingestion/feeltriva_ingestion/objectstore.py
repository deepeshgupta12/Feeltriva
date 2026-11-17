"""Raw source archives in private object storage (M1.12).

Handoff rules applied here:

- `docs/01` section 4: the first of four storage zones is "raw immutable objects".
- `docs/01` section 6: "S3-compatible private buckets, versioning ... Raw ZIPs, manifests ...;
  no public medical files".
- `docs/04`: every file -> "retain the original byte object".
- `docs/03`: data stays outside tracked source; URI and checksum manifests are recorded.

How immutability is kept:

- An archive is stored under a key that contains its SHA-256, so different bytes can never
  share a key. If a key already holds different content the upload is refused, never
  overwritten.
- The bucket has versioning enabled, so even a write made by other means cannot destroy the
  stored bytes.
- After every run each stored archive is downloaded again and hashed; only a matching digest
  counts as stored.

The store speaks plain S3, so any S3-compatible service can replace the local one.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine

from .archives import MANIFEST_PATH, RAW_DIR, Manifest, load_manifest, sha256_file, verify_all
from .cases import _raw_cursor

ARCHIVE_PREFIX = "raw/archives"
MANIFEST_PREFIX = "manifests/ingestion_manifest"


class ObjectStoreError(RuntimeError):
    pass


class ObjectStoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    object_storage_endpoint: str = ""
    object_storage_bucket: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_region: str = "us-east-1"


def make_client(settings: ObjectStoreSettings) -> Any:
    if not (
        settings.object_storage_endpoint
        and settings.object_storage_bucket
        and settings.object_storage_access_key
        and settings.object_storage_secret_key
    ):
        raise SystemExit("OBJECT_STORAGE_ENDPOINT, _BUCKET, _ACCESS_KEY and _SECRET_KEY are required")
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
        region_name=settings.object_storage_region,
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )


def archive_key(name: str, sha256: str) -> str:
    return f"{ARCHIVE_PREFIX}/{sha256}/{name}"


def _not_found(error: Exception) -> bool:
    code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
    status = getattr(error, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in ("404", "NoSuchKey", "NoSuchBucket", "NotFound") or status == 404


def ensure_bucket(s3: Any, bucket: str) -> dict[str, Any]:
    """Create the bucket if needed and make sure object versioning is on."""
    created = False
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception as error:
        if not _not_found(error):
            raise
        s3.create_bucket(Bucket=bucket)
        created = True
    if s3.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
        s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    status = s3.get_bucket_versioning(Bucket=bucket).get("Status")
    if status != "Enabled":
        raise ObjectStoreError(f"bucket {bucket}: versioning is {status!r}, expected 'Enabled'")
    return {"created": created, "versioning": status}


def _stored_digest(s3: Any, bucket: str, key: str) -> tuple[str, int]:
    """Download the object and hash what actually comes back."""
    digest = hashlib.sha256()
    size = 0
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    for block in iter(lambda: body.read(1024 * 1024), b""):
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def store_object(s3: Any, bucket: str, key: str, data: bytes, sha256: str, content_type: str) -> dict[str, Any]:
    """Store `data` under a content-addressed key, or confirm it is already there. Never overwrites."""
    uploaded = False
    version_id = None
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        version_id = head.get("VersionId")
    except Exception as error:
        if not _not_found(error):
            raise
        response = s3.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type, Metadata={"sha256": sha256}
        )
        version_id = response.get("VersionId")
        uploaded = True
    stored_sha, stored_size = _stored_digest(s3, bucket, key)
    if stored_sha != sha256:
        # Either the key held other content already, or the store returned different bytes.
        raise ObjectStoreError(
            f"{key}: stored object has SHA-256 {stored_sha}, expected {sha256}; it was not overwritten"
        )
    return {"key": key, "version_id": version_id, "size_bytes": stored_size, "uploaded": uploaded, "verified": True}


def anonymous_status(endpoint: str, bucket: str, key: str) -> int:
    """HTTP status of a request for the object with no credentials at all."""
    url = f"{endpoint.rstrip('/')}/{bucket}/{urllib.parse.quote(key)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - fixed scheme from settings
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def store_archives(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    settings: ObjectStoreSettings | None = None,
    s3: Any = None,
    manifest_path: Path | None = MANIFEST_PATH,
) -> dict[str, Any]:
    """Upload every source archive unchanged, verify each stored copy, and register it."""
    settings = settings or ObjectStoreSettings()
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)  # the local files must match the manifest before anything is uploaded
    s3 = s3 or make_client(settings)
    bucket = settings.object_storage_bucket
    result: dict[str, Any] = {"bucket": ensure_bucket(s3, bucket), "archives": {}, "manifest": None}
    engine = create_engine(database_url)
    with _raw_cursor(engine) as cur:
        for name, expected in manifest.archives.items():
            path = raw_dir / name
            local = sha256_file(path)
            if local != expected:  # verify_all already checked; kept as a guard against a race
                raise ObjectStoreError(f"{name}: local file changed during the run")
            key = archive_key(name, expected)
            stored = store_object(s3, bucket, key, path.read_bytes(), expected, "application/zip")
            stored["anonymous_http_status"] = anonymous_status(settings.object_storage_endpoint, bucket, key)
            if stored["anonymous_http_status"] < 400:
                raise ObjectStoreError(f"{key} can be read without credentials; the bucket must be private")
            object_uri = f"s3://{bucket}/{key}"
            cur.execute("SELECT sha256 FROM source_archives WHERE archive_name = %s", (name,))
            row = cur.fetchone()
            if row is not None and row[0] != expected:
                raise ObjectStoreError(f"{name} is registered with a different SHA-256 ({row[0]})")
            cur.execute(
                """INSERT INTO source_archives (archive_name, sha256, size_bytes, bucket, object_key, version_id,
                                                object_uri, verified_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                   ON CONFLICT (archive_name) DO UPDATE SET verified_at = now()""",
                (name, expected, stored["size_bytes"], bucket, key, stored["version_id"], object_uri),
            )
            stored["registered"] = row is None
            stored["object_uri"] = object_uri
            result["archives"][name] = stored
        if manifest_path is not None:
            data = manifest_path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            result["manifest"] = store_object(
                s3, bucket, f"{MANIFEST_PREFIX}/{digest}.json", data, digest, "application/json"
            )
        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE verified_at IS NOT NULL), coalesce(sum(size_bytes), 0) "
            "FROM source_archives WHERE archive_name = ANY(%s)",
            (list(manifest.archives),),
        )
        registered, verified, total = cur.fetchone()
        result["registry"] = {"archives": registered, "verified": verified, "bytes": int(total)}
    engine.dispose()
    return result


def check(result: dict[str, Any], manifest: Manifest | None = None) -> list[str]:
    manifest = manifest or load_manifest()
    diffs = []
    if result["bucket"]["versioning"] != "Enabled":
        diffs.append("bucket versioning is not enabled")
    for name in manifest.archives:
        stored = result["archives"].get(name)
        if stored is None or not stored["verified"]:
            diffs.append(f"{name}: not stored and verified")
        elif stored["anonymous_http_status"] < 400:
            diffs.append(f"{name}: readable without credentials")
    if result["registry"]["archives"] != len(manifest.archives) or result["registry"]["verified"] != len(
        manifest.archives
    ):
        diffs.append(f"registry holds {result['registry']} for {len(manifest.archives)} archives")
    return diffs


def describe(result: dict[str, Any]) -> str:
    return json.dumps(
        {name: {k: v for k, v in stored.items() if k != "object_uri"} for name, stored in result["archives"].items()},
        indent=1,
    )
