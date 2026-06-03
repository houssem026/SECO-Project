"""Streamlit front end for the facade designer agent."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile

import streamlit as st

from scripts.config import DEFAULT_CONFIG_PATH, load_config
from scripts.pipeline import PipelineInputs, PipelineOverrides, PipelineResult, stream_pipeline


SUPPORTED_IMAGE_TYPES = ["jpg", "jpeg", "png", "webp"]


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .app-title {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.25rem;
        }
        .logo-mark {
            width: 3rem;
            height: 3rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 0.5rem;
            background: #f0f3f7;
            font-size: 1.7rem;
            border: 1px solid #d9dee7;
        }
        .app-title h1 {
            margin: 0;
            padding: 0;
            line-height: 1.05;
        }
        .muted-caption {
            color: #667085;
            font-size: 0.92rem;
            margin-bottom: 1rem;
        }
        .result-path {
            font-size: 0.85rem;
            color: #667085;
            word-break: break-all;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _save_upload(uploaded_file: object, directory: Path, prefix: str) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".png"
    path = directory / f"{prefix}{suffix}"
    path.write_bytes(uploaded_file.getbuffer())
    return path


def _upload_bytes(uploaded_file: object | None) -> bytes | None:
    if uploaded_file is None:
        return None
    return uploaded_file.getvalue()


def _render_uploaded_images(building_file: object | None, inspiration_file: object | None) -> None:
    st.markdown("#### Image Preview")
    cols = st.columns(2)
    building_bytes = _upload_bytes(building_file)
    inspiration_bytes = _upload_bytes(inspiration_file)
    with cols[0]:
        if building_bytes:
            st.image(building_bytes, caption="Building image", use_container_width=True)
        else:
            st.info("Upload the existing building image.")
    with cols[1]:
        if inspiration_bytes:
            st.image(inspiration_bytes, caption="Inspiration image", use_container_width=True)
        else:
            st.info("Inspiration is optional.")


def _resolve_generated_image(result: PipelineResult, output_dir: str) -> Path | None:
    candidates: list[Path] = []
    if result.generated_image_path:
        image_path = Path(result.generated_image_path).expanduser()
        candidates.append(image_path)
        if not image_path.is_absolute():
            candidates.append(Path.cwd() / image_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    if output_path.exists():
        generated_images = sorted(
            output_path.glob("facade-design-*.png"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if generated_images:
            return generated_images[0].resolve()

    return None


def _read_optional_text(path_value: str) -> str:
    if not path_value:
        return ""

    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


async def _run_and_render(
    inputs: PipelineInputs,
    overrides: PipelineOverrides,
) -> PipelineResult | None:
    trace_expander = st.expander("Agent reasoning trace", expanded=True)
    trace_slots: dict[str, object] = {}
    trace_text: dict[str, list[str]] = {}
    result: PipelineResult | None = None

    with trace_expander:
        st.caption("Live agent outputs and handoffs. This is the visible trace, not hidden chain-of-thought.")
        status = st.status("Running facade design pipeline...", expanded=True)

    try:
        async for update in stream_pipeline(inputs, overrides):
            if update.text and not update.result:
                trace_text.setdefault(update.author, []).append(update.text)
                with trace_expander:
                    if update.author not in trace_slots:
                        with st.expander(update.author, expanded=True):
                            trace_slots[update.author] = st.empty()
                    trace_slots[update.author].markdown(
                        "\n\n---\n\n".join(trace_text[update.author])
                    )
            if update.result:
                result = update.result
    except Exception as exc:
        status.update(label="Pipeline failed", state="error", expanded=True)
        st.error(str(exc))
        return None

    status.update(label="Pipeline complete", state="complete", expanded=False)
    return result


def main() -> None:
    st.set_page_config(page_title="Facade Designer Agent", page_icon="🏛️", layout="wide")
    _inject_styles()
    st.markdown(
        """
        <div class="app-title">
            <div class="logo-mark">🏛️</div>
            <div>
                <h1>Facade Designer Agent</h1>
                <div class="muted-caption">
                    Upload a building, add a redesign brief, and watch the agent pipeline shape a new facade concept.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    config = load_config(DEFAULT_CONFIG_PATH)

    with st.sidebar:
        st.header("⚙️ Run Settings")
        with st.expander("Generation", expanded=True):
            output_dir = st.text_input("Output directory", value=str(config.generation.output_dir))
            aspect_ratio = st.text_input("Aspect ratio", value=config.generation.aspect_ratio)
            image_size = st.selectbox(
                "Image size",
                ["1K", "2K", "4K"],
                index=["1K", "2K", "4K"].index(config.generation.image_size)
                if config.generation.image_size in {"1K", "2K", "4K"}
                else 1,
            )
        with st.expander("Models", expanded=False):
            text_model = st.text_input("Text model", value=config.models.text)
            image_model = st.text_input("Image model", value=config.models.image)

    input_col, output_col = st.columns([0.95, 1.25], gap="large")

    with input_col:
        with st.container(border=True):
            building_file = st.file_uploader(
                "Building image",
                type=SUPPORTED_IMAGE_TYPES,
                help="Upload the existing building facade image.",
            )
            inspiration_file = st.file_uploader(
                "Inspiration image (optional)",
                type=SUPPORTED_IMAGE_TYPES,
                help="Optional visual reference for style, material, rhythm, or mood.",
            )
            brief = st.text_area(
                "Design brief",
                value="",
                height=220,
                placeholder="Describe the facade change you want...",
            )
            run_button = st.button(
                "Generate redesign",
                type="primary",
                use_container_width=True,
                disabled=not building_file or not brief.strip(),
            )

        with st.container(border=True):
            _render_uploaded_images(building_file, inspiration_file)

    with output_col:
        result_box = st.container()
        trace_box = st.container()

    if not run_button:
        with output_col:
            with result_box:
                st.info("Generated facade image will appear here after the pipeline finishes.")
        return

    with tempfile.TemporaryDirectory(prefix="facade-designer-") as tmp_dir:
        upload_dir = Path(tmp_dir)
        building_path = _save_upload(building_file, upload_dir, "building")
        inspiration_path = (
            _save_upload(inspiration_file, upload_dir, "inspiration")
            if inspiration_file
            else None
        )

        with output_col:
            with trace_box:
                result = asyncio.run(
                    _run_and_render(
                        PipelineInputs(
                            building_image_path=building_path,
                            inspiration_image_path=inspiration_path,
                            user_prompt=brief,
                        ),
                        PipelineOverrides(
                            output_dir=Path(output_dir),
                            aspect_ratio=aspect_ratio,
                            image_size=image_size,
                            text_model=text_model,
                            image_model=image_model,
                        ),
                    )
                )

    with output_col:
        if not result:
            return

        with result_box:
            st.markdown("#### Generated Design")
            generated_image = _resolve_generated_image(result, output_dir)
            if generated_image:
                st.image(str(generated_image), use_container_width=True)
                st.markdown(
                    f'<div class="result-path">{generated_image}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning("The pipeline finished, but no generated image file was found.")
                with st.expander("Path diagnostics", expanded=False):
                    st.write("Returned image path:", result.generated_image_path or "(empty)")
                    st.write("Configured output directory:", output_dir)

        with st.expander("Roadmap, prompt and notes", expanded=False):
            implementation_plan = result.implementation_plan or result.final_text
            if implementation_plan:
                st.markdown("**Implementation roadmap**")
                st.markdown(implementation_plan)
            if result.roadmap_chart_path:
                st.markdown("**Roadmap chart**")
                st.code(result.roadmap_chart_path)

            prompt_text = _read_optional_text(result.prompt_path)
            if prompt_text:
                st.markdown("**Image generation prompt**")
                st.code(prompt_text)

            notes = _read_optional_text(result.notes_path)
            if notes:
                st.markdown("**Model notes**")
                st.markdown(notes)


if __name__ == "__main__":
    main()
