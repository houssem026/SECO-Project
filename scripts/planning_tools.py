"""Tools for facade implementation planning agents."""

from __future__ import annotations

from pathlib import Path
import re

from google.adk.tools.tool_context import ToolContext


DEFAULT_ROADMAP_PHASES = [
    "Discovery",
    "Feasibility",
    "Design development",
    "Approvals",
    "Procurement",
    "Construction",
    "Quality control",
    "Handover",
]
def _clean_label(value: str) -> str:
    label = " ".join(str(value).strip().split())
    label = label.replace("&", "and")
    label = re.sub(r'["<>|`:,]', "", label)
    return label[:80] or "Project phase"


def _clean_duration(value: str) -> str:
    duration = " ".join(str(value).strip().split())
    duration = duration.replace("&", "and")
    duration = re.sub(r'["<>|`:,]', "", duration)
    return duration[:40]


def create_roadmap_chart(
    project_title: str,
    phases: list[str],
    tool_context: ToolContext,
    estimated_durations: list[str] | None = None,
) -> dict[str, str]:
    """Create a Mermaid roadmap chart file from ordered facade phases and project-specific durations."""
    generated_image_path = Path(str(tool_context.state.get("generated_image_path", "")))
    output_dir = generated_image_path.parent if generated_image_path.name else Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_path = output_dir / f"{generated_image_path.stem or 'facade-design'}-roadmap.mmd"
    clean_phases = [_clean_label(phase) for phase in phases if str(phase).strip()]
    if not clean_phases:
        clean_phases = DEFAULT_ROADMAP_PHASES
    clean_durations = [
        _clean_duration(duration)
        for duration in (estimated_durations or [])
        if str(duration).strip()
    ]

    title = _clean_label(project_title or "Facade transformation roadmap")
    sections = "\n".join(
        f'    phase_{index}["{phase}<br/>Est. {duration}"]'
        for index, phase in enumerate(clean_phases, start=1)
        for duration in [
            clean_durations[index - 1]
            if index <= len(clean_durations)
            else "to confirm"
        ]
    )
    links = "\n".join(
        f"    phase_{index} --> phase_{index + 1}"
        for index in range(1, len(clean_phases))
    )
    mermaid = "\n".join(
        [
            "flowchart LR",
            f'    title["{title}"] --> phase_1',
            sections,
            links,
            "",
        ]
    )
    chart_path.write_text(mermaid, encoding="utf-8")
    tool_context.state["roadmap_chart_path"] = str(chart_path)
    return {
        "roadmap_chart_path": str(chart_path),
        "chart_format": "mermaid",
    }
