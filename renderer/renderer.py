"""Offline Mermaid renderer. Public API: render(source, scale=2, timeout=30, *, layout="dagre").

The Node/Pango backend and librsvg run in fresh process groups under one
monotonic deadline. No global output directory, persistent worker, or server.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
import re
from pathlib import Path
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
import zlib

if __package__:
    from .runtime_version import RENDERER_VERSION, renderer_version
else:
    from runtime_version import RENDERER_VERSION, renderer_version


MAX_SOURCE_CHARS = 50_000
MAX_SOURCE_BYTES = 256 * 1024
MAX_SCALE = 16
MAX_TIMEOUT = 300
MAX_SVG_BYTES = 32 * 1024 * 1024
MAX_LAYOUT_BYTES = 8 * 1024 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 96 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024
MAX_RASTER_DIMENSION = 16_384
MAX_RASTER_PIXELS = 100_000_000
_SOURCE_ROOT = Path(__file__).resolve().parent
# Source bundle groups backend files; the installed CLI retains its flat /app
# paths so existing engine consumers and fault-injection interfaces still work.
_BACKEND_ROOT = _SOURCE_ROOT / "backend" if (_SOURCE_ROOT / "backend").is_dir() else _SOURCE_ROOT
_BACKEND = _BACKEND_ROOT / "draw-probe.mjs"


@dataclass
class Rendered:
    svg: str
    png: bytes
    layout: dict


class DiagramSyntaxError(ValueError):
    kind = "syntax"
    category = "source"
    code = "syntax"

    def __init__(self, message: str, line_number: int):
        self.line_number = line_number
        super().__init__(f"Lỗi cú pháp dòng {line_number}: {message}")


class RendererError(RuntimeError):
    kind = "engine"
    category = "engine"

    def __init__(self, message: str, code: str = "engine"):
        self.code = code
        super().__init__(message)


class DiagramSourceError(RendererError):
    """Valid Python call, but the diagram must change to satisfy renderer policy.

    Subclass RendererError to preserve existing broad handlers. New consumers
    should catch this subclass first, or inspect category on all public errors.
    """
    kind = "source"
    category = "source"

    def __init__(self, message: str, code: str = "source_policy", line_number=None):
        self.line_number = line_number
        super().__init__(message, code)


_SOURCE_ERROR_CODES = {"source_policy", "source_structure", "font", "glyph",
                       "unsupported", "input", "limit", "invalid_source"}


class _Deadline:
    def __init__(self, timeout):
        self.end = time.monotonic() + timeout

    def remaining(self):
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise RendererError("Render vượt timeout toàn lượt; đã dừng cây tiến trình.", "timeout")
        return remaining


def _positive(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RendererError(f"{name} phải là số hữu hạn trong khoảng (0, {maximum}].", "invalid_argument")
    try:
        converted = float(value)
    except (ValueError, OverflowError) as error:
        raise RendererError(f"{name} không hợp lệ.", "invalid_argument") from error
    if not math.isfinite(converted) or not 0 < converted <= maximum:
        raise RendererError(f"{name} phải là số hữu hạn trong khoảng (0, {maximum}].", "invalid_argument")
    return converted


def _source_bytes(source):
    if not isinstance(source, str):
        raise RendererError("source phải là str UTF-8.", "invalid_argument")
    if len(source) > MAX_SOURCE_CHARS:
        raise DiagramSourceError(f"Source vượt giới hạn {MAX_SOURCE_CHARS} ký tự.", "limit")
    try:
        encoded = source.encode("utf-8")
    except UnicodeError as error:
        raise DiagramSourceError("Source chứa Unicode không mã hóa được thành UTF-8.", "invalid_argument") from error
    if len(encoded) > MAX_SOURCE_BYTES:
        raise DiagramSourceError(f"Source vượt giới hạn {MAX_SOURCE_BYTES} byte UTF-8.", "limit")
    if "\0" in source:
        raise DiagramSourceError("Source chứa ký tự NUL không được hỗ trợ.", "invalid_argument")
    if not source.strip():
        raise DiagramSyntaxError("Source Mermaid rỗng.", 1)
    return encoded


def _read_limited(path, limit):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise RendererError(f"Đầu ra không phải file thường: {path.name}", "output")
        if info.st_size > limit:
            raise RendererError(f"{path.name} vượt giới hạn {limit} byte.", "limit")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise RendererError(f"Không đọc được đầu ra {path.name}: {error}", "output") from error
    if len(data) > limit:
        raise RendererError(f"{path.name} vượt giới hạn {limit} byte.", "limit")
    return data


def _kill_group(process):
    # The renderer's fixed children never detach or create another session.
    # SIGKILL avoids a second, per-stage grace timeout extending the deadline.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
    # When this caller is PID 1 (or an existing subreaper), killed descendants
    # may be adopted here. Reap only this render's group; never consume another
    # concurrent call's child or change process-wide subreaper/signal settings.
    while True:
        try:
            os.waitpid(-process.pid, 0)
        except ChildProcessError:
            break
        except InterruptedError:
            continue


def _run(command, scratch, stage, deadline, watched=()):
    stdout_path = scratch / f"{stage.replace('/', '-')}.stdout"
    stderr_path = scratch / f"{stage.replace('/', '-')}.stderr"
    # Do not inherit NODE_OPTIONS, PYTHONPATH, LD_PRELOAD, FONTCONFIG_* or
    # locale/timezone settings from the caller. Only packaged resources apply.
    env = {"PATH":"/usr/local/bin:/usr/bin:/bin", "LANG":"C.UTF-8", "LC_ALL":"C.UTF-8",
           "TZ":"UTC", "PYTHONHASHSEED":"0", "PYTHONNOUSERSITE":"1", "PYTHONDONTWRITEBYTECODE":"1",
           "FONTCONFIG_FILE":"/etc/fonts/fonts.conf", "FONTCONFIG_PATH":"/etc/fonts", "HOME":str(scratch)}
    env["AIZ_PYTHON_EXECUTABLE"] = sys.executable
    env["AIZ_RENDERER_VERSION"] = renderer_version(_BACKEND.parent)
    # Font/cache/tool temporary files belong to this call as well.
    env["TMPDIR"] = str(scratch)
    env["XDG_CACHE_HOME"] = str(scratch / "cache")
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        deadline.remaining()
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       cwd=scratch, env=env, start_new_session=True)
        except OSError as error:
            raise RendererError(f"Không chạy được dependency {stage}: {error}", "dependency") from error
        try:
            while True:
                remaining = deadline.remaining()
                for stream in (out, err):
                    if os.fstat(stream.fileno()).st_size > MAX_LOG_BYTES:
                        raise RendererError(f"Log {stage} vượt giới hạn kích thước.", "limit")
                for path, limit in watched:
                    if path.exists() and path.stat().st_size > limit:
                        raise RendererError(f"{path.name} vượt giới hạn kích thước đầu ra.", "limit")
                try:
                    returncode = process.wait(timeout=min(0.05, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            deadline.remaining()
        finally:
            # Also kill descendants left after an abnormal or successful leader
            # exit, and on exceptions/KeyboardInterrupt in the Python caller.
            _kill_group(process)
    stdout = _read_limited(stdout_path, MAX_LOG_BYTES).decode("utf-8", "replace")
    stderr = _read_limited(stderr_path, MAX_LOG_BYTES).decode("utf-8", "replace")
    if returncode:
        try:
            detail = json.loads(stderr)
        except (ValueError, TypeError):
            detail = None
        if isinstance(detail, dict) and stage == "Node/Pango":
            kind = detail.get("kind")
            line = detail.get("line")
            if kind == "syntax":
                if type(line) is int and line >= 1:
                    raise DiagramSyntaxError(str(detail.get("message", "Source Mermaid sai cú pháp.")), line)
                raise RendererError("Backend trả số dòng lỗi không hợp lệ.", "output")
            if kind == "source":
                code = detail.get("code")
                if not isinstance(code, str) or code not in _SOURCE_ERROR_CODES or (line is not None and (type(line) is not int or line < 1)):
                    raise RendererError("Backend trả phân loại lỗi source không hợp lệ.", "output")
                raise DiagramSourceError(str(detail.get("message", "Source không được hỗ trợ.")), code, line)
        message = str(detail.get("message")) if isinstance(detail, dict) else stderr.strip() or stdout.strip()
        code = str(detail.get("code", "engine")) if isinstance(detail, dict) else "engine"
        # Missing imports can fail before the backend's JSON handler starts.
        # Never override a structured source/policy classification using its text.
        if detail is None and any(token in message for token in ("ERR_MODULE_NOT_FOUND", "Cannot find", "ModuleNotFoundError", "ImportError", "ENOENT")):
            code = "dependency"
        raise RendererError(f"{stage} thất bại (exit {returncode}): {message or 'không có chẩn đoán'}", code)


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _layout(data):
    try:
        result = json.loads(data, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeError) as error:
        raise RendererError("Layout JSON không hợp lệ.", "output") from error
    required = {"width", "height", "nodes", "edges", "subgraphs", "font_px", "font_family_used"}
    if not isinstance(result, dict) or set(result) != required:
        raise RendererError("Layout không đúng schema Rendered.", "output")
    if not all(_number(result[k]) and result[k] > 0 for k in ("width", "height", "font_px")):
        raise RendererError("Kích thước/font trong layout không hợp lệ.", "output")
    if not isinstance(result["font_family_used"], str) or not result["font_family_used"]:
        raise RendererError("Layout thiếu font thực tế.", "output")
    def box(value):
        return isinstance(value, list) and len(value) == 4 and all(_number(n) for n in value) and value[2] >= 0 and value[3] >= 0
    for key in ("nodes", "edges", "subgraphs"):
        if not isinstance(result[key], list):
            raise RendererError(f"Layout {key} cần array.", "output")
    ids = set()
    for entity in result["nodes"] + result["subgraphs"]:
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), str) or entity["id"] in ids or not box(entity.get("box")) or not box(entity.get("label_box")):
            raise RendererError("Node/subgraph layout không hợp lệ.", "output")
        ids.add(entity["id"])
    for group in result["subgraphs"]:
        if not isinstance(group.get("members"), list) or any(not isinstance(id, str) or id not in ids for id in group["members"]):
            raise RendererError("Subgraph members không hợp lệ.", "output")
    ordinals = []
    for edge in result["edges"]:
        if not isinstance(edge, dict) or not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str) or edge["source"] not in ids or edge["target"] not in ids or type(edge.get("ordinal")) is not int or not box(edge.get("label_box")):
            raise RendererError("Edge layout không hợp lệ.", "output")
        points = edge.get("points")
        if not isinstance(points, list) or len(points) < 2 or any(not isinstance(p, list) or len(p) != 2 or not all(_number(n) for n in p) for p in points):
            raise RendererError("Edge points không hợp lệ.", "output")
        radii = edge.get("corner_radii")
        if not isinstance(radii,list) or len(radii)!=len(points) or any(not _number(r) or r!=0 for r in radii):
            raise RendererError("Edge corner_radii không hợp lệ.", "output")
        ordinals.append(edge["ordinal"])
    if sorted(ordinals) != list(range(len(ordinals))):
        raise RendererError("Ordinal edge không liên tục/duy nhất.", "output")
    return result


def _svg(data, layout, expected_version=None):
    try:
        text = data.decode("utf-8")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("DTD/entity declaration")
        root = ET.fromstring(text)
        if expected_version is not None and root.attrib.get("data-renderer-version") != expected_version:
            raise ValueError("renderer identity mismatch")
        viewbox = list(map(float, root.attrib["viewBox"].split()))
        if root.tag != "{http://www.w3.org/2000/svg}svg" or viewbox != [0, 0, layout["width"], layout["height"]]:
            raise ValueError("viewBox/layout mismatch")
        allowed_tags={"svg","g","defs","marker","path","rect","polygon","polyline","circle","ellipse","line"}
        allowed_attrs={"id","viewBox","width","height","font-family","font-size","font-weight","font-style",
                       "x","y","cx","cy","r","rx","ry","d","points","fill","stroke","stroke-width","stroke-dasharray",
                       "marker-start","marker-end","transform","x1","y1","x2","y2","markerWidth","markerHeight",
                       "markerUnits","orient","overflow","refX","refY","visibility","stroke-linecap"}
        ids=set(); references=[]
        for element in root.iter():
            if element.tag not in {"{http://www.w3.org/2000/svg}"+tag for tag in allowed_tags}:
                raise ValueError("unsupported/active SVG element")
            if "id" in element.attrib:
                if element.attrib["id"] in ids:raise ValueError("duplicate SVG ID")
                ids.add(element.attrib["id"])
            for key,value in element.attrib.items():
                if key not in allowed_attrs and not key.startswith("data-"):
                    raise ValueError("unsupported/active SVG attribute")
                if key == "stroke-linecap" and value not in {"butt", "round", "square"}:
                    raise ValueError("invalid SVG stroke-linecap")
                if re.search(r"url\s*\(",value,re.I):
                    match=re.fullmatch(r"url\(#([A-Za-z0-9_-]+)\)",value)
                    if key not in ("marker-start","marker-end") or not match:
                        raise ValueError("external/invalid SVG reference")
                    references.append(match[1])
        if any(ref not in ids for ref in references):raise ValueError("unresolved marker reference")
        lines=[e for e in root.iter() if "data-ordinal" in e.attrib]
        if len(lines)!=len(layout["edges"]): raise ValueError("SVG edge count mismatch")
        seen=set()
        for line in lines:
            ordinal=int(line.attrib["data-ordinal"])
            if ordinal in seen or ordinal<0 or ordinal>=len(layout["edges"]): raise ValueError("SVG edge ordinal mismatch")
            seen.add(ordinal)
            edge=next(e for e in layout["edges"] if e["ordinal"]==ordinal)
            if line.tag!="{http://www.w3.org/2000/svg}path" or "transform" in line.attrib or "points" in line.attrib:
                raise ValueError("invalid edge primitive")
            if line.attrib.get("data-source")!=edge["source"] or line.attrib.get("data-target")!=edge["target"]:
                raise ValueError("SVG edge endpoints mismatch")
            if json.loads(line.attrib["data-points"])!=edge["points"] or json.loads(line.attrib["data-corner-radii"])!=edge["corner_radii"]:
                raise ValueError("SVG edge geometry metadata mismatch")
            pts=edge["points"]; expected=["M",*pts[0]]
            for p in pts[1:]:expected.extend(["L",*p])
            # Full token consumption: unknown commands, trailing junk and NaN
            # cannot be hidden by a permissive regex tokenizer.
            tokens=line.attrib["d"].split()
            if len(tokens)!=len(expected):raise ValueError("SVG edge path command mismatch")
            for token,want in zip(tokens,expected):
                if isinstance(want,str):
                    if token!=want:raise ValueError("SVG edge path command mismatch")
                elif not math.isfinite(float(token)) or abs(float(token)-want)>1e-8:
                    raise ValueError("SVG edge path/layout mismatch")
    except (ValueError, KeyError, TypeError, ZeroDivisionError, UnicodeError, ET.ParseError) as error:
        raise RendererError(f"SVG không hợp lệ: {error}", "output") from error
    return text


def _raster_dimensions(layout, scale):
    scaled_width, scaled_height = layout["width"] * scale, layout["height"] * scale
    if not math.isfinite(scaled_width) or not math.isfinite(scaled_height):
        raise RendererError("PNG dimensions vượt giới hạn số hữu hạn.", "limit")
    width = math.ceil(scaled_width)
    height = math.ceil(scaled_height)
    if min(width, height) < 1 or max(width, height) > MAX_RASTER_DIMENSION or width * height > MAX_RASTER_PIXELS:
        raise DiagramSourceError(f"PNG vượt giới hạn raster: {width}×{height}, tối đa {MAX_RASTER_DIMENSION}/chiều và {MAX_RASTER_PIXELS} pixels.", "limit")
    return width, height


def _png(data, expected):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RendererError("PNG thiếu signature.", "output")
    offset = 8
    first = True
    idat = False
    while offset + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + 12 + length
        if end > len(data):
            break
        chunk = memoryview(data)[offset + 8:end - 4]
        crc = zlib.crc32(chunk, zlib.crc32(kind)) & 0xffffffff
        if crc != struct.unpack_from(">I", data, end - 4)[0]:
            raise RendererError("PNG có CRC lỗi.", "output")
        if first:
            if kind != b"IHDR" or length != 13 or struct.unpack_from(">II", chunk) != expected:
                raise RendererError("PNG dimensions không khớp SVG/scale.", "output")
            first = False
        idat = idat or kind == b"IDAT"
        if kind == b"IEND":
            if length == 0 and end == len(data) and idat:
                return
            raise RendererError("PNG có IEND không hợp lệ.", "output")
        offset = end
    raise RendererError("PNG không hoàn chỉnh.", "output")


def render(source: str, scale=2, timeout=30, *, layout="dagre", raw_edges=False, elk_spacing=1) -> Rendered:
    """Return all three outputs; layout selects dagre (default) or experimental elk.

    Timeout covers validation, startup, parsing/layout/shaping, rasterization,
    artifact reads and validation. No paths or subprocesses escape a call.
    raw_edges is a compatibility argument; both engines retain their routes.
    """
    timeout = _positive(timeout, "timeout", MAX_TIMEOUT)
    deadline = _Deadline(timeout)
    scale = _positive(scale, "scale", MAX_SCALE)
    if layout not in ("dagre", "elk", "auto"):
        raise RendererError("layout phải là dagre, elk hoặc auto.", "invalid_argument")
    if type(raw_edges) is not bool:
        raise RendererError("raw_edges phải là bool.", "invalid_argument")
    elk_spacing = _positive(elk_spacing, "elk_spacing", 4)
    if layout not in ("elk", "auto") and elk_spacing != 1:
        raise RendererError("elk_spacing chỉ áp dụng cho elk hoặc auto khi chọn ELK.", "invalid_argument")
    encoded = _source_bytes(source)
    node = shutil.which("node")
    raster = shutil.which("rsvg-convert")
    if not node or not raster:
        missing = "node" if not node else "rsvg-convert"
        raise RendererError(f"Thiếu dependency: {missing} trong PATH.", "dependency")
    for name in ("draw-probe.mjs", "text_geometry.py", "subgraph-layout.mjs", "elk-layout.mjs", "theme-source.mjs", "mermaid-model.mjs"):
        if not _BACKEND.with_name(name).is_file():
            raise RendererError(f"Thiếu file renderer dependency: {name}", "dependency")
    try:
        identity = renderer_version(_BACKEND.parent)
    except OSError as error:
        raise RendererError(f"Thiếu manifest/build identity đã ghim: {error}", "dependency") from error
    try:
        with tempfile.TemporaryDirectory(prefix="aiz-render-") as directory:
            scratch = Path(directory)
            deadline.remaining()
            input_path = scratch / "input.mmd"
            input_path.write_bytes(encoded)
            backend = scratch / "backend"
            svg_path = backend / "diagram.svg"
            layout_path = backend / "layout.json"
            _run([node, str(_BACKEND), "--internal", str(input_path), str(backend), layout, "raw", str(elk_spacing)], scratch, "Node/Pango", deadline,
                 [(svg_path, MAX_SVG_BYTES), (layout_path, MAX_LAYOUT_BYTES)])
            svg_data = _read_limited(svg_path, MAX_SVG_BYTES)
            layout_data = _read_limited(layout_path, MAX_LAYOUT_BYTES)
            layout = _layout(layout_data)
            svg = _svg(svg_data, layout, expected_version=identity)
            dimensions = _raster_dimensions(layout, scale)
            deadline.remaining()
            png_path = scratch / "diagram.png"
            _run([raster, f"--zoom={scale}", f"--output={png_path}", str(svg_path)], scratch, "rsvg-convert", deadline,
                 [(png_path, MAX_PNG_BYTES)])
            png = _read_limited(png_path, MAX_PNG_BYTES)
            _png(png, dimensions)
            if len(svg_data) + len(layout_data) + len(png) > MAX_TOTAL_BYTES:
                raise RendererError("Bộ đầu ra vượt giới hạn tổng kích thước.", "limit")
            deadline.remaining()
            result = Rendered(svg=svg, png=png, layout=layout)
        # Include scratch cleanup in the public API deadline as well.
        deadline.remaining()
        return result
    except OSError as error:
        raise RendererError(f"Lỗi scratch/đầu ra renderer: {error}", "output") from error


def _publish(result, destination, deadline):
    """Publish one immutable directory. Never replace another call's output."""
    if destination.exists() or destination.is_symlink():
        raise RendererError(f"Output đã tồn tại, không ghi đè: {destination}", "output_exists")
    if not destination.parent.is_dir():
        raise RendererError(f"Thư mục cha output không tồn tại: {destination.parent}", "output")
    with tempfile.TemporaryDirectory(prefix=".aiz-publish-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "result"
        staged.mkdir()
        for name, data in (("diagram.svg", result.svg.encode("utf-8")), ("diagram.png", result.png),
                           ("layout.json", (json.dumps(result.layout, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))):
            deadline.remaining()
            (staged / name).write_bytes(data)
        deadline.remaining()
        # A successful destination is non-empty. Atomic rename cannot replace it;
        # racing publishers therefore get an explicit error, never a mixed set.
        try:
            staged.rename(destination)
        except FileExistsError as error:
            raise RendererError(f"Output đã tồn tại, không ghi đè: {destination}", "output_exists") from error
        except OSError as error:
            if destination.exists():
                raise RendererError(f"Output đã tồn tại, không ghi đè: {destination}", "output_exists") from error
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render Mermaid offline thành SVG, PNG và layout JSON.")
    parser.add_argument("--version", action="version", version=RENDERER_VERSION or "UNVERIFIED: runtime manifest missing")
    parser.add_argument("input", type=Path)
    parser.add_argument("scale_pos", nargs="?", type=float, help="scale (mặc định 2)")
    parser.add_argument("timeout_pos", nargs="?", type=float, help="timeout toàn lượt (mặc định 30 giây)")
    parser.add_argument("--layout", choices=("dagre", "elk", "auto"), default="dagre", help="Engine bố cục (ELK thử nghiệm)")
    parser.add_argument("--elk-spacing", type=float, default=1, help="Hệ số khoảng cách node ELK (mặc định 1, tối đa 4)")
    parser.add_argument("--raw-edges", action="store_true", help="Tương thích lệnh cũ; cả hai engine luôn giữ đường gốc")
    parser.add_argument("--scale", type=float)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--output", type=Path, help="Thư mục mới để công bố đủ ba file; không ghi đè")
    args = parser.parse_args(argv)
    try:
        if args.scale is not None and args.scale_pos is not None or args.timeout is not None and args.timeout_pos is not None:
            raise RendererError("Không truyền scale/timeout đồng thời bằng positional và option.", "invalid_argument")
        scale = args.scale if args.scale is not None else args.scale_pos if args.scale_pos is not None else 2
        timeout = args.timeout if args.timeout is not None else args.timeout_pos if args.timeout_pos is not None else 30
        deadline = _Deadline(_positive(timeout, "timeout", MAX_TIMEOUT))
        scale = _positive(scale, "scale", MAX_SCALE)
        if args.output is not None and (args.output.exists() or args.output.is_symlink()):
            raise RendererError(f"Output đã tồn tại, không ghi đè: {args.output}", "output_exists")
        try:
            if not stat.S_ISREG(args.input.stat().st_mode):
                raise RendererError("Input phải là file thường .mmd, không đọc FIFO/device.", "input")
            with args.input.open("rb") as stream:
                encoded = stream.read(MAX_SOURCE_BYTES + 1)
            if len(encoded) > MAX_SOURCE_BYTES:
                raise DiagramSourceError(f"Input vượt giới hạn {MAX_SOURCE_BYTES} byte UTF-8.", "limit")
            source = encoded.decode("utf-8")
        except UnicodeError as error:
            raise DiagramSourceError(f"Input không phải UTF-8 hợp lệ: {error}", "invalid_source") from error
        except OSError as error:
            raise RendererError(f"Không đọc được input UTF-8: {error}", "input") from error
        result = render(source, scale=scale, timeout=deadline.remaining(), layout=args.layout, raw_edges=args.raw_edges, elk_spacing=args.elk_spacing)
        destination = args.output or Path.cwd() / f"{args.input.stem}-render-{uuid.uuid4().hex}"
        _publish(result, destination, deadline)
        print(json.dumps({"output": str(destination.resolve())}, ensure_ascii=False))
        return 0
    except (DiagramSyntaxError, RendererError, OSError) as error:
        print(json.dumps({"kind": getattr(error, "kind", "engine"),
                          "category": getattr(error, "category", "engine"),
                          "line": getattr(error, "line_number", None),
                          "code": getattr(error, "code", "output"),
                          "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
