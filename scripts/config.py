"""Central YAML configuration for the facade designer MVP."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class AppConfig:
    name: str
    user_id: str


@dataclass(frozen=True)
class ModelConfig:
    text: str
    image: str

    def with_updates(
        self,
        *,
        text: str | None = None,
        image: str | None = None,
    ) -> "ModelConfig":
        return replace(
            self,
            text=text if text is not None else self.text,
            image=image if image is not None else self.image,
        )


@dataclass(frozen=True)
class VertexConfig:
    use_vertex_ai: bool
    project: str | None
    location: str
    api_version: str


@dataclass(frozen=True)
class GenerationConfig:
    output_dir: Path
    aspect_ratio: str
    image_size: str

    def with_updates(
        self,
        *,
        output_dir: Path | None = None,
        aspect_ratio: str | None = None,
        image_size: str | None = None,
    ) -> "GenerationConfig":
        return replace(
            self,
            output_dir=(
                output_dir.expanduser().resolve()
                if output_dir is not None
                else self.output_dir
            ),
            aspect_ratio=aspect_ratio if aspect_ratio is not None else self.aspect_ratio,
            image_size=image_size if image_size is not None else self.image_size,
        )


@dataclass(frozen=True)
class AgentNamesConfig:
    orchestrator_name: str
    research_name: str
    prompt_name: str
    generation_name: str
    planning_name: str


@dataclass(frozen=True)
class HistoryConfig:
    enabled: bool
    db_path: Path


@dataclass(frozen=True)
class DesignerConfig:
    app: AppConfig
    models: ModelConfig
    vertex: VertexConfig
    generation: GenerationConfig
    agents: AgentNamesConfig
    history: HistoryConfig

    def with_updates(
        self,
        *,
        models: ModelConfig | None = None,
        generation: GenerationConfig | None = None,
    ) -> "DesignerConfig":
        return replace(
            self,
            models=models if models is not None else self.models,
            generation=generation if generation is not None else self.generation,
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{name}' must be a mapping.")
    return value


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_config(config_path: str | Path | None = None) -> DesignerConfig:
    path = Path(config_path).expanduser().resolve() if config_path else DEFAULT_CONFIG_PATH
    data = _read_yaml(path)

    app = _section(data, "app")
    models = _section(data, "models")
    vertex = _section(data, "vertex")
    generation = _section(data, "generation")
    agents = _section(data, "agents")
    history = _section(data, "history")

    project = _optional_str(vertex.get("project")) or _optional_str(
        os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    location = str(vertex.get("location") or os.getenv("GOOGLE_CLOUD_LOCATION") or "global")
    use_vertex_ai = _bool(vertex.get("use_vertex_ai"), default=True)
    if use_vertex_ai:
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

    return DesignerConfig(
        app=AppConfig(
            name=str(app.get("name", "facade_designer")),
            user_id=str(app.get("user_id", "local_user")),
        ),
        models=ModelConfig(
            text=str(models.get("text", "gemini-3.5-flash")),
            image=str(models.get("image", "gemini-2.5-flash-image")),
        ),
        vertex=VertexConfig(
            use_vertex_ai=use_vertex_ai,
            project=project,
            location=location,
            api_version=str(vertex.get("api_version", "v1")),
        ),
        generation=GenerationConfig(
            output_dir=Path(generation.get("output_dir", "outputs")).expanduser().resolve(),
            aspect_ratio=str(generation.get("aspect_ratio", "16:9")),
            image_size=str(generation.get("image_size", "2K")),
        ),
        agents=AgentNamesConfig(
            orchestrator_name=str(agents.get("orchestrator_name", "FacadeDesignPipeline")),
            research_name=str(agents.get("research_name", "ArchitecturalResearcher")),
            prompt_name=str(agents.get("prompt_name", "PromptArchitect")),
            generation_name=str(agents.get("generation_name", "BuildingImageGenerator")),
            planning_name=str(agents.get("planning_name", "ImplementationPlanner")),
        ),
        history=HistoryConfig(
            enabled=_bool(history.get("enabled"), default=True),
            db_path=Path(history.get("db_path", "outputs/run_history.sqlite")).expanduser().resolve(),
        ),
    )
