import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ppt_read_cache import SQLiteReadIndex, file_sha, hash_snapshot


def test_hash_cache_is_request_scoped_and_detects_changes(tmp_path, monkeypatch):
    p = tmp_path / "image.bin"
    p.write_bytes(b"one")
    original = Path.read_bytes
    reads = []
    def counted(self):
        reads.append(self)
        return original(self)
    monkeypatch.setattr(Path, "read_bytes", counted)
    with hash_snapshot():
        assert file_sha(p) == file_sha(p)
        assert len(reads) == 1
        p.write_bytes(b"changed")
        assert file_sha(p) == hashlib.sha256(b"changed").hexdigest()
    with hash_snapshot():
        file_sha(p)
    assert len(reads) == 3
    file_sha(p)
    file_sha(p)
    assert len(reads) == 5  # outside an inspection there is no persistent hash cache


def test_sqlite_index_invalidates_for_external_wal_commits(tmp_path):
    p = tmp_path / "index.sqlite3"
    writer = sqlite3.connect(p)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE items(value)")
    writer.execute("INSERT INTO items VALUES (1)")
    writer.commit()
    cache, calls = SQLiteReadIndex(), []
    def load(db):
        calls.append(True)
        return db.execute("SELECT value FROM items").fetchall()
    assert cache.get(p, "search", load) == [(1,)]
    assert cache.get(p, "search", load) == [(1,)]
    assert len(calls) == 1
    writer.execute("UPDATE items SET value=2")
    writer.commit()
    assert cache.get(p, "search", load) == [(2,)]
    assert len(calls) == 2
    writer.close()
