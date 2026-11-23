import json
import sys

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo


class TextSourceError(ValueError):
    def __init__(self, message, code):
        self.code = code
        super().__init__(message)


class TextEngineError(RuntimeError):
    code = "dependency"


def text_geometry(item):
    options = item if isinstance(item, dict) else {"text": item}
    text = options["text"]
    family = options.get("font_family", "Noto Sans")
    size = float(options.get("font_px", 15))
    if not 1 <= size <= 256:
        raise ValueError("Cỡ chữ phải trong khoảng 1..256 px")

    surface = cairo.RecordingSurface(
        cairo.CONTENT_COLOR_ALPHA,
        None,
    )
    context = cairo.Context(surface)
    layout = PangoCairo.create_layout(context)

    font = Pango.FontDescription()
    # Policy: requested families must be packaged (generic CSS family names use
    # an explicit bundled Noto mapping). Glyph fallback is local Pango fallback.
    available = {item.get_name().casefold(): item.get_name()
                 for item in layout.get_context().list_families()}
    if not available:
        raise TextEngineError("Pango không tìm được font đã đóng gói.")
    generic = {"sans-serif": "Noto Sans", "serif": "Noto Serif", "monospace": "Noto Sans Mono"}
    requested = [name.strip() for name in family.split(",")]
    resolved = []
    for name in requested:
        name = generic.get(name.casefold(), name)
        if name.casefold() not in available:
            if name in {"Noto Sans", "Noto Serif", "Noto Sans Mono"}:
                raise TextEngineError(f"Thiếu font bắt buộc trong image: {name}.")
            raise TextSourceError(f"Font chưa được đóng gói: {name}. Không tải font ngoài.", "font")
        resolved.append(available[name.casefold()])
    font.set_family(", ".join(resolved))
    weight = options.get("font_weight", "normal")
    font.set_weight(Pango.Weight.BOLD if weight == "bold" else
                    Pango.Weight.NORMAL if weight == "normal" else int(weight))
    font.set_style({"normal": Pango.Style.NORMAL, "italic": Pango.Style.ITALIC,
                    "oblique": Pango.Style.OBLIQUE}[options.get("font_style", "normal")])
    font.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(font)
    layout.set_text(text, -1)
    serialized = layout.serialize(Pango.LayoutSerializeFlags.OUTPUT)
    layout_data = json.loads(serialized.get_data().decode("utf-8"))

    fonts_used = set()

    for line in layout_data["output"]["lines"]:
        for run in line["runs"]:
            description = run["font"]["description"]
            actual_font = Pango.FontDescription.from_string(description)
            fonts_used.add(actual_font.get_family())
    # Empty/whitespace-only labels have no shaped runs. Report the font Pango
    # actually resolves for this layout, rather than rejecting a valid blank node.
    if not fonts_used:
        resolved_font = layout.get_context().load_font(font)
        if resolved_font is None:
            raise TextEngineError("Pango không tìm được font cho nhãn rỗng")
        fonts_used.add(resolved_font.describe().get_family())
    unknown_glyphs = layout.get_unknown_glyphs_count()

    if unknown_glyphs:
        raise TextSourceError(
            f"Nhãn có {unknown_glyphs} glyph không được font hỗ trợ: {text!r}", "glyph"
        )

    ink, logical = layout.get_extents()

    context.move_to(0, 0)
    PangoCairo.layout_path(context, layout)

    # Hộp hình học của chính đường nét chữ được xuất bên dưới.
    x1, y1, x2, y2 = context.path_extents()

    commands = []
    for operation, coordinates in context.copy_path():
        values = " ".join(repr(value) for value in coordinates)

        if operation == cairo.PATH_MOVE_TO:
            commands.append(f"M {values}")
        elif operation == cairo.PATH_LINE_TO:
            commands.append(f"L {values}")
        elif operation == cairo.PATH_CURVE_TO:
            commands.append(f"C {values}")
        elif operation == cairo.PATH_CLOSE_PATH:
            commands.append("Z")

    return {
        "label": text,
        "fonts_used": sorted(fonts_used),
        "font_px": size,
        "font_weight": options.get("font_weight", "normal"),
        "font_style": options.get("font_style", "normal"),
        "path": " ".join(commands),
        "ink_box": [
            ink.x / Pango.SCALE,
            ink.y / Pango.SCALE,
            ink.width / Pango.SCALE,
            ink.height / Pango.SCALE,
        ],
        "path_box": [x1, y1, x2 - x1, y2 - y1],
        "logical_box": [
            logical.x / Pango.SCALE,
            logical.y / Pango.SCALE,
            logical.width / Pango.SCALE,
            logical.height / Pango.SCALE,
        ],
        "text_received": layout.get_text(),
        "versions": {
            "pango": Pango.version_string(),
            "cairo": cairo.cairo_version_string(),
            "pycairo": cairo.version,
        },
    }


if __name__ == "__main__":
    try:
        labels = json.load(sys.stdin)
        print(json.dumps([text_geometry(label) for label in labels], ensure_ascii=False, indent=2))
    except TextSourceError as error:
        print(json.dumps({"kind": "source", "code": error.code, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"kind": "engine", "code": getattr(error, "code", "engine"), "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
