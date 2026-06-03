"""Tools for facade implementation planning agents."""

from __future__ import annotations

from pathlib import Path
import textwrap

from google.adk.tools.tool_context import ToolContext


def create_roadmap_image(
    project_title: str,
    phases: list[str],
    tool_context: ToolContext,
    estimated_durations: list[str] | None = None,
) -> dict[str, str]:
    """Generate a roadmap image with Imagen, or fall back to a Markdown table."""
    generated_image_path = Path(str(tool_context.state.get("generated_image_path", "")))
    output_dir = generated_image_path.parent if generated_image_path.name else Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_phases = [str(phase).strip() for phase in phases if str(phase).strip()]
    clean_durations = [
        str(duration).strip()
        for duration in (estimated_durations or [])
        if str(duration).strip()
    ]
    rows = []
    for index, phase in enumerate(clean_phases, start=1):
        duration = clean_durations[index - 1] if index <= len(clean_durations) else "to confirm"
        rows.append((index, phase, duration))

    if not rows:
        rows = [
            (1, "Discovery", "to confirm"),
            (2, "Feasibility", "to confirm"),
            (3, "Design development", "to confirm"),
            (4, "Approvals and delivery", "to confirm"),
        ]

    roadmap_table = "\n".join(
        ["| Step | Phase | Estimated duration |", "|---:|---|---|"]
        + [f"| {index} | {phase} | {duration} |" for index, phase, duration in rows]
    )
    tool_context.state["roadmap_table"] = roadmap_table

    roadmap_image_path = output_dir / f"{generated_image_path.stem or 'facade-design'}-roadmap.png"
    phase_lines = "\n".join(
        f"{index}. {phase} - estimated duration: {duration}"
        for index, phase, duration in rows
    )
    facade_style = str(tool_context.state.get("generation_prompt", "")).strip()[:900]
    title = str(project_title or "Facade transformation roadmap").strip()

    prompt = textwrap.dedent(
        f"""
        Create a clean, professional 16:9 roadmap diagram for an architectural facade transformation report. Include only the roadmap steps.
        The diagram must clearly communicate the sequence of steps, their durations, and their logical progression.
        Prioritize readability, simplicity, and ordering of the steps.

        Title: {title}
        Roadmap steps:
        {phase_lines}
        """
    ).strip()

    try:
        from google import genai
        from google.genai.types import GenerateImagesConfig

        image_model = "imagen-4.0-generate-001"
        client = genai.Client()

        response = client.models.generate_images(
            model=image_model,
            prompt=prompt,
            config=GenerateImagesConfig(
                aspect_ratio="16:9",
                image_size="2K",
                number_of_images=1,
            ),
        )
        response.generated_images[0].image.save(str(roadmap_image_path))
    except Exception as exc:
        tool_context.state["roadmap_image_path"] = ""
        tool_context.state["roadmap_image_model"] = f"fallback_table: {type(exc).__name__}"
        return {
            "roadmap_image_path": "",
            "roadmap_table": roadmap_table,
            "image_model": tool_context.state["roadmap_image_model"],
        }

    tool_context.state["roadmap_image_path"] = str(roadmap_image_path)
    tool_context.state["roadmap_image_model"] = image_model
    return {
        "roadmap_image_path": str(roadmap_image_path),
        "roadmap_table": roadmap_table,
        "image_model": image_model,
    }
