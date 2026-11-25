"""Stateless flowchart editing. Current state travels in SVG/PNG metadata.

No database, history or per-user state. Each call receives the current file,
works on a private copy and returns a new artifact after successful rendering.
The existing renderer owns and cleans its per-call scratch directories.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import inspect
import json
import math
import stat
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

# Repository/native deployment: renderer/ is the sibling source package.
# In the editor image its public modules are installed beside this CLI in /app.
_renderer_root = Path(__file__).resolve().parent.parent / "renderer"
if (_renderer_root / "renderer.py").is_file():
    sys.path.insert(0, str(_renderer_root))

from renderer import render, RendererError, DiagramSyntaxError, MAX_SOURCE_CHARS, MAX_SOURCE_BYTES
if __package__:
    from .edit_artifact import ArtifactError, extract, pack, embed_svg, embed_png, MAX_ARTIFACT_BYTES
else:
    from edit_artifact import ArtifactError, extract, pack, embed_svg, embed_png, MAX_ARTIFACT_BYTES


class DiagramEditError(ValueError):
    def __init__(self, code, message, **details):
        self.code, self.details = code, details
        super().__init__(message)


def _error(code, message, **details):
    raise DiagramEditError(code, message, **details)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _label(value):
    if not isinstance(value, str) or "\0" in value:
        _error("invalid_argument", "Nhãn phải là chuỗi không chứa NUL.")
    try:
        encoded=value.encode("utf-8")
        if len(value)>MAX_SOURCE_CHARS or len(encoded)>MAX_SOURCE_BYTES:
            _error("invalid_argument", "Nhãn vượt giới hạn source của renderer.")
    except UnicodeError:
        _error("invalid_argument", "Nhãn không phải Unicode hợp lệ.")
    return value


def _bridge(request, timeout):
    node = shutil.which("node")
    if not node:
        _error("dependency", "Thiếu Node để đọc/xuất model Mermaid.")
    # Same offline pinned grammar, with no ambient Node/preload configuration.
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"}
    try:
        p = subprocess.run([node, str(Path(__file__).with_name("edit-model.mjs"))],
                           input=_json(request), text=True, encoding="utf-8", capture_output=True,
                           timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        _error("timeout", "Đọc/xuất model Mermaid vượt timeout.")
    except OSError as e:
        _error("dependency", f"Không chạy được adapter chỉnh sửa: {e}")
    if p.returncode:
        detail=None
        try:
            detail = json.loads(p.stderr)
            message = detail["message"]
        except (ValueError, KeyError, TypeError):
            message = p.stderr[:2000]
        if request.get('action') in ('route_edge','region_seed','relayout_region','validate_region_geometry'):
            _error(detail.get('code','routing_failed') if isinstance(detail,dict) else 'routing_failed',message,**(detail.get('details',{}) if isinstance(detail,dict) else {}))
        _error("invalid_diagram", message)
    try:
        return json.loads(p.stdout)
    except ValueError:
        _error("dependency", "Adapter chỉnh sửa trả JSON không hợp lệ.")


def _changes(before, after, before_layout=None, after_layout=None):
    changes = {action: {} for action in ("added", "updated", "deleted")}
    for kind in ("nodes", "edges", "subgraphs"):
        old = {e["id"]: e for e in before[kind]}
        new = {e["id"]: e for e in after[kind]}
        changes["added"][kind] = [deepcopy(e) for id, e in new.items() if id not in old]
        changes["deleted"][kind] = [deepcopy(e) for id, e in old.items() if id not in new]
        changes["updated"][kind] = [{"id": id, "before": deepcopy(old[id]), "after": deepcopy(e)}
                                    for id, e in new.items() if id in old and old[id] != e]
    changes["layout_changed"] = {kind:[] for kind in ("nodes","edges","subgraphs")}
    if before_layout is not None and after_layout is not None:
        for kind in ("nodes","subgraphs"):
            old={e["id"]:e for e in before_layout[kind]}
            new={e["id"]:e for e in after_layout[kind]}
            changes["layout_changed"][kind]=[id for id in new if id in old and new[id]!=old[id]]
        def edge_map(state,layout):
            actual={e["ordinal"]:e for e in layout["edges"]}
            return {edge["id"]:{k:v for k,v in actual[i].items() if k!="ordinal"} for i,edge in enumerate(state["edges"])}
        old,new=edge_map(before,before_layout),edge_map(after,after_layout)
        changes["layout_changed"]["edges"]=[id for id in new if id in old and new[id]!=old[id]]
    return changes


def _entities(state, kind):
    return {e["id"]: e for e in state[kind]}


def _get(state, kind, id):
    try:
        return _entities(state, kind)[id]
    except (KeyError, TypeError):
        _error("id_not_found", f"Không tìm thấy {kind}: {id}", kind=kind, id=id)


def _endpoint(state, id):
    if not isinstance(id, str) or not any(e["id"] == id for k in ("nodes", "subgraphs") for e in state[k]):
        _error("id_not_found", f"Không tìm thấy đầu nối: {id}", id=id)


def _new_id(state, prefix):
    used = {e["id"] for k in ("nodes", "edges", "subgraphs") for e in state[k]}
    while True:
        candidate = prefix + "_" + uuid.uuid4().hex
        if candidate not in used:
            return candidate


def _membership(state):
    """Keep scope child order, then add newly moved children deterministically."""
    parents = {n["id"]: n["subgraph_id"] for n in state["nodes"]}
    parents.update({g["id"]: g["parent_id"] for g in state["subgraphs"]})
    for group in state["subgraphs"]:
        group["members"] = [id for id in group["members"] if parents.get(id) == group["id"]]
        for id, parent in parents.items():
            if parent == group["id"] and id not in group["members"]:
                group["members"].append(id)


def _state_shape(state):
    keys={"schema","direction","config","title","node_defaults","edge_defaults","nodes","subgraphs","edges"}
    if not isinstance(state,dict) or set(state)!=keys or type(state["schema"]) is not int or state["schema"]!=1:
        _error("invalid_artifact","Model metadata không đúng schema v1.")
    if state["direction"] not in ("TB","TD","BT","LR","RL") or not isinstance(state["config"],dict):
        _error("invalid_artifact","Direction/config không hợp lệ.")
    _label(state["title"])
    def style(value):
        if not isinstance(value,dict) or any(not isinstance(k,str) or isinstance(v,bool) or not isinstance(v,(str,int,float)) for k,v in value.items()):
            _error("invalid_artifact","Style metadata không hợp lệ.")
    style(state["node_defaults"]);style(state["edge_defaults"])
    schemas={"nodes":{"id","label","shape","style","subgraph_id"},
             "subgraphs":{"id","label","direction","style","parent_id","members"},
             "edges":{"id","mermaid_id","source","target","label","line_style","arrow_type","length","style"}}
    for kind,fields in schemas.items():
        if not isinstance(state[kind],list):_error("invalid_artifact",f"{kind} phải là danh sách.")
        for item in state[kind]:
            if not isinstance(item,dict) or set(item)!=fields or not isinstance(item["id"],str) or not item["id"]:
                _error("invalid_artifact",f"Đối tượng {kind} không hợp lệ.")
            _label(item["label"]);style(item["style"])
            if kind=="nodes":
                if not isinstance(item["shape"],str) or (item["subgraph_id"] is not None and not isinstance(item["subgraph_id"],str)):
                    _error("invalid_artifact","Shape/parent node không hợp lệ.")
            elif kind=="subgraphs":
                if item["direction"] not in (None,"TB","TD","BT","LR","RL") or (item["parent_id"] is not None and not isinstance(item["parent_id"],str)) or not isinstance(item["members"],list) or any(not isinstance(id,str) for id in item["members"]) or len(item["members"])!=len(set(item["members"])):
                    _error("invalid_artifact","Thành viên/hướng nhóm không hợp lệ.")
            else:
                if not isinstance(item["source"],str) or not isinstance(item["target"],str) or (item["mermaid_id"] is not None and not isinstance(item["mermaid_id"],str)) or item["line_style"] not in ("normal","dotted","thick","invisible") or item["arrow_type"] not in ("arrow_open","arrow_point","arrow_circle","arrow_cross","double_arrow_point","double_arrow_circle","double_arrow_cross") or type(item["length"]) is not int or not 1<=item["length"]<=500:
                    _error("invalid_artifact","Marker/kiểu/độ dài cạnh không hợp lệ.")


def _validate_state(state):
    _state_shape(state)
    ids = [e["id"] for k in ("nodes", "subgraphs") for e in state[k]]
    if len(ids) != len(set(ids)):
        _error("invalid_diagram", "ID node/subgraph trùng nhau.")
    edge_ids = [e["id"] for e in state["edges"]]
    if len(edge_ids) != len(set(edge_ids)):
        _error("invalid_diagram", "ID cạnh trùng nhau.")
    groups = _entities(state, "subgraphs")
    parents = {n["id"]: n["subgraph_id"] for n in state["nodes"]}
    parents.update({g["id"]: g["parent_id"] for g in state["subgraphs"]})
    for id, parent in parents.items():
        seen = {id}
        while parent is not None:
            if parent in seen or parent not in groups:
                _error("invalid_diagram", f"Parent không hợp lệ hoặc có chu trình: {id}")
            seen.add(parent)
            parent = groups[parent]["parent_id"]
    for e in state["edges"]:
        _endpoint(state, e["source"])
        _endpoint(state, e["target"])
    _membership(state)


def _semantic_check(state, parsed):
    """Don't silently publish a serializer that drops labels, styles or structure."""
    for key in ("direction", "config", "title"):
        if state[key] != parsed[key]:
            _error("serialization", f"Xuất Mermaid làm thay đổi {key}.")
    for kind, fields in (("nodes", ("id", "label", "shape", "style", "subgraph_id")),
                         ("subgraphs", ("id", "label", "direction", "style", "parent_id", "members"))):
        a = {e["id"]: {k: e[k] for k in fields} for e in state[kind]}
        b = {e["id"]: {k: e[k] for k in fields} for e in parsed[kind]}
        if a != b:
            _error("serialization", f"Xuất Mermaid làm thay đổi {kind}.", expected=a, actual=b)
    fields = ("source", "target", "label", "line_style", "arrow_type", "length", "style")
    def effective_edge(edge):
        data={k:edge[k] for k in fields}
        # Mermaid ~~~ has no marker token. Keep the requested marker in current
        # editing state for a later visible style, while comparing its effective
        # hidden rendering with the parser's arrow_open representation.
        if edge["line_style"]=="invisible":
            data["arrow_type"]=None
        return data
    if [effective_edge(e) for e in state["edges"]] != [effective_edge(e) for e in parsed["edges"]]:
        _error("serialization", "Xuất Mermaid làm thay đổi cạnh/kiểu nét/marker.", expected=state["edges"], actual=parsed["edges"])
    if [n["id"] for n in state["nodes"]] != [n["id"] for n in parsed["nodes"]]:
        _error("serialization", "Xuất Mermaid làm thay đổi thứ tự node của Dagre.")


