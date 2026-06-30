"""AHA-style grid builder adapted from AHA process_data.py."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from trajectory_recorder_run_sim_eval_d2a import VIEW_ORDER


def sample_indices(length: int, count: int) -> list[int]:
    if length <= 0:
        return []
    if count <= 1:
        return [length - 1]
    if length <= count:
        return list(range(length))
    return sorted({round(i * (length - 1) / (count - 1)) for i in range(count)})


def _load_resize(path: str | Path, cell_size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return image.resize(cell_size, Image.Resampling.BILINEAR)


def build_aha_grid(
    records: Sequence,
    output_path: str | Path,
    *,
    keyframes: int = 12,
    view_order: Sequence[str] = VIEW_ORDER,
    cell_size: tuple[int, int] = (224, 224),
) -> Path:
    """Build a rows-by-time AHA visual grid from StepRecord-like objects."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    indices = sample_indices(len(records), keyframes)
    cols = max(len(indices), 1)
    rows = len(view_order)
    width = cols * cell_size[0]
    height = rows * cell_size[1]
    grid = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(grid)

    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()

    for col, record_index in enumerate(indices):
        record = records[record_index]
        image_paths = getattr(record, "image_paths", record.get("image_paths"))
        step_index = getattr(record, "step_index", record.get("step_index"))
        for row, view_name in enumerate(view_order):
            x = col * cell_size[0]
            y = row * cell_size[1]
            path = image_paths.get(view_name)
            if path:
                grid.paste(_load_resize(path, cell_size), (x, y))
            draw.rectangle((x, y, x + cell_size[0] - 1, y + cell_size[1] - 1), outline="black", width=2)
            label = f"{step_index}"
            draw.rectangle((x, y, x + 58, y + 30), fill=(0, 0, 0))
            draw.text((x + 6, y + 4), label, fill=(255, 255, 255), font=font)

    grid.save(output_path)
    return output_path
