"""Source archive verification. Nothing is extracted to disk and nothing is read from an
archive until its checksum matches the manifest and every entry passes the safety checks."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import stat
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "specs" / "ingestion_manifest.json"
RAW_DIR = ROOT / "data" / "raw"

ALLOWED_SUFFIXES = {".csv", ".txt"}
MAX_ENTRIES = 500
MAX_ENTRY_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200  # largest legitimate ratio in the six archives is about 91:1


class ArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class Manifest:
    archives: dict[str, str]
    files: list[dict]
    text_files: list[dict]


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(raw["source_archives"], raw["files"], raw["text_files"])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksum(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ArchiveError(f"{path.name}: SHA-256 {actual} does not match manifest {expected}")


def validate_zip(path: Path) -> list[zipfile.ZipInfo]:
    """Reject archives with unsafe paths, links, unexpected types or implausible sizes."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"{path.name}: not a valid ZIP file") from exc
    if len(infos) > MAX_ENTRIES:
        raise ArchiveError(f"{path.name}: {len(infos)} entries exceeds limit {MAX_ENTRIES}")
    total = 0
    seen: set[str] = set()
    for info in infos:
        name = info.filename
        parts = PurePosixPath(name.replace("\\", "/")).parts
        if name.startswith(("/", "\\")) or ".." in parts or (parts and ":" in parts[0]) or "\x00" in name:
            raise ArchiveError(f"{path.name}: unsafe entry path {name!r}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ArchiveError(f"{path.name}: symbolic link entry {name!r}")
        if info.is_dir():
            continue
        if name in seen:
            raise ArchiveError(f"{path.name}: duplicate entry {name!r}")
        seen.add(name)
        if PurePosixPath(name).suffix.lower() not in ALLOWED_SUFFIXES:
            raise ArchiveError(f"{path.name}: entry type not allowed {name!r}")
        if info.flag_bits & 0x1:
            raise ArchiveError(f"{path.name}: encrypted entry {name!r}")
        if info.file_size > MAX_ENTRY_BYTES:
            raise ArchiveError(f"{path.name}: entry {name!r} is {info.file_size} bytes, over the limit")
        if info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
            raise ArchiveError(f"{path.name}: entry {name!r} has an implausible compression ratio")
        total += info.file_size
    if total > MAX_TOTAL_BYTES:
        raise ArchiveError(f"{path.name}: {total} uncompressed bytes exceeds the limit")
    return infos


def verify_all(raw_dir: Path = RAW_DIR, manifest: Manifest | None = None) -> dict[str, list[zipfile.ZipInfo]]:
    manifest = manifest or load_manifest()
    result = {}
    for name, expected in manifest.archives.items():
        path = raw_dir / name
        if not path.is_file():
            raise ArchiveError(f"{name}: missing from {raw_dir}")
        verify_checksum(path, expected)
        result[name] = validate_zip(path)
    return result


def read_csv_positional(archive: zipfile.ZipFile, member: str) -> tuple[list[str], Iterator[list[str]]]:
    """Header and row iterator as plain lists. Columns are addressed by position only, so
    repeated header names stay separate columns. Decompression is bounded by the declared size."""
    info = archive.getinfo(member)
    raw = archive.open(info)
    text = io.TextIOWrapper(io.BufferedReader(_Bounded(raw, info.file_size)), encoding="utf-8-sig", newline="")
    reader = csv.reader(text)
    header = next(reader)
    return header, reader


class _Bounded(io.RawIOBase):
    """Stops reading once the entry's declared uncompressed size has been produced."""

    def __init__(self, raw: IO[bytes], limit: int) -> None:
        self._raw, self._left = raw, limit

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:  # type: ignore[no-untyped-def]
        if self._left < 0:
            raise ArchiveError("entry produced more data than its declared size")
        chunk = self._raw.read(len(buffer))
        self._left -= len(chunk)
        if self._left < 0:
            raise ArchiveError("entry produced more data than its declared size")
        buffer[: len(chunk)] = chunk
        return len(chunk)
