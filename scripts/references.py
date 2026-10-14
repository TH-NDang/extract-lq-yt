#!/usr/bin/env python3
"""Normalize source aov-project JSON metadata into a compact reference index.

Images in aov-project are tracked by Git LFS. This step intentionally fetches
JSON metadata only and never treats LFS pointer text as an image.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://raw.githubusercontent.com/TH-NDang/aov-project/main/resources/Lien-Quan-v3"
SOURCES = {
    "heroes": "heroes.json",
    "items": "trang-bi.json",
    "enchantments": "phu-hieu.json",
}


def fetch_json(name: str) -> dict:
    request = Request(f"{BASE}/data/{name}", headers={"User-Agent": "extract-lq-yt/1.0"})
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def image_path(raw: str | dict | None) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("file")
    if not isinstance(raw, str) or not raw.startswith("assets/"):
        return None
    return "resources/Lien-Quan-v3/" + raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("out/references"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    errors = {}
    records = []
    counts = {}

    for kind, json_file in SOURCES.items():
        try:
            data = fetch_json(json_file)
            entries = data.get("heroes" if kind == "heroes" else "items", [])
            counts[kind] = len(entries)
            for item in entries:
                images = []
                if kind == "heroes":
                    for field in ("listHead", "head"):
                        path = image_path(item.get(field))
                        if path and path not in images:
                            images.append(path)
                else:
                    path = image_path(item.get("image"))
                    if path:
                        images.append(path)
                records.append({
                    "type": kind,
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "image_paths": images,
                    "source_data": f"resources/Lien-Quan-v3/data/{json_file}",
                })
        except Exception as exc:
            counts[kind] = 0
            errors[kind] = str(exc)

    index = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_repo": "TH-NDang/aov-project",
        "source_branch": "main",
        "image_storage": "git-lfs",
        "images_included": False,
        "note": "Reference image paths only; obtain image bytes using Git LFS checkout or Drive.",
        "records": records,
    }
    report = {
        "counts": counts,
        "total": len(records),
        "errors": errors,
        "missing_categories": [
            "abilities: no dedicated supplementary spell reference in provided assets/data",
            "arcana: data/ngoc.json status=not-collected",
        ],
    }
    (args.out / "reference-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "reference-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not records:
        raise RuntimeError("Could not download any reference metadata")


if __name__ == "__main__":
    main()
