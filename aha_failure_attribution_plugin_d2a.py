"""AHA-style failure attribution plugin glue for DreamZero rollouts.

DreamZero2AHA treats AHA as an evaluation plugin, not as an online policy or
mandatory inference service. This module records the AHA-ready assets produced
for a failed episode so an AHA attribution workflow can consume them offline.
"""

from __future__ import annotations

from pathlib import Path

from schemas_d2a import AttributionResult


class AHAFailureAttributionPlugin:
    """Prepare failed DreamZero episodes for AHA-style attribution."""

    name = "aha_failure_attribution_plugin"

    def record_failure_case(
        self,
        *,
        image_path: str | Path,
        prompt: str,
        request_json: str | Path,
    ) -> AttributionResult:
        return AttributionResult(
            success_answer="failure",
            failure_type="unknown",
            failure_reason="Prepared AHA-style failure attribution assets for offline evaluation.",
            raw_text=prompt,
            plugin_name=self.name,
            artifact_paths={
                "grid_image": str(image_path),
                "request_json": str(request_json),
            },
        )


def make_aha_failure_attribution_plugin() -> AHAFailureAttributionPlugin:
    return AHAFailureAttributionPlugin()
