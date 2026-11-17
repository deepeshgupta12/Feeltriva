"""Raw archives in private object storage.

Unit tests use an in-memory stand-in for the S3 client. The integration test talks to a real
S3-compatible store and runs only when TEST_OBJECT_STORAGE_ENDPOINT is set (with the PostgreSQL
test variables), for example the `objectstore` service of infra/docker-compose.yml.
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.objectstore import (
    ObjectStoreError,
    ObjectStoreSettings,
    anonymous_status,
    archive_key,
    check,
    ensure_bucket,
    make_client,
    store_archives,
    store_object,
)


class _NotFound(Exception):
    response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}


class FakeS3:
    """Just enough of the S3 API: buckets, versioned objects, metadata."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict] = {}
        self.puts = 0
        self.corrupt_reads = False

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise _NotFound()

    def create_bucket(self, Bucket):
        self.buckets[Bucket] = {"versioning": None, "objects": {}}

    def get_bucket_versioning(self, Bucket):
        status = self.buckets[Bucket]["versioning"]
        return {"Status": status} if status else {}

    def put_bucket_versioning(self, Bucket, VersioningConfiguration):
        self.buckets[Bucket]["versioning"] = VersioningConfiguration["Status"]

    def head_object(self, Bucket, Key):
        versions = self.buckets[Bucket]["objects"].get(Key)
        if not versions:
            raise _NotFound()
        return {"VersionId": f"v{len(versions)}", "ContentLength": len(versions[-1][0]), "Metadata": versions[-1][1]}

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        self.puts += 1
        versions = self.buckets[Bucket]["objects"].setdefault(Key, [])
        versions.append((bytes(Body), dict(Metadata)))
        return {"VersionId": f"v{len(versions)}"}

    def get_object(self, Bucket, Key):
        data = self.buckets[Bucket]["objects"][Key][-1][0]
        return {"Body": io.BytesIO(data[:-1] + b"?" if self.corrupt_reads else data)}


def test_keys_are_content_addressed():
    assert archive_key("archive(11).zip", "ab" * 32) == f"raw/archives/{'ab' * 32}/archive(11).zip"
    assert archive_key("a.zip", "1" * 64) != archive_key("a.zip", "2" * 64)  # different bytes, different key


def test_bucket_is_created_private_with_versioning():
    s3 = FakeS3()
    assert ensure_bucket(s3, "raw") == {"created": True, "versioning": "Enabled"}
    assert ensure_bucket(s3, "raw") == {"created": False, "versioning": "Enabled"}  # idempotent


def test_store_is_verified_idempotent_and_never_overwrites():
    s3 = FakeS3()
    ensure_bucket(s3, "raw")
    data = b"original archive bytes"
    sha = hashlib.sha256(data).hexdigest()
    key = archive_key("a.zip", sha)
    first = store_object(s3, "raw", key, data, sha, "application/zip")
    assert first == {"key": key, "version_id": "v1", "size_bytes": len(data), "uploaded": True, "verified": True}
    second = store_object(s3, "raw", key, data, sha, "application/zip")
    assert (second["uploaded"], second["verified"], s3.puts) == (False, True, 1)  # confirmed, not re-uploaded

    # Something else already sits at a key: refuse, and leave it exactly as it was.
    other_key = archive_key("b.zip", sha)
    s3.put_object("raw", other_key, b"different bytes", "application/zip", {})
    with pytest.raises(ObjectStoreError, match="was not overwritten"):
        store_object(s3, "raw", other_key, data, sha, "application/zip")
    assert s3.buckets["raw"]["objects"][other_key] == [(b"different bytes", {})]

    # The store hands back altered bytes: the upload does not count as stored.
    s3.corrupt_reads = True
    with pytest.raises(ObjectStoreError, match="expected"):
        store_object(s3, "raw", archive_key("c.zip", sha), data, sha, "application/zip")


def test_anonymous_status_reports_what_an_unauthenticated_client_gets():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if "public" in self.path else 403)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        assert anonymous_status(endpoint, "private", "raw/a b(1).zip") == 403
        assert anonymous_status(endpoint, "public", "raw/a.zip") == 200
    finally:
        server.shutdown()


def test_missing_configuration_is_refused():
    with pytest.raises(SystemExit, match="OBJECT_STORAGE"):
        make_client(ObjectStoreSettings(_env_file=None, object_storage_endpoint="http://x", object_storage_bucket="b"))


LIVE = pytest.mark.skipif(
    not (os.environ.get("TEST_OBJECT_STORAGE_ENDPOINT") and os.environ.get("TEST_MIGRATION_DATABASE_URL")),
    reason="set TEST_OBJECT_STORAGE_ENDPOINT (and the PostgreSQL test variables) to run against a real store",
)


@LIVE
def test_real_store_keeps_archives_unchanged_private_and_versioned(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    archive = f"store-{tag}.zip"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.csv", f"disease,f1\nFlu {tag},1\n")
    sha = sha256_file(path)
    manifest = Manifest({archive: sha}, [], [])
    settings = ObjectStoreSettings(
        _env_file=None,
        object_storage_endpoint=os.environ["TEST_OBJECT_STORAGE_ENDPOINT"],
        object_storage_bucket=f"feeltriva-test-{tag}",
        object_storage_access_key=os.environ.get("TEST_OBJECT_STORAGE_ACCESS_KEY", "feeltriva"),
        object_storage_secret_key=os.environ.get("TEST_OBJECT_STORAGE_SECRET_KEY", "feeltriva_dev_storage"),
    )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]

    result = store_archives(tmp_path, url, manifest, settings, manifest_path=None)
    stored = result["archives"][archive]
    assert check(result, manifest) == []
    assert result["bucket"] == {"created": True, "versioning": "Enabled"}
    assert (stored["uploaded"], stored["verified"], stored["registered"]) == (True, True, True)
    assert stored["size_bytes"] == path.stat().st_size and stored["anonymous_http_status"] in (401, 403)
    assert stored["object_uri"] == f"s3://feeltriva-test-{tag}/raw/archives/{sha}/{archive}"

    s3 = make_client(settings)
    body = s3.get_object(Bucket=settings.object_storage_bucket, Key=stored["key"])["Body"].read()
    assert body == path.read_bytes()  # byte for byte

    again = store_archives(tmp_path, url, manifest, settings, manifest_path=None)
    assert (again["archives"][archive]["uploaded"], again["archives"][archive]["registered"]) == (False, False)
    assert again["bucket"]["created"] is False and check(again, manifest) == []
    versions = s3.list_object_versions(Bucket=settings.object_storage_bucket, Prefix=stored["key"]).get("Versions", [])
    assert len(versions) == 1  # the rerun wrote nothing

    # A write made outside the loader cannot destroy the stored bytes: versioning keeps them.
    s3.put_object(Bucket=settings.object_storage_bucket, Key=stored["key"], Body=b"tampered")
    with pytest.raises(ObjectStoreError, match="was not overwritten"):
        store_archives(tmp_path, url, manifest, settings, manifest_path=None)  # the tampering is detected
    original = s3.get_object(Bucket=settings.object_storage_bucket, Key=stored["key"], VersionId=stored["version_id"])
    assert hashlib.sha256(original["Body"].read()).hexdigest() == sha

    with owner_db.transaction(None) as tx:
        from sqlalchemy import text

        row = tx.execute(
            text(
                "SELECT sha256, size_bytes, object_uri, verified_at IS NOT NULL FROM source_archives "
                "WHERE archive_name = :a"
            ),
            {"a": archive},
        ).one()
    assert tuple(row) == (sha, path.stat().st_size, stored["object_uri"], True)
