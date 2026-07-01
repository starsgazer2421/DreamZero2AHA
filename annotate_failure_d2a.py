"""Manual success labeling plus automatic VLM failure attribution."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from make_json_prompt_d2a import FAILURE_TYPES, build_failure_prompt


SUCCESS_CHOICES = {
    "y": True,
    "yes": True,
    "true": True,
    "1": True,
    "n": False,
    "no": False,
    "false": False,
    "0": False,
    "a": "ambiguous",
    "ambiguous": "ambiguous",
    "u": "unknown",
    "unknown": "unknown",
}


def read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


def write_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")


def default_output_path(results_path: Path) -> Path:
    return results_path.with_name("failure_annotations.json")


def existing_annotations_by_episode(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    annotations: dict[int, dict[str, Any]] = {}
    for row in rows:
        episode = row.get("episode")
        if isinstance(episode, int):
            annotations[episode] = row
    return annotations


def prompt_choice(prompt: str, choices: dict[str, Any], *, default: str | None = None) -> Any:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt}{suffix}: ").strip().lower()
        if not value and default is not None:
            value = default
        if value in choices:
            return choices[value]
        print(f"Please choose one of: {', '.join(choices)}")


def resolve_artifact_path(value: str | None, results_path: Path) -> str | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (results_path.parent / path).resolve()
    return str(path)


def open_if_requested(path_text: str | None, *, enabled: bool) -> None:
    if not enabled or not path_text:
        return
    path = Path(path_text)
    if path.exists():
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        print(f"Missing artifact: {path}")


def encode_image_data_url(path_text: str) -> str:
    path = Path(path_text)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{data}"


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Attribution model did not return a JSON object.")
    return data


def normalize_progress(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(4, number))


def normalize_failure_type(value: Any) -> str:
    if isinstance(value, str) and value in FAILURE_TYPES:
        return value
    return "unknown"


def run_openai_attribution(
    *,
    image_path: str,
    instruction: str,
    scene: int,
    model: str,
) -> dict[str, Any]:
    from openai import OpenAI

    prompt = (
        build_failure_prompt(instruction, scene)
        + "\n\nAlso estimate task_progress as an integer from 0 to 4:\n"
        + "0 = no meaningful task progress; "
        + "1 = approaches the relevant object; "
        + "2 = contacts or grasps the relevant object; "
        + "3 = transports or aligns the object toward the target relation; "
        + "4 = completes the requested placement/relation.\n"
        + "Return only JSON with keys: success, task_progress, failure_type, failure_reason, evidence."
    )
    response = OpenAI().responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": encode_image_data_url(image_path)},
                ],
            }
        ],
    )
    data = extract_json_object(response.output_text)
    return {
        "task_progress": normalize_progress(data.get("task_progress")),
        "failure_type": normalize_failure_type(data.get("failure_type")),
        "failure_reason": str(data.get("failure_reason", "")).strip(),
        "evidence_text": str(data.get("evidence", "")).strip(),
        "raw_response": response.output_text,
        "model": model,
    }


def automatic_attribution(
    *,
    success: Any,
    grid_path: str | None,
    prompt: str,
    scene: int,
    model: str,
    enabled: bool,
) -> dict[str, Any]:
    if success is True:
        return {
            "task_progress": 4,
            "failure_type": None,
            "failure_reason": None,
            "evidence_text": "Manually marked as successful.",
            "attribution_model": None,
            "attribution_error": None,
        }
    if not enabled:
        return {
            "task_progress": None,
            "failure_type": "unknown",
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": None,
            "attribution_error": "automatic attribution disabled",
        }
    if not grid_path or not Path(grid_path).exists():
        return {
            "task_progress": None,
            "failure_type": "unknown",
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": model,
            "attribution_error": f"grid image not found: {grid_path}",
        }

    print(f"Running automatic failure attribution with {model}...")
    try:
        result = run_openai_attribution(
            image_path=grid_path,
            instruction=prompt,
            scene=scene,
            model=model,
        )
    except Exception as exc:
        return {
            "task_progress": None,
            "failure_type": "unknown",
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": model,
            "attribution_error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "task_progress": result["task_progress"],
        "failure_type": result["failure_type"],
        "failure_reason": result["failure_reason"],
        "evidence_text": result["evidence_text"],
        "attribution_model": result["model"],
        "attribution_error": None,
        "raw_attribution": result["raw_response"],
    }


def build_annotation(
    episode_row: dict[str, Any],
    *,
    results_path: Path,
    previous: dict[str, Any] | None,
    open_artifacts: bool,
    auto_attribution: bool,
    attribution_model: str,
) -> dict[str, Any] | None:
    episode = episode_row.get("episode")
    scene = episode_row.get("scene")
    prompt = episode_row.get("prompt")
    output_dir = resolve_artifact_path(episode_row.get("output_dir"), results_path)
    video_path = resolve_artifact_path(episode_row.get("video_path"), results_path)
    grid_path = resolve_artifact_path(episode_row.get("aha_grid_path"), results_path)
    request_path = resolve_artifact_path(episode_row.get("aha_request_path"), results_path)
    steps_path = str(Path(output_dir) / "steps.json") if output_dir else None

    print("\n" + "=" * 80)
    print(f"Episode: {episode} | Scene: {scene} | Steps: {episode_row.get('steps')}")
    print(f"Prompt: {prompt}")
    print(f"Video: {video_path}")
    print(f"Grid: {grid_path}")
    print(f"Steps: {steps_path}")
    print(f"Request: {request_path}")

    open_if_requested(grid_path, enabled=open_artifacts)
    open_if_requested(video_path, enabled=open_artifacts)

    action = prompt_choice(
        "Annotate this episode? (y=yes, s=skip, q=quit)",
        {"y": "yes", "yes": "yes", "s": "skip", "skip": "skip", "q": "quit", "quit": "quit"},
        default="y",
    )
    if action == "quit":
        raise KeyboardInterrupt
    if action == "skip":
        return None

    default_success = previous.get("success") if previous else episode_row.get("success")
    if isinstance(default_success, bool):
        success_default = "y" if default_success else "n"
    elif default_success in {"ambiguous", "unknown"}:
        success_default = str(default_success)
    else:
        success_default = "unknown"

    success = prompt_choice(
        "success? (y/n/a=ambiguous/u=unknown)",
        SUCCESS_CHOICES,
        default=success_default,
    )
    attribution = automatic_attribution(
        success=success,
        grid_path=grid_path,
        prompt=str(prompt),
        scene=int(scene),
        model=attribution_model,
        enabled=auto_attribution,
    )
    return {
        "scene": scene,
        "prompt": prompt,
        "episode": episode,
        "success": success,
        "task_progress": attribution["task_progress"],
        "failure_type": attribution["failure_type"],
        "failure_reason": attribution["failure_reason"],
        "evidence_text": attribution["evidence_text"],
        "attribution_model": attribution["attribution_model"],
        "attribution_error": attribution["attribution_error"],
        "evidence": {
            "grid_path": grid_path,
            "video_path": video_path,
            "steps_path": steps_path,
            "aha_request_path": request_path,
        },
        **({"raw_attribution": attribution["raw_attribution"]} if "raw_attribution" in attribution else {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manually label success and automatically attribute failures.")
    parser.add_argument("--results", required=True, help="Path to episode_results.json.")
    parser.add_argument("--output", help="Path to write failure_annotations.json.")
    parser.add_argument(
        "--review-existing",
        action="store_true",
        help="Review episodes that already have annotations instead of skipping them.",
    )
    parser.add_argument(
        "--open-artifacts",
        action="store_true",
        help="Open grid images and videos with the system default applications.",
    )
    parser.add_argument(
        "--no-auto-attribution",
        action="store_true",
        help="Disable VLM failure attribution and write unknown failure fields.",
    )
    parser.add_argument(
        "--attribution-model",
        default=os.environ.get("D2A_ATTRIBUTION_MODEL", "gpt-5.5"),
        help="OpenAI vision model for automatic attribution. Defaults to D2A_ATTRIBUTION_MODEL or gpt-5.5.",
    )
    args = parser.parse_args()

    results_path = Path(args.results).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(results_path)

    episode_rows = read_json_list(results_path)
    annotation_rows = read_json_list(output_path) if output_path.exists() else []
    annotations = existing_annotations_by_episode(annotation_rows)

    try:
        for episode_row in episode_rows:
            episode = episode_row.get("episode")
            if not isinstance(episode, int):
                print(f"Skipping row without integer episode id: {episode_row}")
                continue
            previous = annotations.get(episode)
            if previous is not None and not args.review_existing:
                print(f"Skipping episode {episode}: already annotated.")
                continue

            annotation = build_annotation(
                episode_row,
                results_path=results_path,
                previous=previous,
                open_artifacts=args.open_artifacts,
                auto_attribution=not args.no_auto_attribution,
                attribution_model=args.attribution_model,
            )
            if annotation is None:
                continue
            annotations[episode] = annotation
            annotation_rows = [annotations[key] for key in sorted(annotations)]
            write_json_list(output_path, annotation_rows)
            print(f"Wrote {output_path}")
    except KeyboardInterrupt:
        print("\nAnnotation stopped. Saved annotations are kept on disk.")


if __name__ == "__main__":
    main()
