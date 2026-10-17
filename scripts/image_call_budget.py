"""Opt-in shared, fail-closed budget for actual image API attempts."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def reserve(path, operation):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Shared image budget must be explicitly authorized first")
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("Shared image budget is locked; no image request was sent") from None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        maximum = data.get("max_calls")
        attempts = data.get("attempts")
        if type(maximum) is not int or maximum < 1 or not data.get("evidence") or not isinstance(attempts, list):
            raise ValueError("Shared image budget authorization is invalid")
        if len(attempts) >= maximum:
            raise ValueError("Shared image budget exhausted; no automatic extra calls")
        record = {"id": uuid.uuid4().hex, "operation": str(operation)[:40],
                  "at": datetime.now(timezone.utc).isoformat(),
                  "status": "reserved_attempt_including_possible_failure"}
        attempts.append(record)
        temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return record
    finally:
        os.close(fd)
        lock.unlink()


def reserve_from_environment(method, url):
    path = os.environ.get("MEDIAGEN_IMAGE_BUDGET_FILE")
    if not path or method.upper() != "POST":
        return False
    from urllib.parse import urlsplit
    endpoint = urlsplit(url).path
    if not any(endpoint.endswith("/images/" + kind) for kind in ("generations", "edits", "variations")):
        return False
    reserve(path, endpoint.rsplit("/", 1)[-1])
    return True
