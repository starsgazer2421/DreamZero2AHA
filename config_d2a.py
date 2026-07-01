"""Configuration loading for DreamZero2AHA."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config_d2a.yaml"


@dataclass(frozen=True)
class D2AConfig:
    dreamzero_root: Path
    output_root: Path
    config_path: Path


def _parse_simple_yaml(path: Path) -> dict[str, str]:
    """Parse the tiny key-value YAML subset used by config_d2a.yaml."""

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid config line in {path}: {raw_line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def load_d2a_config(config_path: str | Path | None = None) -> D2AConfig:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"D2A config not found: {path}")

    data = _parse_simple_yaml(path)
    base_dir = path.parent
    dreamzero_root = _resolve_path(data.get("dreamzero_root", "../DreamZero/dreamzero"), base_dir=base_dir)
    output_root = Path(data.get("output_root", "output")).expanduser()
    if output_root.is_absolute():
        resolved_output_root = output_root
    else:
        resolved_output_root = base_dir / output_root

    return D2AConfig(
        dreamzero_root=dreamzero_root,
        output_root=resolved_output_root.resolve(),
        config_path=path.resolve(),
    )
