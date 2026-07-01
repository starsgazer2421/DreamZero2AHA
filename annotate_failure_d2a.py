"""Automatic failure attribution after manual success labels."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

from make_json_prompt_d2a import FAILURE_TYPES, build_failure_prompt


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


def resolve_artifact_path(value: str | None, results_path: Path) -> str | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (results_path.parent / path).resolve()
    return str(path)


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


def normalize_failure_type(value: Any) -> str:
    if isinstance(value, str) and value in FAILURE_TYPES:
        return value
    return "unknown"


def load_aha_request_prompt(request_path: str | None, *, instruction: str, scene: int) -> str:
    if request_path and Path(request_path).exists():
        data = read_json_list(Path(request_path))
        if data:
            conversations = data[0].get("conversations", [])
            if conversations and isinstance(conversations[0], dict):
                value = conversations[0].get("value")
                if isinstance(value, str) and value.strip():
                    return value
    return build_failure_prompt(instruction, scene)


def run_openai_attribution(
    *,
    image_path: str,
    aha_prompt: str,
    model: str,
) -> dict[str, Any]:
    from openai import OpenAI

    prompt = (
        aha_prompt
        + "\n\nReturn only JSON with keys: success, failure_type, failure_reason, evidence."
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
        "failure_type": normalize_failure_type(data.get("failure_type")),
        "failure_reason": str(data.get("failure_reason", "")).strip(),
        "evidence_text": str(data.get("evidence", "")).strip(),
        "raw_response": response.output_text,
        "model": model,
    }


def normalize_manual_success(value: Any, *, episode: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    raise ValueError(
        f"Episode {episode} has success={value!r}. "
        "Please manually edit episode_results.json and set success to true or false before running attribution."
    )


def automatic_failure_attribution(
    *,
    grid_path: str | None,
    request_path: str | None,
    prompt: str,
    scene: int,
    model: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "failure_type": "unknown",
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": None,
            "attribution_error": "automatic attribution disabled",
        }
    if not grid_path or not Path(grid_path).exists():
        return {
            "failure_type": "unknown",
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": model,
            "attribution_error": f"grid image not found: {grid_path}",
        }

    print(f"Running automatic failure attribution with {model}...")
    try:
        aha_prompt = load_aha_request_prompt(request_path, instruction=prompt, scene=scene)
        result = run_openai_attribution(
            image_path=grid_path,
            aha_prompt=aha_prompt,
            model=model,
        )
    except Exception as exc:
        return {
            "failure_type": "unknown",
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": model,
            "attribution_error": f"{type(exc).__name__}: {exc}",
        }

    return {
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
    auto_attribution: bool,
    attribution_model: str,
) -> dict[str, Any]:
    episode = episode_row.get("episode")
    scene = episode_row.get("scene")
    prompt = episode_row.get("prompt")
    output_dir = resolve_artifact_path(episode_row.get("output_dir"), results_path)
    video_path = resolve_artifact_path(episode_row.get("video_path"), results_path)
    grid_path = resolve_artifact_path(episode_row.get("aha_grid_path"), results_path)
    request_path = resolve_artifact_path(episode_row.get("aha_request_path"), results_path)
    steps_path = str(Path(output_dir) / "steps.json") if output_dir else None
    success = normalize_manual_success(episode_row.get("success"), episode=episode)

    print("\n" + "=" * 80)
    print(f"Episode: {episode} | Scene: {scene} | Steps: {episode_row.get('steps')}")
    print(f"Prompt: {prompt}")
    print(f"Grid: {grid_path}")
    print(f"Manual success: {success}")

    if success:
        attribution = {
            "failure_type": None,
            "failure_reason": None,
            "evidence_text": None,
            "attribution_model": None,
            "attribution_error": None,
        }
    else:
        attribution = automatic_failure_attribution(
            grid_path=grid_path,
            request_path=request_path,
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
    parser = argparse.ArgumentParser(
        description="Run automatic failure attribution after success has been manually edited in episode_results.json."
    )
    parser.add_argument("--results", required=True, help="Path to episode_results.json.")
    parser.add_argument("--output", help="Path to write failure_annotations.json.")
    parser.add_argument(
        "--no-auto-attribution",
        action="store_true",
        help="Disable VLM failure attribution and write unknown failure fields.",
    )
    parser.add_argument(
        "--attribution-model",
        default="gpt-5.5",
        help="OpenAI vision model for automatic attribution. Defaults to gpt-5.5.",
    )
    args = parser.parse_args()

    results_path = Path(args.results).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(results_path)

    episode_rows = read_json_list(results_path)
    annotation_rows = []

    try:
        for episode_row in episode_rows:
            episode = episode_row.get("episode")
            if not isinstance(episode, int):
                print(f"Skipping row without integer episode id: {episode_row}")
                continue
            annotation_rows.append(
                build_annotation(
                    episode_row,
                    results_path=results_path,
                    auto_attribution=not args.no_auto_attribution,
                    attribution_model=args.attribution_model,
                )
            )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    write_json_list(output_path, annotation_rows)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
