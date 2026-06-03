"""Tools for facade implementation planning agents."""

from __future__ import annotations

from pathlib import Path
import re
import textwrap

from google.adk.tools.tool_context import ToolContext
from PIL import Image, ImageDraw, ImageFont


DEFAULT_ROADMAP_PHASES = [
    "Discovery",
    "Feasibility",
    "Design development",
    "Approvals",
    "Procurement",
    "Construction",
    "Quality control",
    "Handover",
]


def _clean_label(value: str, *, limit: int = 80) -> str:
    label = " ".join(str(value).strip().split())
    label = label.replace("&", "and")
    label = re.sub(r'["<>|`]', "", label)
    return label[:limit] or "Project phase"


def _clean_duration(value: str) -> str:
    duration = " ".join(str(value).strip().split())
    duration = duration.replace("&", "and")
    duration = re.sub(r'["<>|`]', "", duration)
    return duration[:64] or "to confirm"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    width: int,
    line_gap: int = 6,
) -> int:
    x, y = xy
    avg_char_width = max(1, int(draw.textlength("abcdefghijklmnopqrstuvwxyz", font=font) / 26))
    wrap_width = max(8, width // avg_char_width)
    lines = textwrap.wrap(text, width=wrap_width) or [text]
    for line in lines[:3]:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += bbox[3] - bbox[1] + line_gap
    return y


def _load_thumbnail(path_value: str, size: tuple[int, int]) -> Image.Image | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        image = Image.open(path).convert("RGB")
    except OSError:
        return None
    image.thumbnail(size)
    thumb = Image.new("RGB", size, "#f3f5f7")
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    thumb.paste(image, (x, y))
    return thumb


def create_roadmap_image(
    project_title: str,
    phases: list[str],
    estimated_durations: list[str],
    tool_context: ToolContext,
) -> dict[str, str]:
    """Create a designed PNG roadmap from ordered facade phases and project-specific durations."""
    generated_image_path = Path(str(tool_context.state.get("generated_image_path", "")))
    output_dir = generated_image_path.parent if generated_image_path.name else Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_phases = [_clean_label(phase, limit=64) for phase in phases if str(phase).strip()]
    if not clean_phases:
        clean_phases = DEFAULT_ROADMAP_PHASES
    durations = [_clean_duration(duration) for duration in estimated_durations if str(duration).strip()]

    width = 1200
    card_width = 500
    card_height = 180
    gap = 48
    columns = 2
    rows = (len(clean_phases) + columns - 1) // columns
    header_height = 260
    height = header_height + rows * card_height + max(0, rows - 1) * 46 + 110

    image = Image.new("RGB", (width, height), "#0b1020")
    draw = ImageDraw.Draw(image)

    title_font = _font(44, bold=True)
    subtitle_font = _font(22)
    card_title_font = _font(25, bold=True)
    card_body_font = _font(19)
    badge_font = _font(20, bold=True)

    for y in range(height):
        blend = y / max(1, height - 1)
        r = int(11 + blend * 14)
        g = int(16 + blend * 16)
        b = int(32 + blend * 32)
        draw.line((0, y, width, y), fill=(r, g, b))

    grid_color = "#18243f"
    for x in range(0, width, 80):
        draw.line((x, 0, x, height), fill=grid_color, width=1)
    for y in range(0, height, 80):
        draw.line((0, y, width, y), fill=grid_color, width=1)

    draw.rectangle((0, 0, width, header_height), fill="#111827")
    draw.rectangle((0, header_height - 6, width, header_height), fill="#27e0ff")
    title = _clean_label(project_title or "Facade transformation roadmap", limit=90)
    draw.text((58, 54), title, font=title_font, fill="#f8fbff")
    draw.text(
        (60, 118),
        "AI-assisted delivery sequence with project-specific duration ranges",
        font=subtitle_font,
        fill="#a9b8d8",
    )
    draw.rounded_rectangle(
        (60, 166, 390, 208),
        radius=16,
        fill="#13233d",
        outline="#27e0ff",
        width=2,
    )
    draw.text(
        (82, 176),
        "Facade Transformation Roadmap",
        font=_font(20, bold=True),
        fill="#82f7ff",
    )

    thumbnail = _load_thumbnail(str(generated_image_path), (280, 160))
    if thumbnail:
        thumb_x = width - 340
        thumb_y = 48
        draw.rounded_rectangle(
            (thumb_x - 10, thumb_y - 10, thumb_x + 290, thumb_y + 170),
            radius=22,
            fill="#18243f",
            outline="#7c3cff",
            width=3,
        )
        image.paste(thumbnail, (thumb_x, thumb_y))
        draw.rounded_rectangle(
            (thumb_x, thumb_y, thumb_x + 280, thumb_y + 160),
            radius=16,
            outline="#27e0ff",
            width=2,
        )

    start_x = 60
    start_y = header_height + 50
    arrow_color = "#27e0ff"
    for index, phase in enumerate(clean_phases, start=1):
        row = (index - 1) // columns
        column = (index - 1) % columns
        x = start_x + column * (card_width + gap)
        y = start_y + row * (card_height + 46)

        duration = durations[index - 1] if index <= len(durations) else "to confirm"
        accent = "#27e0ff" if index % 2 else "#a78bfa"
        glow = "#123252" if index % 2 else "#2b1f57"
        draw.rounded_rectangle(
            (x - 8, y - 8, x + card_width + 8, y + card_height + 8),
            radius=28,
            fill=glow,
        )
        draw.rounded_rectangle(
            (x, y, x + card_width, y + card_height),
            radius=24,
            fill="#101a30",
            outline=accent,
            width=2,
        )
        draw.rounded_rectangle((x, y, x + 10, y + card_height), radius=8, fill=accent)
        draw.ellipse((x + 28, y + 26, x + 78, y + 76), fill=accent)
        step_text = str(index)
        step_bbox = draw.textbbox((0, 0), step_text, font=badge_font)
        draw.text(
            (
                x + 53 - (step_bbox[2] - step_bbox[0]) / 2,
                y + 51 - (step_bbox[3] - step_bbox[1]) / 2 - 2,
            ),
            step_text,
            font=badge_font,
            fill="#08111f",
        )
        _draw_wrapped(
            draw,
            (x + 98, y + 28),
            phase,
            card_title_font,
            "#f8fbff",
            card_width - 128,
        )
        draw.rounded_rectangle(
            (x + 28, y + card_height - 68, x + card_width - 28, y + card_height - 18),
            radius=16,
            fill="#162642",
            outline="#314466",
            width=1,
        )
        _draw_wrapped(
            draw,
            (x + 48, y + card_height - 58),
            f"Est. {duration}",
            font=card_body_font,
            fill="#82f7ff",
            width=card_width - 96,
            line_gap=2,
        )

        if index < len(clean_phases) and column < columns - 1:
            arrow_y = y + card_height // 2
            arrow_x1 = x + card_width + 14
            arrow_x2 = x + card_width + gap - 14
            draw.line((arrow_x1, arrow_y, arrow_x2, arrow_y), fill=arrow_color, width=4)
            draw.polygon(
                [
                    (arrow_x2, arrow_y),
                    (arrow_x2 - 12, arrow_y - 8),
                    (arrow_x2 - 12, arrow_y + 8),
                ],
                fill=arrow_color,
            )

    roadmap_image_path = output_dir / f"{generated_image_path.stem or 'facade-design'}-roadmap.png"
    image.save(roadmap_image_path)
    tool_context.state["roadmap_image_path"] = str(roadmap_image_path)
    return {
        "roadmap_image_path": str(roadmap_image_path),
        "image_format": "png",
    }