class _Operations:
    """Mutates only a private in-memory copy. Never persists partial operations."""
    def __init__(self, state, timeout):
        self.state, self.timeout = state, timeout

    def add_node(self, label, shape="rect", fill_color=None, subgraph_id=None):
        if subgraph_id is not None:
            _get(self.state, "subgraphs", subgraph_id)
        valid = _bridge({"action": "validate", "shape": shape,
                         **({"fill_color": fill_color} if fill_color is not None else {})}, self.timeout)
        node = {"id": _new_id(self.state, "n"), "label": _label(label), "shape": valid["shape"],
                "style": deepcopy(self.state["node_defaults"]), "subgraph_id": subgraph_id}
        if fill_color is not None:
            node["style"]["fill"] = valid["fill_color"]
        self.state["nodes"].append(node)
        _membership(self.state)
        return {"node_id": node["id"], "node": deepcopy(node)}

    def delete_node(self, node_id):
        node = deepcopy(_get(self.state, "nodes", node_id))
        edges = [e for e in self.state["edges"] if node_id in (e["source"], e["target"])]
        self.state["edges"] = [e for e in self.state["edges"] if e not in edges]
        self.state["nodes"] = [n for n in self.state["nodes"] if n["id"] != node_id]
        _membership(self.state)
        return {"node_id": node_id, "node": node, "deleted_edge_ids": [e["id"] for e in edges], "deleted_edges": deepcopy(edges)}

    def update_node_label(self, node_id, label):
        node = _get(self.state, "nodes", node_id)
        node["label"] = _label(label)
        return {"node_id": node_id, "node": deepcopy(node)}

    def update_node_shape(self, node_id, shape):
        node = _get(self.state, "nodes", node_id)
        node["shape"] = _bridge({"action": "validate", "shape": shape}, self.timeout)["shape"]
        return {"node_id": node_id, "node": deepcopy(node)}

    def update_node_color(self, node_id, fill_color):
        node = _get(self.state, "nodes", node_id)
        valid = _bridge({"action": "validate", "fill_color": fill_color}, self.timeout)
        node["style"]["fill"] = valid["fill_color"]
        return {"node_id": node_id, "node": deepcopy(node)}

    def add_edge(self, source_id, target_id, label="", line_style=None):
        _endpoint(self.state, source_id)
        _endpoint(self.state, target_id)
        if line_style is not None and line_style not in ("normal", "dotted", "thick", "invisible"):
            _error("invalid_argument", f"Kiểu nét chưa hỗ trợ: {line_style}")
        style = deepcopy(self.state["edge_defaults"])
        if line_style is not None:
            style.pop("stroke-width", None)
            style.pop("stroke-dasharray", None)
        edge = {"id": _new_id(self.state, "e"), "mermaid_id": None, "source": source_id, "target": target_id,
                "label": _label(label), "line_style": line_style or "normal", "arrow_type": "arrow_point", "length": 1, "style": style}
        self.state["edges"].append(edge)
        return {"edge_id": edge["id"], "edge": deepcopy(edge)}

    def delete_edge(self, edge_id):
        edge = deepcopy(_get(self.state, "edges", edge_id))
        self.state["edges"] = [e for e in self.state["edges"] if e["id"] != edge_id]
        return {"edge_id": edge_id, "edge": edge}

    def update_edge_label(self, edge_id, label):
        edge = _get(self.state, "edges", edge_id)
        edge["label"] = _label(label)
        return {"edge_id": edge_id, "edge": deepcopy(edge)}

    def update_edge_line_style(self, edge_id, line_style):
        edge = _get(self.state, "edges", edge_id)
        if line_style not in ("normal", "dotted", "thick", "invisible"):
            _error("invalid_argument", f"Kiểu nét chưa hỗ trợ: {line_style}")
        edge["line_style"] = line_style
        edge["style"].pop("stroke-width", None)
        edge["style"].pop("stroke-dasharray", None)
        return {"edge_id": edge_id, "edge": deepcopy(edge)}

    def add_subgraph(self, label, node_ids, parent_subgraph_id=None):
        if not isinstance(node_ids, list) or any(not isinstance(id, str) for id in node_ids) or len(node_ids) != len(set(node_ids)):
            _error("invalid_argument", "node_ids phải là danh sách ID duy nhất.")
        if parent_subgraph_id is not None:
            _get(self.state, "subgraphs", parent_subgraph_id)
        nodes = [_get(self.state, "nodes", id) for id in node_ids]
        group = {"id": _new_id(self.state, "g"), "label": _label(label), "direction": None, "style": {},
                 "parent_id": parent_subgraph_id, "members": list(node_ids)}
        self.state["subgraphs"].append(group)
        for node in nodes:
            node["subgraph_id"] = group["id"]
        _membership(self.state)
        return {"subgraph_id": group["id"], "subgraph": deepcopy(group), "node_ids": list(node_ids)}

    def rename_subgraph(self, subgraph_id, label):
        group = _get(self.state, "subgraphs", subgraph_id)
        group["label"] = _label(label)
        return {"subgraph_id": subgraph_id, "subgraph": deepcopy(group)}

    def move_node_to_subgraph(self, node_id, target_subgraph_id):
        node = _get(self.state, "nodes", node_id)
        if target_subgraph_id is not None:
            _get(self.state, "subgraphs", target_subgraph_id)
        old = node["subgraph_id"]
        node["subgraph_id"] = target_subgraph_id
        _membership(self.state)
        return {"node_id": node_id, "node": deepcopy(node), "old_subgraph_id": old, "new_subgraph_id": target_subgraph_id}

    def delete_subgraph(self, subgraph_id, mode):
        group = deepcopy(_get(self.state, "subgraphs", subgraph_id))
        if mode not in ("ungroup", "delete_contents"):
            _error("invalid_argument", "mode bắt buộc là ungroup hoặc delete_contents.")
        removed = {subgraph_id}
        promoted = []
        if mode == "delete_contents":
            while True:
                children = {g["id"] for g in self.state["subgraphs"] if g["parent_id"] in removed}
                if children <= removed:
                    break
                removed.update(children)
            removed.update(n["id"] for n in self.state["nodes"] if n["subgraph_id"] in removed)
        else:
            for node in self.state["nodes"]:
                if node["subgraph_id"] == subgraph_id:
                    node["subgraph_id"] = group["parent_id"]
                    promoted.append(node["id"])
            for child in self.state["subgraphs"]:
                if child["parent_id"] == subgraph_id:
                    child["parent_id"] = group["parent_id"]
                    promoted.append(child["id"])
        direct = [e["id"] for e in self.state["edges"] if subgraph_id in (e["source"], e["target"])]
        deleted_edges = [e["id"] for e in self.state["edges"] if e["source"] in removed or e["target"] in removed]
        self.state["edges"] = [e for e in self.state["edges"] if e["id"] not in deleted_edges]
        self.state["nodes"] = [n for n in self.state["nodes"] if n["id"] not in removed]
        self.state["subgraphs"] = [g for g in self.state["subgraphs"] if g["id"] not in removed]
        _membership(self.state)
        return {"subgraph_id": subgraph_id, "mode": mode, "deleted_object_ids": sorted(removed),
                "promoted_ids": promoted, "deleted_edge_ids": deleted_edges, "direct_group_edge_ids": direct}

    def insert_node_on_edge(self, edge_id, label, shape="rect", fill_color=None, subgraph_id=None):
        old = deepcopy(_get(self.state, "edges", edge_id))
        node_result = self.add_node(label, shape, fill_color, subgraph_id)
        self.delete_edge(edge_id)
        new_edges = []
        for source, target, edge_label in [(old["source"], node_result["node_id"], old["label"]),
                                           (node_result["node_id"], old["target"], "")]:
            result = self.add_edge(source, target, edge_label, old["line_style"])
            edge = _get(self.state, "edges", result["edge_id"])
            for key in ("style", "arrow_type", "length"):
                edge[key] = deepcopy(old[key])
            new_edges.append(deepcopy(edge))
        return {**node_result, "deleted_edge": old, "deleted_edge_id": edge_id, "new_edges": new_edges,
                "new_edge_ids": [e["id"] for e in new_edges]}

    def delete_node_and_reconnect(self, node_id, connections=None):
        _get(self.state, "nodes", node_id)
        incoming = [e for e in self.state["edges"] if e["target"] == node_id]
        outgoing = [e for e in self.state["edges"] if e["source"] == node_id]
        inferred = connections is None
        template = None
        if inferred:
            if len(incoming) != 1 or len(outgoing) != 1 or incoming[0]["source"] == node_id or outgoing[0]["target"] == node_id:
                _error("ambiguous_reconnect", "Cần connections chỉ rõ từng cặp nguồn–đích khi có nhiều nhánh, thiếu nhánh hoặc self-loop.")
            left, right = incoming[0], outgoing[0]
            if left["label"] and right["label"] and left["label"] != right["label"]:
                _error("ambiguous_reconnect", "Hai nhãn khác nhau; cần connections để chọn nhãn mới.")
            if any(left[key] != right[key] for key in ("line_style", "arrow_type", "style", "length")):
                _error("ambiguous_reconnect", "Kiểu cạnh khác nhau; cần connections chỉ rõ cách nối lại.")
            template = left
            connections = [{"source_id": left["source"], "target_id": right["target"], "label": left["label"] or right["label"], "line_style": left["line_style"]}]
        if not isinstance(connections, list) or not connections:
            _error("invalid_argument", "connections cần ít nhất một cặp nguồn–đích.")
        predecessors = {e["source"] for e in incoming if e["source"] != node_id}
        successors = {e["target"] for e in outgoing if e["target"] != node_id}
        for connection in connections:
            if not isinstance(connection, dict) or set(connection) - {"source_id", "target_id", "label", "line_style"}:
                _error("invalid_argument", "connection chỉ nhận source_id, target_id, label, line_style.")
            source, target = connection.get("source_id"), connection.get("target_id")
            if not isinstance(source, str) or not isinstance(target, str) or source not in predecessors or target not in successors:
                _error("invalid_argument", "connection phải nối một node/nhóm đầu vào với một node/nhóm đầu ra của bước bị xóa.")
        deleted = self.delete_node(node_id)
        new_edges = []
        for connection in connections:
            result = self.add_edge(**connection)
            edge = _get(self.state, "edges", result["edge_id"])
            if template:
                for key in ("style", "arrow_type", "length"):
                    edge[key] = deepcopy(template[key])
            new_edges.append(deepcopy(edge))
        return {**deleted, "new_edges": new_edges, "new_edge_ids": [e["id"] for e in new_edges]}


