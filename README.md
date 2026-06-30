# DreamZero2AHA

DreamZero2AHA is a non-invasive adapter project for evaluating DreamZero simulation rollouts with AHA-style failure attribution.

The key idea is:

1. DreamZero runs the policy in `sim-evals`.
2. The simulator state provides a rule-based success/failure decision.
3. Failed episodes are converted into AHA-style multi-view temporal grids.
4. The grid and prompt are saved as AHA-ready evaluation artifacts.
5. Results are written as per-episode JSONL files.

## Pipeline

![DreamZero2AHA pipeline](assets/d2a_pipeline_paper_style.png)

## Project Contents

This project provides derivative adapter files whose names preserve the source context:

- `config_d2a.yaml`: editable project config for DreamZero path, AHA path, and output path
- `config_d2a.py`: config loader that resolves relative/absolute paths from `config_d2a.yaml`
- `run_sim_eval_d2a.py`: derivative runner based on DreamZero `eval_utils/run_sim_eval.py`
- `success_checkers_droid_environment_d2a.py`: success probes for sim-evals DROID scenes
- `trajectory_recorder_run_sim_eval_d2a.py`: camera/action recorder for DreamZero rollouts
- `process_data_grid_d2a.py`: AHA-style grid builder inspired by AHA `process_data.py`
- `make_json_prompt_d2a.py`: AHA conversation JSON builder inspired by AHA `make_json.py`
- `aha_failure_attribution_plugin_d2a.py`: AHA-style failure attribution plugin glue
- `report_eval_metrics_d2a.py`: JSONL and summary helpers
- `schemas_d2a.py`: shared dataclasses for step records, attribution metadata, and JSONL episode results

## How to Start

Check `config_d2a.yaml` first:

```yaml
dreamzero_root: ../dreamzero
aha_root: ../AHA
output_root: output
```

`dreamzero_root`, `aha_root`, and `output_root` are resolved relative to this `DreamZero2AHA` directory unless they are absolute paths.

After starting the DreamZero policy server on the server machine, run the client-side evaluator:

```bash
python DreamZero2AHA/run_sim_eval_d2a.py \
  --episodes 10 \
  --scene 1 \
  --prompt "put the cube in the bowl"
```

The runner reads `config_d2a.yaml`, adds the configured DreamZero root and `eval_utils/sim-evals/src` to `PYTHONPATH`, then switches the working directory to the DreamZero root before launching IsaacLab. This keeps DreamZero assets and relative paths compatible with the original evaluation code.

Useful runner arguments:

- `--episodes`: number of simulation episodes to run
- `--scene`: sim-evals DROID scene id; currently `1`, `2`, or `3`
- `--prompt`: task instruction sent to the DreamZero policy server; if omitted, a default prompt is selected from `--scene`
- `--host` / `--port`: optional DreamZero policy server address; defaults to `localhost:6000`, matching the original DreamZero evaluator
- `--output-root`: output directory; defaults to `output_root` in `config_d2a.yaml`
- `--keyframes`: number of temporal columns sampled into the AHA grid
- `--max-steps`: optional per-episode step cap; defaults to the environment max episode length
- `--video-fps`: saved rollout video frame rate
- `--enable-aha-plugin` / `--no-enable-aha-plugin`: whether to record AHA attribution plugin metadata for failed episodes

Outputs are written under `DreamZero2AHA/output/` by default and include:

- `episode_XXXX/frames/`
- `episode_XXXX/steps.json`
- `episode_XXXX/episode_N.mp4`
- `episode_XXXX/episode_N_aha_grid.jpg` for failures
- `episode_XXXX/aha_request.json` for failures
- `episode_results.jsonl`

Each JSONL row uses a flat evaluation schema:

```json
{
  "episode": 0,
  "scene": 1,
  "prompt": "put the cube in the bowl",
  "success": false,
  "failure_type": "unknown",
  "video_path": "...",
  "aha_grid_path": "...",
  "aha_request_path": "..."
}
```

For successful episodes, `failure_type` is `null`. Task progress fields are reserved for later and are not emitted yet.

## Project Changelog

- **2026-07-01**:
  - Created the code repository and completed the first draft of the code, with the core D2A functionality initially implemented.
  - **Note**: No demo testing or debugging has been done yet, and task progress hasn't been set up.

