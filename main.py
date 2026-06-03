"""Entrypoint and local runner for the facade designer agent."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from scripts.agent import build_agent
from scripts.config import DEFAULT_CONFIG_PATH, load_config


def _existing_image(path: str) -> Path:
    image_path = Path(path).expanduser().resolve()
    if not image_path.exists():
        raise argparse.ArgumentTypeError(f"Image does not exist: {image_path}")
    if not image_path.is_file():
        raise argparse.ArgumentTypeError(f"Path is not a file: {image_path}")
    return image_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a new facade design from a building image.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to the central YAML config.")
    parser.add_argument("--building", required=True, type=_existing_image, help="Existing building image.")
    parser.add_argument("--prompt", required=True, help="Description of the desired facade change.")
    parser.add_argument("--inspiration", type=_existing_image, help="Optional inspiration/theme image.")
    parser.add_argument("--output-dir", help="Override output directory from config.")
    parser.add_argument("--aspect-ratio", help="Override output aspect ratio from config.")
    parser.add_argument("--image-size", choices=["1K", "2K", "4K"], help="Override output image size from config.")
    parser.add_argument("--text-model", help="Override text model from config.")
    parser.add_argument("--image-model", help="Override image model from config.")
    parser.add_argument(
        "--image-search-grounding",
        action="store_true",
        help="Enable image-model Google Search grounding for this run.",
    )
    return parser.parse_args()


async def run_pipeline(args: argparse.Namespace) -> dict[str, str]:
    config = load_config(args.config)
    generation_config = config.generation
    if args.output_dir:
        generation_config = generation_config.with_updates(output_dir=Path(args.output_dir))
    if args.aspect_ratio:
        generation_config = generation_config.with_updates(aspect_ratio=args.aspect_ratio)
    if args.image_size:
        generation_config = generation_config.with_updates(image_size=args.image_size)
    if args.image_search_grounding:
        generation_config = generation_config.with_updates(image_search_grounding=True)

    model_config = config.models
    if args.image_model:
        model_config = model_config.with_updates(image=args.image_model)
    if args.text_model:
        model_config = model_config.with_updates(text=args.text_model)

    run_config = config.with_updates(
        models=model_config,
        generation=generation_config,
    )

    session_id = f"session-{uuid4().hex}"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=run_config.app.name,
        user_id=run_config.app.user_id,
        session_id=session_id,
        state={
            "building_image_path": str(args.building),
            "inspiration_image_path": str(args.inspiration) if args.inspiration else "",
            "user_prompt": args.prompt,
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
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text or final_text

    final_session = await session_service.get_session(
        app_name=run_config.app.name,
        user_id=run_config.app.user_id,
        session_id=session_id,
    )
    state = final_session.state
    return {
        "final_text": final_text,
        "generated_image_path": state.get("generated_image_path", ""),
        "prompt_path": state.get("prompt_path", ""),
        "notes_path": state.get("notes_path", ""),
        "model": state.get("image_generation_model", run_config.models.image),
    }


def main() -> None:
    args = parse_args()
    result = asyncio.run(run_pipeline(args))
    print(result["final_text"] or "Facade design workflow finished.")
    if result["generated_image_path"]:
        print(f"Generated image: {result['generated_image_path']}")
    if result["prompt_path"]:
        print(f"Prompt file: {result['prompt_path']}")
    if result["notes_path"]:
        print(f"Notes file: {result['notes_path']}")


if __name__ == "__main__":
    main()