def _apply(state, operations, timeout):
    if not isinstance(operations, list) or not operations or len(operations) > 500:
        _error("invalid_argument", "operations cần 1..500 lệnh.")
    engine, results, aliases = _Operations(state, timeout), [], {}
    allowed = {name for name, member in vars(_Operations).items() if not name.startswith("_") and callable(member)}
    def resolve(value):
        if isinstance(value, str) and value.startswith("$"):
            if value[1:] not in aliases:
                _error("invalid_argument", f"Alias chưa được tạo: {value}")
            return aliases[value[1:]]
        return value
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("op"),str) or operation["op"] not in allowed:
            _error("unsupported_operation", f"Lệnh chỉnh sửa không hỗ trợ: {operation}")
        args = {k: v for k, v in operation.items() if k not in ("op", "as")}
        # Resolve aliases only in ID fields, never reinterpret literal labels.
        for key in list(args):
            if key.endswith("_id"):
                args[key] = resolve(args[key])
            elif key == "node_ids" and isinstance(args[key], list):
                args[key] = [resolve(id) for id in args[key]]
            elif key == "connections" and isinstance(args[key], list):
                args[key] = [{k: resolve(v) if k.endswith("_id") else v for k,v in c.items()} if isinstance(c,dict) else c for c in args[key]]
        method = getattr(engine, operation["op"])
        try:
            inspect.signature(method).bind(**args)
        except TypeError as e:
            _error("invalid_argument", str(e))
        result = method(**args)
        if "as" in operation:
            alias = operation["as"]
            if not isinstance(alias, str) or not alias or alias in aliases:
                _error("invalid_argument", "Alias phải là tên duy nhất không rỗng.")
            key = "subgraph_id" if operation["op"] == "add_subgraph" else "edge_id" if operation["op"] == "add_edge" else "node_id"
            if operation["op"] not in ("add_node", "add_edge", "add_subgraph", "insert_node_on_edge"):
                _error("invalid_argument", "Alias chỉ dùng với lệnh tạo đối tượng.")
            aliases[alias] = result[key]
        results.append({"op": operation["op"], **result})
    _validate_state(state)
    return results


