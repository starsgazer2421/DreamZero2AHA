"""Interactive offline failure annotation for DreamZero2AHA episodes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from make_json_prompt_d2a import FAILURE_TYPES


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
    with path.open("r", encoding="utf-8") as f:
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


def prompt_int(prompt: str, *, min_value: int, max_value: int, default: int | None = None) -> int:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if not value and default is not None:
            return default
        try:
            number = int(value)
        except ValueError:
            print("Please enter an integer.")
            continue
        if min_value <= number <= max_value:
            return number
        print(f"Please enter a value from {min_value} to {max_value}.")


def prompt_failure_type(success: Any, *, default: str | None = None) -> str | None:
    if success is True:
        return None

    choices = {str(index + 1): value for index, value in enumerate(FAILURE_TYPES)}
    choices.update({value: value for value in FAILURE_TYPES})
    if default and default in FAILURE_TYPES:
        choices[""] = default

    print("Failure types:")
    for index, failure_type in enumerate(FAILURE_TYPES, start=1):
        print(f"  {index}. {failure_type}")
    return prompt_choice("failure_type", choices, default=default)


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


def build_annotation(
    episode_row: dict[str, Any],
    *,
    results_path: Path,
    previous: dict[str, Any] | None,
    open_artifacts: bool,
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
    progress_default = previous.get("task_progress") if previous else None
    if not isinstance(progress_default, int):
        progress_default = None
    task_progress = prompt_int("task_progress (0-4)", min_value=0, max_value=4, default=progress_default)

    previous_failure_type = previous.get("failure_type") if previous else episode_row.get("failure_type")
    failure_type = prompt_failure_type(success, default=previous_failure_type)
    return {
        "scene": scene,
        "prompt": prompt,
        "episode": episode,
        "success": success,
        "task_progress": task_progress,
        "failure_type": failure_type,
        "evidence": {
            "grid_path": grid_path,
            "video_path": video_path,
            "steps_path": steps_path,
            "aha_request_path": request_path,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactively annotate DreamZero2AHA failure cases.")
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
