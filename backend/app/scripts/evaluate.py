"""
Precision AI - offline evaluation on the held-out labelled set (data/eval/eval_set.json).

  python -m app.scripts.evaluate

Measures, with LLMs disabled (the deterministic floor of the system):
  * category accuracy of the rule classifier
  * priority accuracy (exact and within one level)
  * duplicate detection precision / recall at the configured threshold, gated on category
Prints a JSON report; numbers are only as meaningful as the small, author-written set behind them.
"""

import asyncio
import json
from collections import Counter

from app.core.config import PROJECT_DIR, get_settings
from app.core.logging import setup_logging
from app.database import async_session_factory
from app.embeddings import embed, get_embedder
from app.services import classification as cls
from app.services.priority import RANK, assess_by_rules


async def main() -> dict:
    settings = get_settings()
    data = json.loads((PROJECT_DIR / "data" / "eval" / "eval_set.json").read_text(encoding="utf-8"))
    rows = data["classification"]
    confusion: Counter = Counter()
    correct_cat = exact_pri = near_pri = 0
    misses = []
    async with async_session_factory() as db:
        for r in rows:
            c = await cls.classify(r["text"], db, allow_llm=False)
            ok = c.category == r["category"]
            correct_cat += ok
            if not ok:
                confusion[(r["category"], c.category)] += 1
                misses.append({"text": r["text"], "expected": r["category"], "got": c.category})
            p = assess_by_rules(r["text"], c.category, c.entities, None).system_priority
            exact_pri += p == r["priority"]
            near_pri += abs(RANK[p] - RANK[r["priority"]]) <= 1

        tp = fp = fn = tn = 0
        for pair in data["duplicate_pairs"]:
            va, vb = await embed([pair["a"], pair["b"]])
            sim = float(va @ vb)
            ca = (await cls.classify(pair["a"], db, allow_llm=False)).category
            cb = (await cls.classify(pair["b"], db, allow_llm=False)).category
            same_cat_or_identical = ca == cb or sim >= settings.CROSS_CATEGORY_SIMILARITY
            predicted = sim >= settings.INCIDENT_SIMILARITY_THRESHOLD and same_cat_or_identical
            tp += predicted and pair["same"]
            fp += predicted and not pair["same"]
            fn += (not predicted) and pair["same"]
            tn += (not predicted) and not pair["same"]

    n = len(rows)
    report = {
        "embedder": get_embedder().name,
        "classification": {"n": n, "accuracy": round(correct_cat / n, 3), "misses": misses},
        "priority": {"n": n, "exact_accuracy": round(exact_pri / n, 3), "within_one_level": round(near_pri / n, 3)},
        "duplicate_detection": {
            "pairs": tp + fp + fn + tn, "threshold": settings.INCIDENT_SIMILARITY_THRESHOLD,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        },
    }
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    import os

    os.environ.setdefault("LOG_LEVEL", "WARNING")
    setup_logging()
    asyncio.run(main())