def _route_snapshot(rendered, state, routes, scale, timeout, positions=None, labels=None):
    """Validate numeric routes, patch only fresh renderer paths, rasterize again."""
    import html
    import re
    import xml.etree.ElementTree as ET
    import renderer as runtime
    layout=deepcopy(rendered.layout)
    svg=rendered.svg
    positions={} if positions is None else positions
    labels={} if labels is None else labels
    if not isinstance(positions,dict) or not isinstance(labels,dict):_error('invalid_geometry','positions/labels phải là object.')
    if not isinstance(routes,dict):_error('invalid_geometry','routes phải là object.')
    if positions or labels:
        layout=_bridge({'action':'region_seed','layout':layout,'state':state,
                        'positions':positions,'labels':labels},timeout)
        old_nodes={n['id']:n for n in rendered.layout['nodes']}
        new_nodes={n['id']:n for n in layout['nodes']}
        def move_group(match):
            attrs,body=match.group(1),match.group(2)
            node_id=re.search(r'(?<![\w-])id="([^"]*)"',attrs)
            ordinal=re.search(r'data-edge-label="(\d+)"',attrs)
            dx=dy=0;box=None;node_box=None
            if node_id and html.unescape(node_id[1]) in positions:
                id=html.unescape(node_id[1]);before=old_nodes[id];after=new_nodes[id]
                dx=after['box'][0]-before['box'][0];dy=after['box'][1]-before['box'][1]
                box=after['label_box'];node_box=after['box']
            elif ordinal:
                i=int(ordinal[1]);id=state['edges'][i]['id']
                if id in labels:
                    before=next(e for e in rendered.layout['edges'] if e['ordinal']==i)['label_box']
                    box=next(e for e in layout['edges'] if e['ordinal']==i)['label_box']
                    dx=box[0]-before[0];dy=box[1]-before[1]
            if box is None:return match.group()
            attrs+=f' transform="translate({dx} {dy})"'
            for name,value in [('data-label-box',box),('data-node-box',node_box)]:
                if value is not None:attrs=re.sub(rf'{name}="[^"]*"',lambda _:f'{name}="{html.escape(_json(value),quote=True)}"',attrs)
            return '<g'+attrs+'>'+body+'</g>'
        svg=re.sub(r'<g\b([^>]*)>(.*?)</g>',move_group,svg,flags=re.S)
        required={e['id'] for e in state['edges'] if e['source'] in positions or e['target'] in positions}
        required.update(labels)
        if not required.issubset(routes):_error('invalid_geometry','Thiếu đường mới cho cạnh nối node đã di chuyển.')
    if not isinstance(routes,dict) or len(routes)>len(state['edges']):
        _error('invalid_artifact','Danh sách đường cạnh không hợp lệ.')
    for edge_id,points in routes.items():
        # Every replay checks endpoints, label anchor and hard obstacles again.
        result=_bridge({'action':'route_edge','state':state,'layout':layout,
                        'edge_id':edge_id,'points':points,'allow_invisible':bool(positions)},timeout)
        ordinal=next(i for i,e in enumerate(state['edges']) if e['id']==edge_id)
        data=next(e for e in layout['edges'] if e['ordinal']==ordinal)
        data['points']=result['points'];data['corner_radii']=[0]*len(result['points'])
        attrs={'d':' '.join(f'{"M" if i==0 else "L"} {p[0]} {p[1]}' for i,p in enumerate(points)),
               'data-points':_json(points),'data-corner-radii':_json(data['corner_radii'])}
        pattern=rf'<path\b[^>]*\bdata-ordinal="{ordinal}"[^>]*>'
        def patch(match):
            tag=match.group()
            for key,value in attrs.items():
                tag,count=re.subn(rf'(?<![\w-]){key}="[^"]*"',lambda _:f'{key}="{html.escape(value,quote=True)}"',tag)
                if count!=1:_error('render_failed','Không tìm thấy thuộc tính đường cạnh trong SVG mới.')
            return tag
        svg,count=re.subn(pattern,patch,svg)
        if count!=1:_error('render_failed','Không tìm thấy đúng một cạnh trong SVG mới.')
    if positions or labels:_bridge({'action':'validate_region_geometry','layout':layout,'state':state,
                                    'positions':positions,'labels':labels},timeout)
    version=ET.fromstring(rendered.svg).attrib['data-renderer-version']
    deadline=runtime._Deadline(timeout)
    try:
        svg=runtime._svg(svg.encode(),layout,expected_version=version)
        with tempfile.TemporaryDirectory(prefix='aiz-edge-edit-') as folder:
            scratch=Path(folder);source=scratch/'diagram.svg';target=scratch/'diagram.png'
            source.write_text(svg,encoding='utf-8')
            raster=shutil.which('rsvg-convert')
            if not raster:_error('dependency','Thiếu rsvg-convert.')
            runtime._run([raster,f'--zoom={scale}',f'--output={target}',str(source)],scratch,'edge-raster',deadline,
                         [(target,runtime.MAX_PNG_BYTES)])
            png=runtime._read_limited(target,runtime.MAX_PNG_BYTES)
            runtime._png(png,runtime._raster_dimensions(layout,scale))
        return runtime.Rendered(svg=svg,png=png,layout=layout)
    except RendererError as e:
        _error('render_failed',str(e),renderer_code=e.code)


