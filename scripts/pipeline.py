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
from scripts.history_store import RunHistoryStore


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
    run_id: str
    final_text: str
    generated_image_path: str
    prompt_path: str
    notes_path: str
    model: str
    implementation_plan: str = ""
    roadmap_image_path: str = ""
    implementation_report_path: str = ""
    history_db_path: str = ""


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


def _read_text_file(path_value: object) -> str:
    path_text = _normalize_path(path_value)
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return ""


def _record_file_artifact(
    history: RunHistoryStore | None,
    *,
    run_id: str,
    agent_name: str,
    artifact_type: str,
    name: str,
    path_value: object,
    mime_type: str = "",
    include_content: bool = False,
) -> None:
    if history is None:
        return
    path = _normalize_path(path_value)
    if not path:
        return
    history.add_artifact(
        run_id=run_id,
        agent_name=agent_name,
        artifact_type=artifact_type,
        name=name,
        content=_read_text_file(path) if include_content else "",
        path=path,
        mime_type=mime_type,
    )


def _record_final_artifacts(
    history: RunHistoryStore | None,
    *,
    run_id: str,
    state: dict[str, object],
) -> None:
    if history is None:
        return

    if state.get("generation_prompt"):
        history.add_artifact(
            run_id=run_id,
            agent_name="PromptArchitect",
            artifact_type="text",
            name="generation_prompt",
            content=str(state.get("generation_prompt", "")),
        )
    if state.get("implementation_plan"):
        history.add_artifact(
            run_id=run_id,
            agent_name="ImplementationPlanner",
            artifact_type="text",
            name="implementation_plan",
            content=str(state.get("implementation_plan", "")),
        )
    if state.get("roadmap_table"):
        history.add_artifact(
            run_id=run_id,
            agent_name="ImplementationPlanner",
            artifact_type="table",
            name="roadmap_table",
            content=str(state.get("roadmap_table", "")),
        )

    _record_file_artifact(
        history,
        run_id=run_id,
        agent_name="BuildingImageGenerator",
        artifact_type="image",
        name="generated_design",
        path_value=state.get("generated_image_path"),
        mime_type="image/png",
    )
    _record_file_artifact(
        history,
        run_id=run_id,
        agent_name="BuildingImageGenerator",
        artifact_type="text",
        name="saved_generation_prompt",
        path_value=state.get("prompt_path"),
        mime_type="text/plain",
        include_content=True,
    )
    _record_file_artifact(
        history,
        run_id=run_id,
        agent_name="BuildingImageGenerator",
        artifact_type="text",
        name="model_notes",
        path_value=state.get("notes_path"),
        mime_type="text/plain",
        include_content=True,
    )
    _record_file_artifact(
        history,
        run_id=run_id,
        agent_name="ImplementationPlanner",
        artifact_type="image",
        name="roadmap_image",
        path_value=state.get("roadmap_image_path"),
        mime_type="image/png",
    )
    _record_file_artifact(
        history,
        run_id=run_id,
        agent_name="ImplementationReportWriter",
        artifact_type="markdown",
        name="implementation_report",
        path_value=state.get("implementation_report_path"),
        mime_type="text/markdown",
        include_content=True,
    )


async def stream_pipeline(
    inputs: PipelineInputs,
    overrides: PipelineOverrides | None = None,
) -> AsyncGenerator[PipelineUpdate, None]:
    overrides = overrides or PipelineOverrides()
    run_config = build_run_config(overrides)

    run_id = f"run-{uuid4().hex}"
    session_id = f"session-{uuid4().hex}"
    history = (
        RunHistoryStore(run_config.history.db_path)
        if run_config.history.enabled
        else None
    )
    if history:
        history.start_run(
            run_id=run_id,
            session_id=session_id,
            user_prompt=inputs.user_prompt,
            building_image_path=inputs.building_image_path,
            inspiration_image_path=inputs.inspiration_image_path,
            output_dir=run_config.generation.output_dir,
            text_model=run_config.models.text,
            image_model=run_config.models.image,
        )
        history.add_artifact(
            run_id=run_id,
            agent_name="User",
            artifact_type="text",
            name="user_prompt",
            content=inputs.user_prompt,
        )
        history.add_artifact(
            run_id=run_id,
            agent_name="User",
            artifact_type="image",
            name="building_image",
            path=str(inputs.building_image_path),
            mime_type="image",
        )
        if inputs.inspiration_image_path:
            history.add_artifact(
                run_id=run_id,
                agent_name="User",
                artifact_type="image",
                name="inspiration_image",
                path=str(inputs.inspiration_image_path),
                mime_type="image",
            )

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
    event_index = 0
    try:
        async for event in runner.run_async(
            user_id=run_config.app.user_id,
            session_id=session_id,
            new_message=message,
        ):
            text = _event_text(event)
            is_final = event.is_final_response()
            author = getattr(event, "author", "agent")
            if is_final and text:
                final_text = text
            if text:
                event_index += 1
                if history:
                    history.add_artifact(
                        run_id=run_id,
                        agent_name=author,
                        artifact_type="text",
                        name="agent_event",
                        content=text,
                        metadata={
                            "event_index": event_index,
                            "is_final_response": is_final,
                        },
                    )
                yield PipelineUpdate(
                    author=author,
                    text=text,
                    is_final_response=is_final,
                )
    except Exception as exc:
        if history:
            history.finish_run(
                run_id=run_id,
                status="failed",
                final_text=final_text,
                error=str(exc),
            )
        raise

    final_session = await session_service.get_session(
        app_name=run_config.app.name,
        user_id=run_config.app.user_id,
        session_id=session_id,
    )
    state = final_session.state
    _record_final_artifacts(history, run_id=run_id, state=state)
    result = PipelineResult(
        run_id=run_id,
        final_text=final_text,
        generated_image_path=_normalize_path(state.get("generated_image_path")),
        prompt_path=_normalize_path(state.get("prompt_path")),
        notes_path=_normalize_path(state.get("notes_path")),
        model=str(state.get("image_generation_model", run_config.models.image)),
        implementation_plan=str(state.get("implementation_plan", "")),
        roadmap_image_path=_normalize_path(state.get("roadmap_image_path")),
        implementation_report_path=_normalize_path(state.get("implementation_report_path")),
        history_db_path=str(run_config.history.db_path) if history else "",
    )
    if history:
        history.finish_run(
            run_id=run_id,
            status="completed",
            final_text=final_text,
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
