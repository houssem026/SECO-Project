"""Shared ADK runner pipeline for CLI and Streamlit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from scripts.agent import build_agent
from scripts.config import DesignerConfig, load_config


@dataclass(frozen=True)
class PipelineInputs:
    building_image_path: Path
    user_prompt: str
    inspiration_image_path: Path | None = None


@dataclass(frozen=True)
class PipelineOverrides:
    config_path: str | Path | None = None
    output_dir: Path | None = None
    aspect_ratio: str | None = None
    image_size: str | None = None
    text_model: str | None = None
    image_model: str | None = None


@dataclass(frozen=True)
class PipelineResult:
    final_text: str
    generated_image_path: str
    prompt_path: str
    notes_path: str
    model: str
    implementation_plan: str = ""
    roadmap_chart_path: str = ""


@dataclass(frozen=True)
class PipelineUpdate:
    author: str
    text: str
    is_final_response: bool = False
    result: PipelineResult | None = None


def build_run_config(overrides: PipelineOverrides) -> DesignerConfig:
    config = load_config(overrides.config_path)

    generation_config = config.generation
    if overrides.output_dir:
        generation_config = generation_config.with_updates(output_dir=overrides.output_dir)
    if overrides.aspect_ratio:
        generation_config = generation_config.with_updates(aspect_ratio=overrides.aspect_ratio)
    if overrides.image_size:
        generation_config = generation_config.with_updates(image_size=overrides.image_size)

    model_config = config.models
    if overrides.image_model:
        model_config = model_config.with_updates(image=overrides.image_model)
    if overrides.text_model:
        model_config = model_config.with_updates(text=overrides.text_model)

    return config.with_updates(models=model_config, generation=generation_config)


def _event_text(event: object) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        return ""

    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n\n".join(texts).strip()


def _normalize_path(value: object) -> str:
    if not value:
        return ""

    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())


async def stream_pipeline(
    inputs: PipelineInputs,
    overrides: PipelineOverrides | None = None,
) -> AsyncGenerator[PipelineUpdate, None]:
    overrides = overrides or PipelineOverrides()
    run_config = build_run_config(overrides)

    session_id = f"session-{uuid4().hex}"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=run_config.app.name,
        user_id=run_config.app.user_id,
        session_id=session_id,
        state={
            "building_image_path": str(inputs.building_image_path),
            "inspiration_image_path": (
                str(inputs.inspiration_image_path) if inputs.inspiration_image_path else ""
            ),
            "user_prompt": inputs.user_prompt,
        },
    )

    runner = Runner(
        agent=build_agent(config=run_config),
        app_name=run_config.app.name,
        session_service=session_service,
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text="Create the facade redesign using the session images and brief.")],
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=run_config.app.user_id,
        session_id=session_id,
        new_message=message,
    ):
        text = _event_text(event)
        is_final = event.is_final_response()
        if is_final and text:
            final_text = text
        if text:
            yield PipelineUpdate(
                author=getattr(event, "author", "agent"),
                text=text,
                is_final_response=is_final,
            )

    final_session = await session_service.get_session(
        app_name=run_config.app.name,
        user_id=run_config.app.user_id,
        session_id=session_id,
    )
    state = final_session.state
    result = PipelineResult(
        final_text=final_text,
        generated_image_path=_normalize_path(state.get("generated_image_path")),
        prompt_path=_normalize_path(state.get("prompt_path")),
        notes_path=_normalize_path(state.get("notes_path")),
        model=str(state.get("image_generation_model", run_config.models.image)),
        implementation_plan=str(state.get("implementation_plan", "")),
        roadmap_chart_path=_normalize_path(state.get("roadmap_chart_path")),
    )
    yield PipelineUpdate(
        author=run_config.agents.orchestrator_name,
        text=final_text,
        is_final_response=True,
        result=result,
    )


async def run_pipeline(
    inputs: PipelineInputs,
    overrides: PipelineOverrides | None = None,
) -> PipelineResult:
    result: PipelineResult | None = None
    async for update in stream_pipeline(inputs, overrides):
        if update.result:
            result = update.result

    if result is None:
        raise RuntimeError("Pipeline finished without returning a result.")
    return result