class DiagramEditor:
    """Configuration only. Every call receives an artifact and returns a new one.

    No model, database, history, lock or artifact is retained on this object.
    diagram_id/revision are checked against the submitted file, not a server head.
    """
    def __init__(self, *, scale=2, timeout=30):
        for name,value,maximum in (("scale",scale,16),("timeout",timeout,300)):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=maximum:
                _error("invalid_argument",f"{name} không hợp lệ.")
        self.scale,self.timeout=scale,timeout

    def _render(self, source):
        try:
            return render(source,scale=self.scale,timeout=self.timeout)
        except (RendererError,DiagramSyntaxError) as e:
            _error("render_failed",f"Không tạo kết quả vì render thất bại: {e}",renderer_code=getattr(e,"code","syntax"))

    def _source(self, state):
        result=_bridge({"action":"serialize","state":state},self.timeout)
        _semantic_check(state,result["parsed"])
        return result["source"]

    @staticmethod
    def _manifest(state, layout=None):
        mapping=[]
        if layout is not None and len(state["edges"])!=len(layout["edges"]):
            _error("render_failed","Số cạnh renderer khác model chỉnh sửa.")
        by_ordinal={e["ordinal"]:e for e in layout["edges"]} if layout is not None else {}
        for i,edge in enumerate(state["edges"]):
            if layout is not None:
                actual=by_ordinal.get(i)
                if actual is None or (actual["source"],actual["target"])!=(edge["source"],edge["target"]):
                    _error("render_failed","Đầu nối/ordinal renderer khác model chỉnh sửa.")
            mapping.append({"edge_id":edge["id"],"ordinal":i,"source":edge["source"],"target":edge["target"]})
        return {"node_ids":[n["id"] for n in state["nodes"]],"subgraph_ids":[g["id"] for g in state["subgraphs"]],"edges":mapping}

    def _checked(self, artifact, diagram_id, expected_revision):
        if not isinstance(diagram_id,str) or not diagram_id or type(expected_revision) is not int or expected_revision<1:
            _error("invalid_argument","Cần diagram_id không rỗng và expected_revision nguyên dương.")
        try:
            payload=extract(artifact)
        except ArtifactError as e:
            _error("invalid_artifact",str(e))
        if payload["preview"]:
            _error("preview_artifact","File preview không phải phiên bản đã áp dụng; hãy dùng file gốc và gửi lại operations.")
        if payload["diagram_id"]!=diagram_id:
            _error("diagram_not_found","diagram_id không khớp file được gửi vào.")
        if payload["revision"]!=expected_revision:
            _error("stale_revision","Revision không khớp file được gửi vào.",expected_revision=expected_revision,actual_revision=payload["revision"])
        self._check_source(payload["source"])
        state=payload["state"]
        original=deepcopy(state)
        _validate_state(state)
        if state!=original:
            _error("invalid_artifact","Quan hệ thành viên trong metadata không nhất quán.")
        # Treat metadata as untrusted input. Validate paints/defaults through the
        # same style validators and check source/model equivalence. Never replay
        # any uploaded SVG primitive, PNG pixel or stored layout as output.
        self._source(state)
        parsed=_bridge({"action":"import","source":payload["source"]},self.timeout)
        _semantic_check(state,parsed)
        return payload

    @staticmethod
    def _check_source(source):
        if not isinstance(source,str):
            _error("invalid_argument","Source Mermaid phải là chuỗi.")
        try:encoded=source.encode('utf-8')
        except UnicodeError:_error("invalid_argument","Source không phải Unicode hợp lệ.")
        if len(source)>MAX_SOURCE_CHARS or len(encoded)>MAX_SOURCE_BYTES:
            _error("invalid_argument","Source Mermaid vượt giới hạn renderer.")

    def _result(self, diagram_id, revision, state, source, rendered, changes, results, *, preview=False, geometry=None):
        manifest=self._manifest(state,rendered.layout)
        try:
            raw=pack(diagram_id,revision,source,state,preview=preview,geometry=geometry)
            svg=embed_svg(rendered.svg,raw)
            png=embed_png(rendered.png,raw)
        except ArtifactError as e:
            _error("invalid_artifact",str(e))
        return {"diagram_id":diagram_id,"revision":revision,"preview":preview,"source":source,
                "state":deepcopy(state),"changes":changes,"results":results,"manifest":manifest,
                "rendered":{"svg":svg,"png":png,"layout":deepcopy(rendered.layout)}}

    def create_diagram(self, source, diagram_id=None):
        self._check_source(source)
        if diagram_id is None:diagram_id="d_"+uuid.uuid4().hex
        if not isinstance(diagram_id,str) or not diagram_id:
            _error("invalid_argument","diagram_id phải là chuỗi không rỗng.")
        rendered=self._render(source)
        state=_bridge({"action":"import","source":source},self.timeout)
        _validate_state(state)
        self._source(state)
        empty={kind:[] for kind in ("nodes","edges","subgraphs")}
        return self._result(diagram_id,1,state,source,rendered,_changes(empty,state),[])

    def get_diagram(self, artifact, diagram_id, expected_revision):
        payload=self._checked(artifact,diagram_id,expected_revision)
        if "geometry" in payload:self._restore_routes(payload,self._render(payload["source"]))
        return {"diagram_id":diagram_id,"revision":expected_revision,"source":payload["source"],
                "state":deepcopy(payload["state"]),"manifest":self._manifest(payload["state"]),
                **({"geometry":deepcopy(payload["geometry"])} if "geometry" in payload else {})}

    def _restore_routes(self, payload, rendered):
        geometry=payload.get('geometry')
        if 'geometry' not in payload:return rendered
        import xml.etree.ElementTree as ET
        if not isinstance(geometry,dict) or set(geometry) not in ({'renderer_version','base_layout','routes'},{'renderer_version','base_layout','routes','positions','labels'}):
            _error('invalid_artifact','Geometry metadata không hợp lệ.')
        version=ET.fromstring(rendered.svg).attrib['data-renderer-version']
        if geometry['renderer_version']!=version or geometry['base_layout']!=rendered.layout:
            _error('layout_incompatible','Renderer hoặc bố cục gốc đã thay đổi; không thể phát lại đường đã sửa.')
        return _route_snapshot(rendered,payload['state'],geometry['routes'],self.scale,self.timeout,geometry.get('positions'),geometry.get('labels'))

    def reroute_edge(self, artifact, diagram_id, expected_revision, edge_id,
                     avoid_overlap_with=None, prefer_side=None):
        return self.apply_diagram_edit(artifact,diagram_id,expected_revision,[{
            'op':'reroute_edge','edge_id':edge_id,'avoid_overlap_with':[] if avoid_overlap_with is None else avoid_overlap_with,
            'prefer_side':prefer_side}])

    def relayout_region(self, artifact, diagram_id, expected_revision, node_ids,
                        goal='compact', direction='LR', preserve_boundary=True, bounds=None):
        operation={'op':'relayout_region','node_ids':node_ids,'goal':goal,
                   'direction':direction,'preserve_boundary':preserve_boundary}
        if bounds is not None:operation['bounds']=bounds
        return self.apply_diagram_edit(artifact,diagram_id,expected_revision,[operation])

    def _reroute(self, payload, operations, preview):
        import xml.etree.ElementTree as ET
        if len(operations)>50:_error('invalid_argument','Tối đa 50 lệnh chỉnh hình học mỗi lần.')
        base=self._render(payload['source'])
        before=self._restore_routes(payload,base)
        current=before
        routes=deepcopy(payload.get('geometry',{}).get('routes',{}))
        positions=deepcopy(payload.get('geometry',{}).get('positions',{}))
        labels=deepcopy(payload.get('geometry',{}).get('labels',{}))
        results=[]
        for op in operations:
            if op.get('op')=='relayout_region':
                if set(op)-{'op','node_ids','goal','direction','preserve_boundary','bounds'}:
                    _error('invalid_argument','Tham số relayout_region không hợp lệ.')
                request={k:v for k,v in op.items() if k!='op'}
                planned=_bridge({'action':'relayout_region','state':payload['state'],
                                 'layout':current.layout,**request},self.timeout)
                positions.update(planned['positions']);labels.update(planned['labels']);routes.update(planned['routes'])
                current=_route_snapshot(base,payload['state'],routes,self.scale,self.timeout,positions,labels)
                results.append({'op':'relayout_region',**planned})
            else:
                if not isinstance(op,dict) or set(op)-{'op','edge_id','avoid_overlap_with','prefer_side'}:
                    _error('invalid_argument','Tham số reroute_edge không hợp lệ.')
                edge_id=op.get('edge_id')
                if not isinstance(edge_id,str):_error('invalid_argument','Cần edge_id.')
                _get(payload['state'],'edges',edge_id)
                request={k:v for k,v in op.items() if k!='op'}
                ordinal=next(i for i,e in enumerate(payload['state']['edges']) if e['id']==edge_id)
                edge_layout=next(e for e in current.layout['edges'] if e['ordinal']==ordinal)
                routed=_bridge({'action':'route_edge','state':payload['state'],
                                'layout':current.layout,**request,'relocate_label':True,
                                'label_size':edge_layout['label_box'][2:]},self.timeout)
                routes[edge_id]=routed['points']
                if routed.get('label_box', [0,0,0,0])[2]>0:
                    labels[edge_id]=routed['label_box'][:2]
                current=_route_snapshot(base,payload['state'],routes,self.scale,self.timeout,positions,labels)
                results.append({'op':'reroute_edge','edge_id':edge_id,**routed})
        geometry={'renderer_version':ET.fromstring(base.svg).attrib['data-renderer-version'],
                  'base_layout':base.layout,'routes':routes}
        if positions or labels:geometry.update(positions=positions,labels=labels)
        revision=payload['revision'] if preview else payload['revision']+1
        result=self._result(payload['diagram_id'],revision,payload['state'],payload['source'],current,
            _changes(payload['state'],payload['state'],before.layout,current.layout),results,
            preview=preview,geometry=geometry)
        if preview:result['base_revision']=payload['revision']
        return result

    def _edit(self, artifact, diagram_id, expected_revision, operations, *, preview):
        payload=self._checked(artifact,diagram_id,expected_revision)
        if not isinstance(operations,list) or not operations:
            _error('invalid_argument','operations cần danh sách không rỗng.')
        routing=[isinstance(op,dict) and op.get('op') in ('reroute_edge','relayout_region') for op in operations]
        if any(routing):
            if not all(routing):_error('invalid_argument','Không trộn lệnh chỉnh hình học với lệnh sửa model trong cùng batch.')
            return self._reroute(payload,operations,preview)
        if 'geometry' in payload:
            _error('geometry_edit_conflict','Bản này có chỉnh sửa hình học; chưa hỗ trợ sửa model trên bản có geometry. Hãy tạo bản mới từ source.')
        old=payload["state"]
        state=deepcopy(old)
        results=_apply(state,operations,self.timeout)
        source=self._source(state)
        # Fresh renders keep indirect geometry reports correct without retaining
        # uploaded layout or any server-side cache between requests.
        before=self._render(payload["source"])
        rendered=self._render(source)
        revision=expected_revision if preview else expected_revision+1
        response=self._result(diagram_id,revision,state,source,rendered,
                              _changes(old,state,before.layout,rendered.layout),results,preview=preview)
        if preview:response["base_revision"]=expected_revision
        return response

    def apply_diagram_edit(self, artifact, diagram_id, expected_revision, operations):
        return self._edit(artifact,diagram_id,expected_revision,operations,preview=False)

    def preview_diagram_edit(self, artifact, diagram_id, expected_revision, operations):
        return self._edit(artifact,diagram_id,expected_revision,operations,preview=True)

    def export_diagram(self, artifact, diagram_id, expected_revision, destination):
        payload=self._checked(artifact,diagram_id,expected_revision)
        rendered=self._restore_routes(payload,self._render(payload["source"]))
        empty={kind:[] for kind in ("nodes","edges","subgraphs")}
        result=self._result(diagram_id,expected_revision,payload["state"],payload["source"],rendered,_changes(empty,empty),[],geometry=payload.get("geometry"))
        return _publish(result,destination)


