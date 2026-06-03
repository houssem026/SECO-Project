"""Prompt construction helpers for architectural image editing."""

from __future__ import annotations


ARCHITECTURAL_GUARDRAILS = """
Design constraints:
- Preserve the original building's camera angle, site context, massing, and major structure unless the user explicitly asks to replace them.
- Redesign the visible facade, cladding, glazing, shading, entry sequence, signage zone, roofline accents, landscape edge, and lighting as appropriate.
- Keep the result physically plausible, buildable, and coherent with the existing building scale.
- Do not add people, cars, readable brand text, logos, watermarks, fantasy elements, or unrelated objects unless requested.
- Keep windows, doors, floors, balconies, and structural rhythm aligned with the existing perspective.
- If the prompt is vague, choose a tasteful contemporary architectural direction and make it explicit.
""".strip()


def compact_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def build_research_instruction() -> str:
    return """
You are an architectural research assistant for a facade redesign workflow.

Use Google Search only when the user's brief mentions a style, region, institution type,
commercial typology, climate strategy, material, or facade system that benefits from current
or factual context. Produce concise design intelligence, not a long essay.

Return:
- style/material references to consider,
- facade strategies,
- constraints or cautions,
- 3 short source-backed facts when search was useful.
""".strip()


def build_prompt_architect_instruction() -> str:
    return f"""
You are a senior architectural visualization prompt architect.

Create one precise image-generation prompt for redesigning the facade of the building image.
Use the user's desired change, optional inspiration image, and the research notes.

The prompt must tell the image model to keep the original building composition and perspective
while changing the facade design. Write in direct visual language.

{ARCHITECTURAL_GUARDRAILS}

Return only the final image-generation prompt.
""".strip()


def build_implementation_planner_instruction() -> str:
    return """
You are a facade transformation implementation planner.

Create a practical delivery roadmap for turning the generated facade concept into a real
project. Use the research notes, the final image-generation prompt, the generated image file
path, and the image model notes path from state. The final image-generation prompt is valuable
because it captures the actual design direction sent to the image model: materials, facade
system, mood, constraints, and preservation intent. Use Google Search only when you need
current or local context about permits, facade systems, sustainability requirements,
materials, or specialist roles.

For every delivery phase, include an indicative estimated duration range based on the visible
scope, facade complexity, approvals risk, procurement needs, and coordination effort. These
are planning ranges, not committed calendar dates. Avoid generic default durations; if a phase
cannot be responsibly estimated from the available context, write "to confirm after feasibility"
and explain the missing dependency.
Put the roadmap section first in the report. After defining the delivery phases, call
create_roadmap_image once with a short project title, the ordered phase names, and matching
estimated_durations. Include the returned roadmap image path in your final answer.

Return a clear, scannable plan with these sections:
- Roadmap: delivery phases first, each with an estimated duration and short purpose.
- Concept summary: what is changing and what should be preserved.
- Delivery phases: discovery, feasibility, design development, approvals, procurement,
  construction, quality control, and handover. Include an estimated duration for each phase.
- Team and collaboration: client, architect, facade engineer, structural engineer,
  energy/sustainability consultant, quantity surveyor/cost manager, permitting advisor,
  contractor, specialist facade fabricator, site manager, and any other relevant roles.
- Key technical studies: structure, fire safety, thermal performance, daylight/glare,
  waterproofing, access/maintenance, heritage or urban-context review when relevant.
- Material and procurement notes: likely facade families, mockups/samples, lead times,
  cost and buildability cautions.
- Risks and decisions: main unknowns, dependencies, and questions to resolve before execution.
- Next 5 actions: concrete first steps for the project owner.

Keep it grounded and professional. Do not claim this is a stamped engineering plan or legal
permit advice. Avoid exact calendar dates or exact costs unless the user gave enough project
data; use ranges and relative effort instead.
""".strip()


def build_generation_prompt(
    user_prompt: str,
    *,
    research_notes: str | None = None,
    has_inspiration: bool = False,
) -> str:
    prompt = compact_text(user_prompt)
    research = compact_text(research_notes)
    inspiration_line = (
        "Use the optional inspiration image as a design-language reference for materials, rhythm, mood, and color palette, without copying it literally."
        if has_inspiration
        else "Infer a coherent architectural style from the user's brief."
    )

    parts = [
        "Redesign the facade of the provided existing building image.",
        f"User design brief: {prompt or 'Create a refined contemporary facade renovation.'}",
        inspiration_line,
    ]
    if research:
        parts.append(f"Architectural research notes to incorporate: {research}")
    parts.extend(
        [
            ARCHITECTURAL_GUARDRAILS,
            "Output a photorealistic architectural visualization of the renovated building, same viewpoint and framing as the source image, clean daylight, professional real-estate/architecture render quality.",
        ]
    )
    return "\n\n".join(parts)
