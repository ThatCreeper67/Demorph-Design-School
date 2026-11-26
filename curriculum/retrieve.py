"""Minimal keyword retrieval for the versioned Design School knowledge index."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def retrieve(root: str | Path, query: str, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    root = Path(root).resolve()
    index_path = root / "curriculum" / "knowledge_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema_version") != "1.0.0" or not isinstance(index.get("entries"), list):
        raise ValueError(f"Unsupported or invalid knowledge index: {index_path}")
    terms = {word.casefold() for word in query.split() if len(word) > 1}
    ranked = []
    for entry in index["entries"]:
        if module and entry["module_id"] != module:
            continue
        haystack = " ".join([entry["title"], entry.get("summary", ""), *entry.get("keywords", [])]).casefold()
        score = sum(term in haystack for term in terms)
        if score:
            ranked.append((score, entry))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["knowledge_id"]))
    result = []
    for score, entry in ranked[:max(0, limit)]:
        path = (root / entry["path"]).resolve()
        if root not in path.parents:
            raise ValueError("Knowledge index path escapes Design School root")
        result.append({**entry, "score": score, "content": path.read_text(encoding="utf-8")})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--module")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(retrieve(args.root, args.query, args.module, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