def _publish(result, destination):
    """Publish only caller-requested output; remove staging on success/failure."""
    destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        _error("output_exists","Output đã tồn tại hoặc thư mục cha chưa tồn tại.")
    with tempfile.TemporaryDirectory(prefix=".edit-export-",dir=destination.parent) as temporary:
        staged=Path(temporary)/"result"
        staged.mkdir()
        for name,data in [("diagram.svg",result["rendered"]["svg"].encode('utf-8')),
                          ("diagram.png",result["rendered"]["png"]),
                          ("layout.json",_json(result["rendered"]["layout"]).encode('utf-8')),
                          ("source.mmd",result["source"].encode('utf-8')),
                          ("edit-manifest.json",_json({"diagram_id":result["diagram_id"],"revision":result["revision"],"preview":result["preview"],**result["manifest"]}).encode('utf-8'))]:
            (staged/name).write_bytes(data)
        try:staged.rename(destination)
        except OSError:_error("output_exists","Không thể công bố output; file đầu vào giữ nguyên.")
    return {"diagram_id":result["diagram_id"],"revision":result["revision"],"output":str(destination)}


# Explicit method signatures keep function calling/agent schema discovery clear.
# These thin wrappers share the same atomic batch implementation.
def _install_operation_methods():
    for name,method in vars(_Operations).items():
        if name.startswith('_') or not callable(method):
            continue
        def make(name,method):
            signature=inspect.signature(method)
            def command(self,artifact,diagram_id,expected_revision,*args,**kwargs):
                bound=signature.bind(None,*args,**kwargs)
                values={k:v for k,v in bound.arguments.items() if k!='self'}
                return self.apply_diagram_edit(artifact,diagram_id,expected_revision,[{"op":name,**values}])
            command.__name__=name
            command.__doc__=f"Atomically apply {name}; requires diagram_id and expected_revision."
            parameters=list(signature.parameters.values())
            command.__signature__=signature.replace(parameters=[parameters[0],inspect.Parameter('artifact',inspect.Parameter.POSITIONAL_OR_KEYWORD),inspect.Parameter('diagram_id',inspect.Parameter.POSITIONAL_OR_KEYWORD),inspect.Parameter('expected_revision',inspect.Parameter.POSITIONAL_OR_KEYWORD),*parameters[1:]])
            return command
        setattr(DiagramEditor,name,make(name,method))
