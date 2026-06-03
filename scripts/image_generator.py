"""Gemini image generation bridge used by the ADK custom agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image


@dataclass(frozen=True)
class ImageGenerationRequest:
    building_image_path: Path
    prompt: str
    output_dir: Path
    model: str
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    use_vertex_ai: bool = True
    vertex_api_version: str = "v1"
    inspiration_image_path: Path | None = None
    aspect_ratio: str = "16:9"
    image_size: str = "2K"


@dataclass(frozen=True)
class ImageGenerationResult:
    image_path: Path
    prompt_path: Path
    notes_path: Path
    model: str
    text_notes: str


def _open_images(paths: Iterable[Path]) -> list[Image.Image]:
    images: list[Image.Image] = []
    for path in paths:
        image = Image.open(path)
        image.load()
        images.append(image)
    return images


def generate_building_design(request: ImageGenerationRequest) -> ImageGenerationResult:
    from google import genai
    from google.genai import types

    output_dir = request.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    image_path = output_dir / f"facade-design-{stamp}.png"
    prompt_path = output_dir / "latest_prompt.txt"
    notes_path = output_dir / "latest_notes.txt"

    image_paths = [request.building_image_path]
    if request.inspiration_image_path:
        image_paths.append(request.inspiration_image_path)

    opened_images = _open_images(image_paths)
    contents: list[object] = [request.prompt, opened_images[0]]
    if request.inspiration_image_path and len(opened_images) > 1:
        contents.extend(
            [
                "The next image is optional inspiration. Use it for design language, not as the building geometry.",
                opened_images[1],
            ]
        )

    config_kwargs: dict[str, object] = {
        "response_modalities": ["TEXT", "IMAGE"],
        "image_config": types.ImageConfig(
            aspect_ratio=request.aspect_ratio,
            image_size=request.image_size,
        ),
    }

    client_kwargs: dict[str, object] = {
        "http_options": types.HttpOptions(api_version=request.vertex_api_version),
    }
    if request.use_vertex_ai:
        client_kwargs["vertexai"] = True
        if request.google_cloud_project:
            client_kwargs["project"] = request.google_cloud_project
        if request.google_cloud_location:
            client_kwargs["location"] = request.google_cloud_location

    client = genai.Client(**client_kwargs)
    response = client.models.generate_content(
        model=request.model,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    text_notes: list[str] = []
    saved_image = False
    for part in response.parts:
        if getattr(part, "text", None):
            text_notes.append(part.text)
            continue

        image = part.as_image() if hasattr(part, "as_image") else None
        if image is not None and not saved_image:
            image.save(image_path)
            saved_image = True

    if not saved_image:
        raise RuntimeError("Gemini returned no image part. Check model access, prompt safety, and quota.")

    prompt_path.write_text(request.prompt, encoding="utf-8")
    notes_path.write_text("\n\n".join(text_notes).strip(), encoding="utf-8")

    return ImageGenerationResult(
        image_path=image_path,
        prompt_path=prompt_path,
        notes_path=notes_path,
        model=request.model,
        text_notes="\n\n".join(text_notes).strip(),
    )
