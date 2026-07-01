"""DreamZero simulation evaluation with attribution-ready evidence export.

This is a non-invasive derivative of eval_utils/run_sim_eval.py. It imports the
DreamZero policy client from the source file and keeps new evaluation logic in
DreamZero2AHA.
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import gymnasium as gym
import mediapy
import torch
import tyro
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent
BEIJING_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_d2a import load_d2a_config

D2A_CONFIG = load_d2a_config()
DREAMZERO_ROOT = D2A_CONFIG.dreamzero_root
EVAL_UTILS_ROOT = DREAMZERO_ROOT / "eval_utils"
SIM_EVALS_SRC = DREAMZERO_ROOT / "eval_utils" / "sim-evals" / "src"

for path in (DREAMZERO_ROOT, EVAL_UTILS_ROOT, SIM_EVALS_SRC):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from eval_utils import run_sim_eval as dreamzero_run_sim_eval
from make_json_prompt_d2a import build_aha_request, write_aha_request_json
from process_data_grid_d2a import build_aha_grid, sample_indices
from report_eval_metrics_d2a import append_episode_json
from schemas_d2a import EpisodeResult
from trajectory_recorder_run_sim_eval_d2a import DreamZero2AHATrajectoryRecorder, extract_views_from_obs

DreamZeroJointPosClient = dreamzero_run_sim_eval.DreamZeroJointPosClient


def dreamzero_main_default(name: str, fallback):
    parameter = inspect.signature(dreamzero_run_sim_eval.main).parameters.get(name)
    if parameter is None or parameter.default is inspect.Parameter.empty:
        return fallback
    return parameter.default


def instruction_for_scene(scene: int) -> str:
    match scene:
        case 1:
            return "put the cube in the bowl"
        case 2:
            return "pick up the can and put it in the mug"
        case 3:
            return "put the banana in the bin"
        case _:
            raise ValueError(f"Scene {scene} not supported")


def main(
    episodes: int = 10,
    scene: int = 1,
    prompt: str | None = None,
    headless: bool = True,
    host: str | None = None,
    port: int | None = None,
    device: str = "cuda:0",
    output_root: str | None = None,
    keyframes: int = 12,
    max_steps: int | None = None,
    video_fps: int = 15,
):
    if not D2A_CONFIG.dreamzero_root.exists():
        raise FileNotFoundError(f"DreamZero repository not found: {D2A_CONFIG.dreamzero_root}")
    os.chdir(D2A_CONFIG.dreamzero_root)

    from isaaclab.app import AppLauncher

    parser = argparse.ArgumentParser(description="DreamZero2AHA simulation evaluation.")
    AppLauncher.add_app_launcher_args(parser)
    args_cli, _ = parser.parse_known_args()
    args_cli.enable_cameras = True
    args_cli.headless = headless
    args_cli.device = device
    app_launcher = AppLauncher(args_cli)
    simulation_app = app_launcher.app

    import sim_evals.environments  # noqa: F401
    from isaaclab_tasks.utils import parse_env_cfg

    env_cfg = parse_env_cfg("DROID", device=args_cli.device, num_envs=1, use_fabric=True)
    task_prompt = prompt or instruction_for_scene(scene)
    env_cfg.set_scene(scene)
    env = gym.make("DROID", cfg=env_cfg)

    resolved_host = host or dreamzero_main_default("host", "localhost")
    resolved_port = port if port is not None else dreamzero_main_default("port", 6000)
    print(f"[D2A] Connecting to DreamZero policy server at {resolved_host}:{resolved_port}")
    client = DreamZeroJointPosClient(remote_host=resolved_host, remote_port=resolved_port)

    if output_root:
        output_base_arg = Path(output_root).expanduser()
        output_base = output_base_arg if output_base_arg.is_absolute() else PROJECT_ROOT / output_base_arg
        output_base = output_base.resolve()
    else:
        output_base = D2A_CONFIG.output_root
    run_started_at = datetime.now(BEIJING_TZ)
    run_dir = output_base / run_started_at.strftime("%Y-%m-%d") / run_started_at.strftime("%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "episode_results.json"
    episode_max_steps = max_steps or env.env.max_episode_length

    with torch.no_grad():
        for ep in range(episodes):
            obs, _ = env.reset()
            obs, _ = env.reset()
            episode_dir = run_dir / f"episode_{ep:04d}"
            recorder = DreamZero2AHATrajectoryRecorder(episode_dir)
            video = []
            end_reason = "max_steps"

            for step in tqdm(range(episode_max_steps), desc=f"Episode {ep + 1}/{episodes}", leave=True):
                ret = client.infer(obs, task_prompt)
                views = extract_views_from_obs(obs)
                recorder.record_step(step, views, action=ret["action"])

                if not headless:
                    cv2.imshow("DreamZero2AHA", cv2.cvtColor(ret["viz"], cv2.COLOR_RGB2BGR))
                    cv2.waitKey(1)
                video.append(ret["viz"])

                action = torch.tensor(ret["action"])[None]
                obs, _, term, trunc, _ = env.step(action)
                if term or trunc:
                    end_reason = "terminated" if term else "truncated"
                    break

            client.reset()
            video_path = episode_dir / f"episode_{ep}.mp4"
            mediapy.write_video(video_path, video, fps=video_fps)

            sampled_frame_indices = sample_indices(len(recorder.records), keyframes)
            recorder.write_frames(sampled_frame_indices)
            grid_path = build_aha_grid(recorder.records, episode_dir / f"episode_{ep}_aha_grid.jpg", keyframes=keyframes)
            request = build_aha_request(
                request_id=f"scene{scene}_episode{ep}",
                image_path=grid_path,
                instruction=task_prompt,
                scene=scene,
            )
            request_path = write_aha_request_json(request, episode_dir / "aha_request.json")

            recorder.write_steps_json()
            result = EpisodeResult(
                episode=ep,
                scene=scene,
                prompt=task_prompt,
                success="unknown",
                end_reason=end_reason,
                steps=len(recorder.records),
                output_dir=str(episode_dir),
                video_path=str(video_path),
                aha_grid_path=str(grid_path) if grid_path else None,
                aha_request_path=str(request_path) if request_path else None,
                success_probe={},
            )
            append_episode_json(result, results_path)

    env.close()
    simulation_app.close()


if __name__ == "__main__":
    tyro.cli(main)
