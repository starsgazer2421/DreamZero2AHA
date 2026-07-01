"""JSON result writer and summary helpers inspired by AHA eval_metrics scripts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from schemas_d2a import EpisodeResult


def _read_episode_results(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def append_episode_json(result: EpisodeResult, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_episode_results(output_path)
    rows.append(result.to_dict())
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return output_path


def summarize_results(results: Iterable[EpisodeResult]) -> dict:
    rows = list(results)
    total = len(rows)
    successes = sum(1 for row in rows if row.success is True)
    unknown = sum(1 for row in rows if row.success == "unknown")
    failure_types = Counter()
    for row in rows:
        if row.success is True:
            continue
        failure_types["unknown"] += 1
    return {
        "total": total,
        "successes": successes,
        "failures": total - successes - unknown,
        "unknown": unknown,
        "success_rate": successes / total if total else 0.0,
        "failure_types": dict(failure_types),
    }

def write_summary(results: Iterable[EpisodeResult], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summarize_results(results), f, indent=2, ensure_ascii=False)
    return output_path
