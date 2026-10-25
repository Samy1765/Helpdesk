"""Seed and knowledge data must stay independent of the held-out evaluation set, and every
runbook must carry the metadata the loader and the UI rely on."""

import json
import re

from app.core.config import PROJECT_DIR
from app.database.seed import CATEGORY_DEPARTMENT, parse_front_matter

DATA = PROJECT_DIR / "data"
# Eight-word windows catch a reused or lightly edited sentence without flagging short generic
# phrases such as "connected but no internet" that any IT text contains.
SHINGLE = 8


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _shingles(text: str) -> set[tuple[str, ...]]:
    w = _words(text)
    return {tuple(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def _eval_texts() -> list[str]:
    data = json.loads((DATA / "eval" / "eval_set.json").read_text(encoding="utf-8"))
    texts = [r["text"] for r in data["classification"]]
    texts += [p[k] for p in data["duplicate_pairs"] for k in ("a", "b")]
    return texts


def _corpus() -> dict[str, str]:
    files = sorted((DATA / "knowledge").glob("*.md")) + sorted((DATA / "seed").glob("*.json"))
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def test_no_evaluation_text_in_seed_or_knowledge():
    corpus = {name: _shingles(text) for name, text in _corpus().items()}
    leaks = []
    for text in _eval_texts():
        sh = _shingles(text)
        for name, cs in corpus.items():
            if sh & cs:
                leaks.append((name, text))
    assert not leaks, f"evaluation sentences reused in seed/knowledge data: {leaks[:5]}"


def test_runbooks_have_valid_metadata_and_steps():
    paths = sorted((DATA / "knowledge").glob("*.md"))
    assert len(paths) >= 40
    seen_categories = set()
    for path in paths:
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        assert meta.get("title"), path.name
        assert meta.get("category") in CATEGORY_DEPARTMENT, path.name
        seen_categories.add(meta["category"])
        assert re.search(r"^\d+\. ", body, re.M), f"{path.name} has no numbered steps"
    assert seen_categories == set(CATEGORY_DEPARTMENT)
