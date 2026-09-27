#!/usr/bin/env python3
"""将用户数据导出为可核验的快照；模型缓存和服务进程文件不随快照迁移。"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

SKIP_DIRS = {"models", "logs", "run"}
SKIP_DB_NAMES = {"pte.sqlite3", "pte.sqlite3-wal", "pte.sqlite3-shm"}


def sha256(path: Path) -> str:
    """分块读取，避免将大录音一次装进内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(source: Path, destination: Path) -> dict:
    """先做 SQLite 在线备份，再复制静态资产，并逐件复核哈希。"""
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_dir() or destination.exists() or destination.is_relative_to(source):
        raise ValueError("source must exist; destination must be new and outside source")
    db = source / "db" / "pte.sqlite3"
    if not db.is_file():
        raise FileNotFoundError(db)
    destination.mkdir(parents=True)
    target_db = destination / "db" / "pte.sqlite3"
    target_db.parent.mkdir(parents=True)
    # SQLite backup API 取得同一时点的数据库副本，不直接复制 WAL 文件。
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as old:
        with sqlite3.connect(target_db) as new:
            old.backup(new)
            if new.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("exported database failed integrity_check")
    files = []
    for original in sorted(source.rglob("*")):
        relative = original.relative_to(source)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if original.is_symlink():
            raise ValueError(f"symlink in private data: {relative}")
        if not original.is_file() or (relative.parts[0] == "db" and original.name in SKIP_DB_NAMES):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        before, after = sha256(original), sha256(target)
        if before != after:
            raise OSError(f"hash mismatch: {relative}")
        files.append({"path": str(relative), "sha256": after, "bytes": target.stat().st_size})
    files.insert(0, {"path": "db/pte.sqlite3", "sha256": sha256(target_db), "bytes": target_db.stat().st_size})
    manifest = {"format": 1, "files": files, "excluded_directories": sorted(SKIP_DIRS)}
    (destination / "snapshot-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def verify(destination: Path) -> int:
    """迁移后在 M5 重算全部文件哈希并检查 SQLite 完整性。"""
    manifest = json.loads((destination / "snapshot-manifest.json").read_text())
    for item in manifest["files"]:
        path = destination / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise OSError(f"snapshot mismatch: {item['path']}")
    with sqlite3.connect(f"file:{destination / 'db/pte.sqlite3'}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("snapshot database failed integrity_check")
    return len(manifest["files"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("export", "verify"))
    parser.add_argument("path", type=Path, help="new snapshot directory or existing snapshot to verify")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    args = parser.parse_args()
    count = len(export(args.source, args.path)["files"]) if args.mode == "export" else verify(args.path)
    print(f"{args.mode}: verified {count} files at {args.path}")
