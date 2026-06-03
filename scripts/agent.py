"""ADK agents for the facade designer pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator

from typing_extensions import override

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import FunctionTool, google_search
from google.genai import types

from scripts.config import DesignerConfig, GenerationConfig, ModelConfig, VertexConfig, load_config
from scripts.image_generator import (
    ImageGenerationRequest,
    generate_building_design,
)
from scripts.planning_tools import create_roadmap_image
from scripts.prompting import (
    build_generation_prompt,
    build_implementation_planner_instruction,
    build_prompt_architect_instruction,
    build_research_instruction,
)


logger = logging.getLogger(__name__)


class ImageGenerationAgent(BaseAgent):
    """Custom ADK agent that renders the final facade image."""

    models: ModelConfig
    vertex: VertexConfig
    generation: GenerationConfig
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        *,
        name: str,
        models: ModelConfig,
        vertex: VertexConfig,
        generation: GenerationConfig,
    ):
        super().__init__(
            name=name,
            models=models,
            vertex=vertex,
            generation=generation,
        )

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        logger.info("[%s] Starting image generation.", self.name)

        state = ctx.session.state
        generation_prompt = state.get("generation_prompt") or build_generation_prompt(
            state.get("user_prompt", ""),
            research_notes=state.get("research_notes"),
            has_inspiration=bool(state.get("inspiration_image_path")),
        )
        state["generation_prompt"] = generation_prompt

        request = ImageGenerationRequest(
            building_image_path=Path(state["building_image_path"]),
            inspiration_image_path=(
                Path(state["inspiration_image_path"])
                if state.get("inspiration_image_path")
                else None
            ),
            prompt=generation_prompt,
            output_dir=self.generation.output_dir,
            model=self.models.image,
            google_cloud_project=self.vertex.project,
            google_cloud_location=self.vertex.location,
            use_vertex_ai=self.vertex.use_vertex_ai,
            vertex_api_version=self.vertex.api_version,
            aspect_ratio=self.generation.aspect_ratio,
            image_size=self.generation.image_size,
        )

        result = await asyncio.to_thread(generate_building_design, request)
        state["generated_image_path"] = str(result.image_path)
        state["prompt_path"] = str(result.prompt_path)
        state["notes_path"] = str(result.notes_path)
        state["image_generation_model"] = result.model

        state_delta = {
            "generation_prompt": generation_prompt,
            "generated_image_path": str(result.image_path),
            "prompt_path": str(result.prompt_path),
            "notes_path": str(result.notes_path),
            "image_generation_model": result.model,
        }
        message = (
            "Facade design generated.\n"
            f"Image: {result.image_path}\n"
            f"Prompt: {result.prompt_path}\n"
            f"Notes: {result.notes_path}\n"
            f"Model: {result.model}"
        )
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=message)]),
            actions=EventActions(state_delta=state_delta),
        )


class MarkdownReportAgent(BaseAgent):
    """Custom ADK agent that stores the implementation report as Markdown."""

    model_config = {"arbitrary_types_allowed": True}

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        generated_image_path = Path(str(state.get("generated_image_path", "")))
        output_dir = generated_image_path.parent if generated_image_path.name else Path("outputs")
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / f"{generated_image_path.stem or 'facade-design'}-report.md"
        roadmap_image_path = str(state.get("roadmap_image_path", ""))
        if not roadmap_image_path:
            roadmap_candidate = output_dir / f"{generated_image_path.stem or 'facade-design'}-roadmap.png"
            if roadmap_candidate.exists():
                roadmap_image_path = str(roadmap_candidate)
        implementation_plan = str(state.get("implementation_plan", "")).strip()
        generation_prompt = str(state.get("generation_prompt", "")).strip()

        lines = [
            "# Facade Transformation Implementation Report",
            "",
        ]
        if roadmap_image_path:
            lines.extend(["## Roadmap", "", f"![Roadmap]({roadmap_image_path})", ""])
        if implementation_plan:
            lines.extend([implementation_plan, ""])
        if generated_image_path:
            lines.extend(["## Generated Design", "", f"![Generated design]({generated_image_path})", ""])
        if generation_prompt:
            lines.extend(["## Image Generation Prompt", "", "```text", generation_prompt, "```", ""])

        report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        state_delta = {
            "implementation_report_path": str(report_path),
            "roadmap_image_path": roadmap_image_path,
        }
        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"Implementation report saved: {report_path}")],
            ),
            actions=EventActions(state_delta=state_delta),
        )


def build_agent(
    *,
    text_model: str | None = None,
    config: DesignerConfig | None = None,
) -> SequentialAgent:
    config = config or load_config()
    text_model = text_model or config.models.text

    research_agent = LlmAgent(
        name=config.agents.research_name,
        model=text_model,
        instruction=build_research_instruction()
        + "\n\nUser prompt:\n{user_prompt}",
        description="Finds architectural context and material strategies for facade renovation.",
        tools=[google_search],
        output_key="research_notes",
    )

    prompt_agent = LlmAgent(
        name=config.agents.prompt_name,
        model=text_model,
        instruction=build_prompt_architect_instruction()
        + "\n\nResearch notes:\n{research_notes}\n\nUser prompt:\n{user_prompt}",
        description="Turns the design request into a precise image generation prompt.",
        output_key="generation_prompt",
    )

    image_generation_agent = ImageGenerationAgent(
        name=config.agents.generation_name,
        models=config.models,
        vertex=config.vertex,
        generation=config.generation,
    )

    implementation_planner_agent = LlmAgent(
        name=config.agents.planning_name,
        model=text_model,
        instruction=build_implementation_planner_instruction()
        + "\n\nResearch notes:\n{research_notes}"
        + "\n\nFinal image-generation prompt:\n{generation_prompt}"
        + "\n\nGenerated image path:\n{generated_image_path}"
        + "\n\nImage model notes path:\n{notes_path}",
        description="Creates an execution roadmap, team plan, risks, and next actions for the facade transformation.",
        tools=[google_search, FunctionTool(create_roadmap_image)],
        output_key="implementation_plan",
    )

    report_agent = MarkdownReportAgent(name="ImplementationReportWriter")

    return SequentialAgent(
        name=config.agents.orchestrator_name,
        sub_agents=[
            research_agent,
            prompt_agent,
            image_generation_agent,
            implementation_planner_agent,
            report_agent,
        ],
        description="Runs facade design specialists in order: research, prompt, image generation, implementation planning, report writing.",
    )


root_agent = build_agent()
