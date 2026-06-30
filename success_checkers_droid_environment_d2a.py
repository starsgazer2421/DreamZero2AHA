"""Rule-based success checks for sim-evals DROID scenes.

This module complements DreamZero's eval_utils/run_sim_eval.py. The upstream
sim-evals environment currently exposes only timeout termination, so task
success needs to be checked from simulator state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SceneSuccessSpec:
    scene: int
    carried_object_aliases: tuple[str, ...]
    target_aliases: tuple[str, ...]
    xy_radius: float
    z_min: float | None = None
    z_max: float | None = None


SCENE_SUCCESS_SPECS: dict[int, SceneSuccessSpec] = {
    1: SceneSuccessSpec(
        scene=1,
        carried_object_aliases=("rubiks_cube", "cube"),
        target_aliases=("_24_bowl", "bowl"),
        xy_radius=0.14,
        z_min=-0.02,
        z_max=0.18,
    ),
    2: SceneSuccessSpec(
        scene=2,
        carried_object_aliases=("_10_potted_meat_can", "potted_meat_can", "can"),
        target_aliases=("_25_mug", "mug"),
        xy_radius=0.13,
        z_min=-0.03,
        z_max=0.20,
    ),
    3: SceneSuccessSpec(
        scene=3,
        carried_object_aliases=("_11_banana", "banana"),
        target_aliases=("KLT_Bin", "bin", "Bin"),
        xy_radius=0.18,
        z_min=-0.04,
        z_max=0.22,
    ),
}


def _to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    arr = np.asarray(value, dtype=np.float64)
    return arr.reshape(-1)


def _asset_position(asset: Any) -> np.ndarray | None:
    data = getattr(asset, "data", None)
    if data is None:
        return None

    for attr in ("root_pos_w", "body_pos_w", "root_state_w"):
        if not hasattr(data, attr):
            continue
        arr = _to_numpy(getattr(data, attr))
        if arr.size >= 3:
            return arr[:3]
    return None


def _scene_assets(env: Any) -> dict[str, Any]:
    scene = getattr(env, "scene", None)
    if scene is None and hasattr(env, "unwrapped"):
        scene = getattr(env.unwrapped, "scene", None)
    if scene is None and hasattr(env, "env"):
        scene = getattr(env.env, "scene", None)
    if scene is None:
        return {}

    assets: dict[str, Any] = {}
    if hasattr(scene, "keys"):
        for name in scene.keys():
            try:
                assets[str(name)] = scene[name]
            except Exception:
                pass
    for name in dir(scene):
        if name.startswith("_") or name in assets:
            continue
        try:
            value = getattr(scene, name)
        except Exception:
            continue
        if hasattr(value, "data"):
            assets[name] = value
    return assets


def _find_asset(assets: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str | None, Any | None]:
    lowered = {name.lower(): (name, asset) for name, asset in assets.items()}
    for alias in aliases:
        direct = lowered.get(alias.lower())
        if direct is not None:
            return direct
    for alias in aliases:
        alias_lower = alias.lower()
        for name, asset in assets.items():
            if alias_lower in name.lower():
                return name, asset
    return None, None


def check_scene_success(env: Any, scene: int) -> tuple[bool, dict[str, Any]]:
    """Return success plus a probe dictionary for logging and debugging."""

    spec = SCENE_SUCCESS_SPECS.get(scene)
    if spec is None:
        return False, {"reason": f"unsupported_scene_{scene}"}

    assets = _scene_assets(env)
    object_name, obj = _find_asset(assets, spec.carried_object_aliases)
    target_name, target = _find_asset(assets, spec.target_aliases)
    if obj is None or target is None:
        return False, {
            "reason": "asset_not_found",
            "available_assets": sorted(assets.keys()),
            "object_aliases": list(spec.carried_object_aliases),
            "target_aliases": list(spec.target_aliases),
        }

    object_pos = _asset_position(obj)
    target_pos = _asset_position(target)
    if object_pos is None or target_pos is None:
        return False, {
            "reason": "position_not_found",
            "object_name": object_name,
            "target_name": target_name,
        }

    delta = object_pos - target_pos
    xy_dist = float(np.linalg.norm(delta[:2]))
    z_delta = float(delta[2])
    z_ok = True
    if spec.z_min is not None:
        z_ok = z_ok and z_delta >= spec.z_min
    if spec.z_max is not None:
        z_ok = z_ok and z_delta <= spec.z_max
    success = xy_dist <= spec.xy_radius and z_ok
    return success, {
        "object_name": object_name,
        "target_name": target_name,
        "object_pos": object_pos.tolist(),
        "target_pos": target_pos.tolist(),
        "xy_dist": xy_dist,
        "z_delta": z_delta,
        "xy_radius": spec.xy_radius,
        "z_min": spec.z_min,
        "z_max": spec.z_max,
    }

