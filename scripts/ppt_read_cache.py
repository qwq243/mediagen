"""Read-side acceleration only; never cache approvals or production decisions."""
import hashlib
import sqlite3
import threading
from collections import OrderedDict
from contextlib import contextmanager, closing
from contextvars import ContextVar
from pathlib import Path

_hashes = ContextVar("ppt_request_hashes", default=None)


@contextmanager
def hash_snapshot():
    """Reuse bytes within one inspection, not between HTTP requests or executions."""
    token = _hashes.set({})
    try:
        yield
    finally:
        _hashes.reset(token)


def file_sha(path):
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"missing file: {p}")
    cache = _hashes.get()
    stat = p.stat()
    key = (str(p.resolve()), stat.st_dev, stat.st_ino, stat.st_size,
           stat.st_mtime_ns, stat.st_ctime_ns)
    if cache is not None and key in cache:
        return cache[key]
    value = hashlib.sha256(p.read_bytes()).hexdigest()
    after = p.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("file changed during inspection; refresh and retry")
    if cache is not None:
        cache[key] = value
    return value


class SQLiteReadIndex:
    """Bounded discovery cache invalidated by database and WAL file changes.

    Factory results are private immutable snapshots. Consumers must copy returned
    rows before decorating them. No connection remains open between calls (important
    for Windows library moves). This is never used for production authorization.
    """
    def __init__(self, capacity=3):
        self.capacity = capacity
        self.entries = OrderedDict()
        self.lock = threading.RLock()

    def get(self, path, variant, factory):
        path = Path(path).resolve()
        def signature():
            result = []
            for p in (path, Path(str(path) + "-wal")):
                try:
                    s = p.stat()
                    # The SQLite change counter and WAL salts supplement timestamps.
                    with p.open("rb") as stream:
                        header = stream.read(100 if p == path else 32)
                    result.append((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                                   s.st_ctime_ns, header))
                except FileNotFoundError:
                    result.append(None)
            return tuple(result)
        identity = signature()
        name = str(path)
        with self.lock:
            entry = self.entries.get(name)
            if entry and entry["identity"] != identity:
                del self.entries[name]
                entry = None
            if not entry:
                entry = {"identity": identity, "values": {}}
                self.entries[name] = entry
            self.entries.move_to_end(name)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
            if variant not in entry["values"]:
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                    db.execute("BEGIN")
                    result = factory(db)
                    db.rollback()
                if identity == signature():
                    entry["values"][variant] = result
                return result
            return entry["values"][variant]
