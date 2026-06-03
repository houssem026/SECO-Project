"""Entrypoint and local runner for the facade designer agent."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scripts.config import DEFAULT_CONFIG_PATH
from scripts.pipeline import PipelineInputs, PipelineOverrides, run_pipeline as run_agent_pipeline


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
    result = await run_agent_pipeline(
        PipelineInputs(
            building_image_path=args.building,
            inspiration_image_path=args.inspiration,
            user_prompt=args.prompt,
        ),
        PipelineOverrides(
            config_path=args.config,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            aspect_ratio=args.aspect_ratio,
            image_size=args.image_size,
            text_model=args.text_model,
            image_model=args.image_model,
            image_search_grounding=args.image_search_grounding,
        ),
    )
    return {
        "final_text": result.final_text,
        "generated_image_path": result.generated_image_path,
        "prompt_path": result.prompt_path,
        "notes_path": result.notes_path,
        "model": result.model,
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
