"""Immutable, credential-free image request recipes; never makes a network call.

Request parameters are known. Provider-internal model/seed/defaults are not inferred.
"""
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def safe(value):
    text = json.dumps(value, ensure_ascii=False)
    if re.search(r"\bsk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+|(?:api[_-]?key|access[_-]?token|cookie|password)\s*[\"']?\s*[:=]\s*[\"']?\S+", text, re.I):
        raise ValueError("Potential credential in image recipe; remove it before generating")
    if isinstance(value, dict):
        if any(re.search(r"api.?key|token|password|cookie|authorization|secret|proxy|headers", k, re.I)
               for k in value):
            raise ValueError("Credential/transport fields must not be stored in an image recipe")
        for v in value.values():
            safe(v)
    elif isinstance(value, list):
        for v in value:
            safe(v)


def begin(out, mode, payload, images=(), mask=None, postprocessing=None):
    safe(payload)
    safe(postprocessing or {})
    out = Path(out).resolve()
    folder = out.parent / "generation-records" / ("gen-" + uuid.uuid4().hex[:20])
    folder.mkdir(parents=True)
    record = {"schema_version": 1, "id": folder.name, "status": "prepared",
              "created_at": datetime.now(timezone.utc).isoformat(), "mode": mode,
              "requested_model": payload.get("model"), "reported_model": None,
              "parameters": {k: v for k, v in payload.items() if k != "prompt"},
              "prompt": payload.get("prompt", ""), "inputs": [], "outputs": [],
              "provider_defaults": "unknown", "reproducibility": "request archived; pixel-identical replay not guaranteed",
              "postprocessing": postprocessing or {},
              "recipe_path": str(folder / "recipe.json")}
    (folder / "prompt.txt").write_text(record["prompt"], encoding="utf-8")
    for i, (role, path) in enumerate([("reference", x) for x in images] + ([("mask", mask)] if mask else [])):
        src = Path(path).resolve()
        sha = digest(src)
        dest = folder / "inputs" / (f"{i+1:02d}-" + sha[:16] + src.suffix.lower())
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(src, dest)
        if digest(dest) != sha:
            raise ValueError("Image input changed while archiving")
        lineage = sidecar(src)
        record["inputs"].append({"role": role, "source_path": str(src), "path": str(dest),
                                 "sha256": sha, "parent_recipe_id": lineage.get("id") if lineage else None})
    write(record["recipe_path"], record)
    return record


def finish(record, outputs, response):
    folder = Path(record["recipe_path"]).parent
    # Only an explicitly returned model is reported, never the requested alias as proof.
    model = response.get("model") if isinstance(response, dict) else None
    if isinstance(model, str) and len(model) < 200:
        safe(model)
        record["reported_model"] = model
    items = response.get("data", []) if isinstance(response, dict) else []
    for i, output in enumerate(outputs):
        src = Path(output).resolve()
        dest = folder / "outputs" / (str(i+1) + src.suffix.lower())
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(src, dest)
        row = {"path": str(dest), "source_path": str(src), "sha256": digest(dest)}
        if i < len(items) and isinstance(items[i], dict) and isinstance(items[i].get("revised_prompt"), str):
            revised = items[i]["revised_prompt"]
            safe(revised)
            row["revised_prompt"] = revised
        record["outputs"].append(row)
    record["status"] = "completed"
    write(record["recipe_path"], record)
    for output in outputs:
        # Convenient lookup, but immutable record in generation-records is canonical.
        write(Path(str(Path(output).resolve()) + ".recipe.json"), record)
    return record


def failed(record):
    record["status"] = "failed"
    write(record["recipe_path"], record)  # No exception text or raw upstream data.


def sidecar(image):
    path = Path(str(Path(image).resolve()) + ".recipe.json")
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"gen-[a-f0-9]{20}", record.get("id", "")):
        return None
    canonical = Path(record.get("recipe_path", ""))
    if canonical.name != "recipe.json" or canonical.parent.name != record["id"] or not canonical.is_file():
        return None
    actual = json.loads(canonical.read_text(encoding="utf-8"))
    if actual != record:
        raise ValueError("Generation sidecar disagrees with its canonical record")
    if not any(x.get("sha256") == digest(image) for x in record.get("outputs", [])):
        return None
    return record


def bundle_to(image, destination):
    """Attach complete inputs/outputs/prompt to the artifact, not just a mutable pointer."""
    record = sidecar(image)
    if not record:
        return None
    source = Path(record["recipe_path"]).parent
    safe(record)
    for row in record["inputs"] + record["outputs"]:
        path = Path(row["path"]).resolve()
        if not path.is_relative_to(source.resolve()) or digest(path) != row["sha256"]:
            raise ValueError("Recipe image escaped archive or changed")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Generation archives must not contain symlinks")
    dest = Path(destination) / record["id"]
    if not dest.exists():
        shutil.copytree(source, dest)
    # Derive from the canonical source each time. A previously imported archive
    # already contains destination paths; do not relativize those to a new source.
    copied = json.loads(json.dumps(record))
    for row in copied["inputs"] + copied["outputs"]:
        relative = Path(row["path"]).relative_to(source)
        row["path"] = str(dest / relative)
        if digest(row["path"]) != row["sha256"]:
            raise ValueError("Generation recipe image changed")
    copied["recipe_path"] = str(dest / "recipe.json")
    existing = json.loads((dest / "recipe.json").read_text(encoding="utf-8"))
    if existing != record and existing != copied:
        raise ValueError("Existing generation archive differs; never overwrite another recipe")
    write(copied["recipe_path"], copied)
    return {"id": copied["id"], "path": copied["recipe_path"], "sha256": digest(copied["recipe_path"])}
