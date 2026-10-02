"""Materialize the committed Qwen and Chroma shards into a local runtime cache."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

try:
    import fcntl
except ImportError:  # Windows development/runtime
    fcntl = None


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "runtime_assets" / "reference_rag_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assemble(parts_dir: Path, target: Path, expected: dict) -> None:
    parts = sorted(parts_dir.glob("part-*"))
    if len(parts) != expected["parts"]:
        raise RuntimeError(f"Incomplete runtime asset: {parts_dir.name}")
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("wb") as output:
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, output, 8 * 1024 * 1024)
        output.flush()
        os.fsync(output.fileno())
    if temporary.stat().st_size != expected["size"] or _sha256(temporary) != expected["sha256"]:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Runtime asset checksum failed: {target.name}")
    os.replace(temporary, target)


def _needs_assembly(path: Path, expected: dict) -> bool:
    return not path.is_file() or path.stat().st_size != expected["size"]


@contextmanager
def _exclusive_lock(handle):
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return

    import msvcrt

    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    try:
        yield
    finally:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _link_tree(source: Path, target: Path, excluded: set[str]) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if relative.as_posix() in excluded or any(parent.as_posix() in excluded for parent in relative.parents):
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(path, destination)
            except OSError:
                shutil.copy2(path, destination)


def ensure_runtime_assets() -> tuple[Path, Path, dict]:
    """Return materialized ``(model_dir, chroma_dir, manifest)``.

    No download is attempted. A process lock and checksums make concurrent
    first-use assembly deterministic.
    """
    manifest_path = BUNDLE / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Committed reference RAG manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest.get("bundle_sha256", "")[:16]
    if not version:
        raise RuntimeError("Invalid reference RAG manifest")
    cache = Path(tempfile.gettempdir()) / f"intern_s1_reference_rag_{version}"
    cache.mkdir(parents=True, exist_ok=True)
    lock_path = cache / ".assemble.lock"
    with lock_path.open("a+b") as lock:
        with _exclusive_lock(lock):
            model_dir = cache / "model"
            chroma_dir = cache / "chroma"
            model_dir.mkdir(exist_ok=True)
            chroma_dir.mkdir(exist_ok=True)
            _link_tree(BUNDLE / "model", model_dir, {"model.safetensors.parts"})
            _link_tree(BUNDLE / "chroma", chroma_dir, {"chroma.sqlite3.parts"})
            targets = manifest["assembled_files"]
            model_target = model_dir / "model.safetensors"
            db_target = chroma_dir / "chroma.sqlite3"
            if _needs_assembly(model_target, targets["model/model.safetensors"]):
                _assemble(BUNDLE / "model" / "model.safetensors.parts", model_target,
                          targets["model/model.safetensors"])
            if _needs_assembly(db_target, targets["chroma/chroma.sqlite3"]):
                _assemble(BUNDLE / "chroma" / "chroma.sqlite3.parts", db_target,
                          targets["chroma/chroma.sqlite3"])
            marker = cache / ".ready"
            marker.write_text(manifest["bundle_sha256"] + "\n", encoding="ascii")
    return model_dir, chroma_dir, manifest


__all__ = ["ensure_runtime_assets"]
