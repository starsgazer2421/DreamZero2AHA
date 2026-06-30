"""AHA conversation JSON builder adapted from AHA make_json.py."""

from __future__ import annotations

import json
from pathlib import Path


FAILURE_TYPES = [
    "grasp_failure",
    "object_slip",
    "wrong_object",
    "wrong_location",
    "placement_failure",
    "collision_or_blockage",
    "no_progress",
    "timeout",
    "other",
]


SCENE_SUBTASKS: dict[int, list[str]] = {
    1: ["grasp the cube", "move the cube above the bowl", "release the cube into the bowl"],
    2: ["grasp the can", "move the can above the mug", "release the can into the mug"],
    3: ["grasp the banana", "move the banana above the bin", "release the banana into the bin"],
}


def build_failure_prompt(instruction: str, scene: int, *, episode_level: bool = True) -> str:
    subtasks = SCENE_SUBTASKS.get(scene, [])
    subtask_text = "; ".join(subtasks) if subtasks else "unknown"
    scope = "the whole episode" if episode_level else "the visible sub-task"
    return (
        "<image>\n"
        "The image contains multiple camera views of a robot manipulation rollout over time. "
        "Rows are camera views and columns are sampled timesteps from left to right. "
        "The task instruction is: "
        f"\"{instruction}\". "
        f"Expected sub-tasks are: {subtask_text}. "
        f"First determine whether {scope} succeeded by choosing from [\"yes\", \"no\"]. "
        "If it failed, explain the most likely failure reason using visual evidence. "
        "Classify the failure into exactly one of: "
        f"{FAILURE_TYPES}. "
        "Return concise JSON with keys: success, failure_type, failure_reason, evidence."
    )


def build_aha_request(
    *,
    request_id: str,
    image_path: str | Path,
    instruction: str,
    scene: int,
) -> dict:
    return {
        "id": request_id,
        "image": str(image_path),
        "conversations": [
            {
                "from": "human",
                "value": build_failure_prompt(instruction, scene),
            }
        ],
    }


def write_aha_request_json(request: dict, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump([request], f, indent=2)
    return output_path