_install_operation_methods()


def _read_file(path, limit):
    if not stat.S_ISREG(path.lstat().st_mode):
        _error("invalid_argument","Input phải là file thường, không phải symlink/FIFO/device.")
    with path.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:_error("invalid_argument","Input vượt giới hạn kích thước.")
    return data


def main(argv=None):
    parser=argparse.ArgumentParser(description="Chỉnh sửa SVG/PNG mang metadata hiện tại; không giữ database/lịch sử.")
    parser.add_argument('command',choices=['init','get','apply','preview','export'])
    parser.add_argument('--scale',type=float,default=2)
    parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--input',type=Path,help='SVG/PNG gốc có metadata chỉnh sửa')
    parser.add_argument('--source',type=Path,help='Mermaid .mmd, chỉ dùng khi init')
    parser.add_argument('--diagram-id')
    parser.add_argument('--expected-revision',type=int)
    parser.add_argument('--operations',type=Path,help='JSON array; bỏ trống để đọc stdin với apply/preview')
    parser.add_argument('--output',type=Path,help='Thư mục output mới; bắt buộc ngoài get')
    args=parser.parse_args(argv)
    try:
        editor=DiagramEditor(scale=args.scale,timeout=args.timeout)
        if args.command!='get' and args.output is None:
            _error('invalid_argument','Cần --output trỏ tới thư mục mới.')
        if args.output is not None and (args.output.exists() or args.output.is_symlink()):
            _error('output_exists','Không ghi đè output đã tồn tại.')
        if args.command=='init':
            if args.source is None:_error('invalid_argument','init cần --source.')
            result=editor.create_diagram(_read_file(args.source,MAX_SOURCE_BYTES).decode('utf-8'),args.diagram_id)
        else:
            if args.input is None or args.diagram_id is None or args.expected_revision is None:
                _error('invalid_argument','Cần --input, --diagram-id và --expected-revision.')
            pair=(_read_file(args.input,MAX_ARTIFACT_BYTES),args.diagram_id,args.expected_revision)
            if args.command in ('apply','preview'):
                raw=_read_file(args.operations,2*1024*1024) if args.operations else sys.stdin.buffer.read(2*1024*1024+1)
                if len(raw)>2*1024*1024:_error('invalid_argument','operations vượt 2 MiB.')
                operations=json.loads(raw)
                result=getattr(editor,'preview_diagram_edit' if args.command=='preview' else 'apply_diagram_edit')(*pair,operations)
            elif args.command=='export':
                print(_json(editor.export_diagram(*pair,args.output)));return 0
            else:
                print(_json(editor.get_diagram(*pair)));return 0
        published=_publish(result,args.output)
        summary={k:v for k,v in result.items() if k!='rendered'}
        print(_json({**summary,**published}))
        return 0
    except (DiagramEditError,ArtifactError,RendererError,DiagramSyntaxError,OSError,ValueError,TypeError,RecursionError) as e:
        print(_json({'code':getattr(e,'code','invalid_argument'),'message':str(e),'details':getattr(e,'details',{})}),file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
