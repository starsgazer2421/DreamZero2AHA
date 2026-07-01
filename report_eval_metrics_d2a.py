"""Result writer and summary helpers inspired by AHA eval_metrics scripts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from schemas_d2a import EpisodeResult


def _write_readable_results(jsonl_path: Path) -> Path:
    readable_path = jsonl_path.with_name(f"{jsonl_path.stem}_readable.json")
    rows = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    with readable_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return readable_path


def append_episode_jsonl(result: EpisodeResult, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
    _write_readable_results(output_path)
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
        failure_type = row.attribution.failure_type if row.attribution is not None else "unknown"
        failure_types[failure_type] += 1
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
