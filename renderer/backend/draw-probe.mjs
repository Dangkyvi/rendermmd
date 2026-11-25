import { parseFlowchart } from "./mermaid-model.mjs";
import { SourceError } from "./theme-source.mjs";
import { layoutSubgraphs } from "./subgraph-layout.mjs";

import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { readFile, writeFile, mkdtemp, rename, rm, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
const require = createRequire(import.meta.url);
const dagre = require("@dagrejs/dagre");
// The public Node CLI delegates to the Python contract. --internal is used
// only by the Python supervisor, with a private destination in its scratch.
if (process.argv[2] !== "--internal") {
  try {
    execFileSync(process.env.AIZ_PYTHON_EXECUTABLE ?? "python3", [
      fileURLToPath(new URL(existsSync(new URL("./renderer.py", import.meta.url)) ? "./renderer.py" : "../renderer.py", import.meta.url)), ...process.argv.slice(2),
    ], {stdio:"inherit"});
  } catch (error) {
    process.exitCode = error.status ?? 1;
  }
} else {
let workDir;
let parserLineMap;
let sourceLineCount = 1;
try {
  const destination = process.argv[4];
  if (!destination) throw new Error("Backend cần output directory riêng.");
  try { await stat(destination); throw new Error("Output backend đã tồn tại."); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  workDir = await mkdtemp(join(dirname(destination), ".node-"));

  const { sourceConfiguration, plainLabel: decodeLabel, parseStyles, shapePaint, labelFont, fontSize, fontFamily, color } = await import("./theme-source.mjs");
  const inputPath = process.argv[3];

  if (!inputPath) {
    throw new Error("Thiếu đường dẫn file .mmd đầu vào.");
  }

  const source = await readFile(inputPath, "utf8");
  const requested = sourceConfiguration(source);
  // Parse errors refer to Mermaid's cleaned code. Restore its front-matter and
  // leading-comment line offsets once, using parser metadata, not error ID text.
  parserLineMap = requested.lineMap;
  sourceLineCount = requested.sourceLineCount;
  const { diagram, config } = await parseFlowchart(source, requested);
  const variables = config.themeVariables;
  const requestedVariables = requested.config.themeVariables ?? {};
  const fontPx = fontSize(requestedVariables.fontSize ?? requested.config.fontSize ?? 15);
  const family = fontFamily(requestedVariables.fontFamily ?? requested.config.fontFamily ?? "Noto Sans");
  const globalFont = {"font-family":family,"font-size":fontPx,"font-weight":"normal","font-style":"normal"};
  // Preserve the prototype's unthemed appearance. Explicit source themes use
  // Mermaid's computed palette, including derived themeVariables.
  const themed = Object.keys(requested.config).length > 0;
  const palette = themed ? {
    node: requestedVariables.nodeBkg ?? requestedVariables.mainBkg ?? variables.mainBkg ?? variables.primaryColor,
    border: variables.nodeBorder ?? variables.primaryBorderColor,
    text: variables.nodeTextColor ?? variables.textColor,
    line: variables.defaultLinkColor ?? variables.lineColor,
    cluster: variables.clusterBkg, clusterBorder: variables.clusterBorder,
    clusterText: variables.clusterTextColor ?? variables.titleColor ?? variables.textColor,
    title: variables.titleColor ?? variables.textColor,
    edgeText: variables.textColor, edgeBackground: variables.edgeLabelBackground,
    background: variables.background,
  } : {node:"#eff6ff",border:"#2563eb",text:"#0f172a",line:"#334155",cluster:"#f8fafc",clusterBorder:"#94a3b8",clusterText:"#0f172a",title:"#0f172a",edgeText:"#0f172a",edgeBackground:"#ffffff",background:"none"};
  for (const value of Object.values(palette)) {
    try { color(value); }
    catch (error) {
      // User paints were validated before theme computation. A bad derived
      // palette is an engine/dependency result, not another source mistake.
      throw Object.assign(new Error(`Theme engine tạo màu không hợp lệ: ${error.message}`), {code: 'output'});
    }
  }
  const title = decodeLabel(diagram.db.getDiagramTitle());

  const sourceGroups = diagram.db.getSubGraphs();
  const groupIds = new Set(sourceGroups.map((group) => group.id));
  for (const group of sourceGroups) {
    if ((group.metadata && Object.keys(group.metadata).some((key) => key !== "view")) ||
        (group.metadata?.view && group.metadata.view !== "expanded")) {
      throw new SourceError(`Subgraph ${group.id}: metadata chưa hỗ trợ (chỉ view: expanded).`);
    }
  }
  const direction = diagram.db.getDirection();
  const rankdir = direction === "TD" ? "TB" : direction;

  if (!["LR", "RL", "TB", "BT"].includes(rankdir)) {
    throw new SourceError(`Hướng chưa được demo hỗ trợ: ${direction}`);
  }
  const graph = new dagre.graphlib.Graph({ multigraph: true });

  graph.setGraph({
    rankdir,
    nodesep: 40,
    ranksep: 80,
    marginx: 20,
    marginy: 20,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  const sourceVertices = [...diagram.db.getVertices().values()];
  for (const item of [...sourceVertices,...sourceGroups,...diagram.db.getEdges()]) {
    if (item.labelType === "markdown") throw new SourceError("Nhãn Markdown chưa được hỗ trợ; dùng nhãn văn bản với br/entity.");
  }
  for (const node of sourceVertices) {
    if (node.link || node.haveCallback || node.classes?.includes("clickable") || node.img || node.icon) {
      throw new SourceError(`Node ${node.id}: link/callback/ảnh/icon từ source không được phép.`);
    }
  }
  // Validate even unused class definitions, so forbidden declarations never hide
  // behind an unassigned class. Only inert paint and Pango font properties pass.
  for (const [id, definition] of diagram.db.getClasses()) {
    parseStyles([...(definition.styles ?? []), ...(definition.textStyles ?? [])], `classDef ${id}`);
  }
  const vertices = sourceVertices.filter((node) => !groupIds.has(node.id));
  if (!vertices.length && !sourceGroups.length) throw new SourceError("Flowchart không có node/subgraph.", "input");
  function nodeStyle(node, group = false) {
    return {...globalFont, fill:group ? palette.cluster : palette.node,
      stroke:group ? palette.clusterBorder : palette.border, color:group ? palette.clusterText : palette.text,
      "stroke-width":1,
      ...parseStyles([
        ...diagram.db.getCompiledStyles(group ? node.classes ?? [] : ["default","node",...(node.classes ?? [])]),
        ...(node.styles ?? []),
      ], `Node/subgraph ${node.id}`)};
  }
  const nodeStyles = vertices.map((node) => nodeStyle(node));
  const groupStyles = sourceGroups.map((group) => nodeStyle({
    ...group, styles:sourceVertices.find((node) => node.id===group.id)?.styles ?? [],
  }, true));
  const sourceEdges = diagram.db.getEdges();
  const requestedLayout=process.argv[5]??'dagre';
  if(!['dagre','elk','auto'].includes(requestedLayout)) throw new Error(`Layout engine không hợp lệ: ${requestedLayout}`);
  // Versioned policy: count the parsed model, never render candidate layouts.
  const autoThresholds={nodes:25,edges:35,subgraphs:3,depth:2};
  const groupParent=new Map();
  for(const group of sourceGroups) for(const id of group.nodes) if(groupIds.has(id)) {
    if(groupParent.has(id)&&groupParent.get(id)!==group.id) throw new SourceError(`Subgraph ${id} có nhiều parent.`,'source_structure');
    groupParent.set(id,group.id);
  }
  let maxDepth=0;
  for(const group of sourceGroups) {
    let id=group.id,depth=0;const seen=new Set();
    while(id!==undefined) {
      if(seen.has(id)) throw new SourceError('Cây subgraph có chu trình.','source_structure');
      seen.add(id);depth++;id=groupParent.get(id);
    }
    maxDepth=Math.max(maxDepth,depth);
  }
  const layoutStats={nodes:vertices.length,edges:sourceEdges.length,subgraphs:sourceGroups.length,depth:maxDepth};
  const useElk=Object.keys(autoThresholds).some(key=>layoutStats[key]>=autoThresholds[key]);
  const layoutEngine=requestedLayout==='auto'?(useElk?'elk':'dagre'):requestedLayout;

  // getEdges() is the order used by linkStyle, not the suffix of edge.id.
  const edgeLabels = sourceEdges.map((edge) =>
    edge.stroke === "invisible" ? "" : edge.text ?? "",
  );
  const strokeStyles = {
    normal: { "stroke-width": 1.5 },
    dotted: { "stroke-width": 1.5, "stroke-dasharray": "3 3" },
    thick: { "stroke-width": 3.5 },
    invisible: { "stroke-width": 0 },
  };
  const arrowTypes = {
    arrow_open: [null, null],
    arrow_point: [null, "point"],
    arrow_circle: [null, "circle"],
    arrow_cross: [null, "cross"],
    double_arrow_point: ["point", "point"],
    double_arrow_circle: ["circle", "circle"],
    double_arrow_cross: ["cross", "cross"],
  };
  function edgeAppearance(edge, ordinal) {
    if (!Object.hasOwn(strokeStyles, edge.stroke) ||
        !Object.hasOwn(arrowTypes, edge.type)) {
      throw new SourceError(`Edge ${ordinal}: nét/đầu nối chưa hỗ trợ: ${edge.stroke}/${edge.type}`);
    }
    const overrides = parseStyles([
      ...diagram.db.getCompiledStyles(edge.classes ?? []),
      ...(sourceEdges.defaultStyle ?? []), ...(edge.style ?? []),
    ], `Edge ${ordinal}`);
    if (overrides.fill && overrides.fill !== "none") throw new SourceError(`Edge ${ordinal}: chỉ fill:none được hỗ trợ.`);
    return {...globalFont, color:palette.edgeText, stroke:palette.line, ...strokeStyles[edge.stroke], ...overrides,
      markerColor:overrides.stroke ?? requestedVariables.arrowheadColor ?? palette.line};
  }
  const edgeStyles = sourceEdges.map(edgeAppearance);
  const plainLabel = (value) => decodeLabel(value);

  let measurements;
  try {
    measurements = JSON.parse(
      execFileSync(process.env.AIZ_PYTHON_EXECUTABLE ?? "python3", [fileURLToPath(new URL("./text_geometry.py", import.meta.url))], {
        input: JSON.stringify([
          ...vertices.map((node,index) => ({text:plainLabel(node.text),...labelFont(nodeStyles[index])})),
          ...edgeLabels.map((text,index) => ({text:plainLabel(text),...labelFont(edgeStyles[index])})),
          ...sourceGroups.map((group,index) => ({text:plainLabel(group.title),...labelFont(groupStyles[index])})),
          {text:title,...labelFont(globalFont)},
        ]),
        encoding: "utf8",
        stdio: ["pipe", "pipe", "pipe"],
        maxBuffer: 16 * 1024 * 1024,
      }),
    );
  } catch (error) {
    let detail;
    try { detail = JSON.parse(error.stderr?.toString() ?? ''); } catch {}
    if (detail?.kind === 'source' && ['font', 'glyph'].includes(detail.code)) {
      throw new SourceError(detail.message, detail.code);
    }
    if (detail?.kind === 'engine') {
      throw Object.assign(new Error(`Pango: ${detail.message}`), {code: detail.code ?? 'engine'});
    }
    throw error;
  }
  const visibleFonts = measurements.filter((item) => item.path_box[2] > 0 && item.path_box[3] > 0)
    .flatMap((item) => item.fonts_used);
  const fontsUsed = [...new Set(visibleFonts.length ? visibleFonts : measurements.flatMap((item) => item.fonts_used))].sort();

  if (fontsUsed.length === 0) {
    throw new Error("Chưa xác định được font thực tế của nhãn.");
  }
  const polygonShapes = [
    "hexagon",
    "lean_right",
    "lean_left",
    "trapezoid",
    "inv_trapezoid",
    "odd",
  ];
  // Registry aliases checked against Mermaid 12.3.0 shapes.ts. The product's
  // legacy "flag" is A>label] => odd, NOT modern @{shape: flag} (paper tape).
  const shapeAliases = new Map([
    ["square", ["rect", "squareRect", "proc", "process", "rectangle"]],
    ["round", ["rounded", "roundedRect", "event"]],
    ["stadium", ["terminal", "pill"]],
    ["subroutine", ["fr-rect", "subprocess", "subproc", "framed-rectangle"]],
    ["cylinder", ["cyl", "db", "database"]],
    ["circle", ["circ"]],
    ["diamond", ["diam", "decision", "question"]],
    ["hexagon", ["hex", "prepare"]],
    ["lean_right", ["lean-r", "lean-right", "in-out"]],
    ["lean_left", ["lean-l", "lean-left", "out-in"]],
    ["trapezoid", ["trap-b", "priority", "trapezoid-bottom"]],
    ["inv_trapezoid", ["trap-t", "manual", "trapezoid-top", "inv-trapezoid"]],
    ["odd", ["rect_left_inv_arrow"]],
    ["doublecircle", ["dbl-circ", "double-circle"]],
  ].flatMap(([internal, aliases]) => [internal, ...aliases].map((alias) => [alias, internal])));
  vertices.forEach((node, index) => {
    const geometry = measurements[index];
    const shape = shapeAliases.get(node.type ?? "square");

    if (
      ![
        "square",
        "round",
        "diamond",
        "circle",
        "stadium",
        "doublecircle",
        "subroutine",
        "cylinder",
        ...polygonShapes,
      ].includes(shape)
    ) {
      throw new SourceError(`Shape chưa được hỗ trợ: ${node.type}, node ${node.id}. Flag legacy dùng A>label] (odd); shape flag hiện đại là paper tape.`);
    }

    let width = Math.max(geometry.logical_box[2], geometry.path_box[2]) + 32;

    let height = Math.max(geometry.logical_box[3], geometry.path_box[3]) + 24;

    if (shape === "diamond" || polygonShapes.includes(shape)) {
      width *= 2;
      height *= 2;
    }

    if (shape === "stadium") {
      // Dành phần giữa đủ rộng cho nhãn, cộng hai đầu bán nguyệt.
      width += height;
    }

    if (shape === "circle" || shape === "doublecircle") {
      const diameter =
        Math.hypot(width, height) + (shape === "doublecircle" ? 12 : 0);

      width = diameter;
      height = diameter;
    }
    if (shape === "subroutine") {
      width += 24;
    }
    if (shape === "cylinder") {
      height += 48;
    }

    graph.setNode(node.id, {
      label: node.text,
      appearance: nodeStyles[index],
      geometry,
      shape,
      width,
      height,
    });
  });

  sourceGroups.forEach((group, index) => {
    graph.setNode(group.id, {
      shape: "square", isSubgraph: true, appearance: groupStyles[index],
      geometry: measurements[vertices.length + edgeLabels.length + index],
    });
  });

  sourceEdges.forEach((edge, ordinal) => {
    const geometry = measurements[vertices.length + ordinal];
    const hasLabel = edgeLabels[ordinal].length > 0;
    const appearance = edgeStyles[ordinal];
    const invisible = edge.stroke === "invisible";

    graph.setEdge(
      edge.start,
      edge.end,
      {
        ordinal,
        appearance,
        invisible,
        arrows: invisible ? [null, null] : arrowTypes[edge.type],
        minlen: Math.max(1, edge.length ?? 1),
        geometry,
        hasLabel,
        label: edgeLabels[ordinal],
        width: hasLabel
          ? Math.max(geometry.logical_box[2], geometry.path_box[2]) + 12
          : 0,
        height: hasLabel
          ? Math.max(geometry.logical_box[3], geometry.path_box[3]) + 8
          : 0,
        labelpos: "c",
      },
      String(ordinal),
    );
  });

  const elkSpacing=Number(process.argv[7]??1);
  if (layoutEngine === 'elk') {
    const {layoutElk}=await import('./elk-layout.mjs');
    await layoutElk(graph,sourceGroups,rankdir,elkSpacing);
  } else layoutSubgraphs(dagre, graph, sourceGroups, rankdir);
  const titleGeometry = measurements.at(-1);
  if (title) {
    const extraWidth = Math.max(0,titleGeometry.path_box[2]+40-graph.graph().width);
    const dx = extraWidth/2, dy = Math.max(titleGeometry.logical_box[3],titleGeometry.path_box[3])+32;
    for (const id of graph.nodes()) {
      const node=graph.node(id);node.x+=dx;node.y+=dy;
      if(node.titlePosition) {node.titlePosition.x+=dx;node.titlePosition.y+=dy;}
    }
    for (const edge of graph.edges()) {
      const data=graph.edge(edge);
      data.points=data.points.map((p)=>({x:p.x+dx,y:p.y+dy}));
      if (data.hasLabel) {data.x+=dx;data.y+=dy;}
    }
    graph.graph().width+=extraWidth;
    graph.graph().height+=dy;
  }
  function polygonPoints(node) {
    const templates = {
      hexagon: [
        [0.25, 0],
        [0.75, 0],
        [1, 0.5],
        [0.75, 1],
        [0.25, 1],
        [0, 0.5],
      ],
      lean_right: [
        [0.25, 0],
        [1, 0],
        [0.75, 1],
        [0, 1],
      ],
      lean_left: [
        [0, 0],
        [0.75, 0],
        [1, 1],
        [0.25, 1],
      ],
      trapezoid: [
        [0.25, 0],
        [0.75, 0],
        [1, 1],
        [0, 1],
      ],
      inv_trapezoid: [
        [0, 0],
        [1, 0],
        [0.75, 1],
        [0.25, 1],
      ],
      odd: [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
        [0.25, 0.5],
      ],
    };
    const template = templates[node.shape];
    if (!template) return null;
    return template.map(([x, y]) => ({
      x: node.x + (x - 0.5) * node.width,
      y: node.y + (y - 0.5) * node.height,
    }));
  }

  function boundaryPoint(node, toward) {
    const dx = toward.x - node.x;
    const dy = toward.y - node.y;

    if (dx === 0 && dy === 0) {
      throw new Error("Không xác định được hướng nối edge.");
    }

    const a = node.width / 2;
    const b = node.height / 2;
    let t;
    if (node.shape === "cylinder") {
      const radius = 12;
      const capCenter = b - radius;

      // Kiểm tra tia có chạm cạnh đứng trước không.
      if (dx !== 0) {
        const sideDistance = a / Math.abs(dx);

        if (Math.abs(dy * sideDistance) <= capCenter) {
          return {
            x: node.x + dx * sideDistance,
            y: node.y + dy * sideDistance,
          };
        }
      }

      // Tìm giao với nửa ellipse ngoài của nắp trên hoặc dưới.
      const coefficientA =
        (dx * dx) / (a * a) +
        (dy * dy) / (radius * radius);

      const coefficientB =
        -2 * Math.abs(dy) * capCenter / (radius * radius);

      const coefficientC =
        (capCenter * capCenter) / (radius * radius) - 1;

      const discriminant =
        coefficientB * coefficientB -
        4 * coefficientA * coefficientC;

      const distance = (
        -coefficientB + Math.sqrt(Math.max(0, discriminant))
      ) / (2 * coefficientA);

      return {
        x: node.x + dx * distance,
        y: node.y + dy * distance,
      };
    }

    const polygon = polygonPoints(node);
    if (polygon) {
      let nearest = Infinity;
      for (let i = 0; i < polygon.length; i++) {
        const start = polygon[i];
        const end = polygon[(i + 1) % polygon.length];
        const sx = end.x - start.x;
        const sy = end.y - start.y;
        const qx = start.x - node.x;
        const qy = start.y - node.y;
        const denominator = dx * sy - dy * sx;
        if (Math.abs(denominator) < 1e-12) continue;
        const distance = (qx * sy - qy * sx) / denominator;
        const position = (qx * dy - qy * dx) / denominator;
        if (distance >= 0 && position >= -1e-9 && position <= 1 + 1e-9) {
          nearest = Math.min(nearest, distance);
        }
      }
      if (!Number.isFinite(nearest)) {
        throw new Error("Không tìm được giao điểm với biên đa giác.");
      }
      return { x: node.x + dx * nearest, y: node.y + dy * nearest };
    }
    if (node.shape === "circle" || node.shape === "doublecircle") {
      t = a / Math.hypot(dx, dy);
    } else if (node.shape === "diamond") {
      t = 1 / (Math.abs(dx) / a + Math.abs(dy) / b);
    } else {
      t = Math.min(
        dx === 0 ? Infinity : a / Math.abs(dx),
        dy === 0 ? Infinity : b / Math.abs(dy),
      );

      // Nếu tia chạm vùng góc bo, tìm giao với cung tròn.
      const radius = node.shape === "stadium" ? b : 8;
      const hitX = Math.abs(dx * t);
      const hitY = Math.abs(dy * t);

      if (
        (node.shape === "round" || node.shape === "stadium") &&
        hitX > a - radius &&
        hitY > b - radius
      ) {
        const cx = a - radius;
        const cy = b - radius;
        const projection = Math.abs(dx) * cx + Math.abs(dy) * cy;
        const lengthSquared = dx * dx + dy * dy;
        const discriminant =
          projection * projection -
          lengthSquared * (cx * cx + cy * cy - radius * radius);

        t = (projection + Math.sqrt(Math.max(0, discriminant))) / lengthSquared;
      }
    }

    return { x: node.x + dx * t, y: node.y + dy * t };
  }

  const namespace = "http://www.w3.org/2000/svg";

  const records = [];
  function attribute(record, key, value) { record.attributes[key] = String(value); }
  function add(parent, tag, attributes = {}) {
    const record = {tag, attributes: {}, children: []};
    for (const [key, value] of Object.entries(attributes)) attribute(record, key, value);
    if (parent) parent.children.push(record);
    records.push(record);
    return record;
  }
  function xml(value) {
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function serialize(record) {
    const attributes = Object.entries(record.attributes).map(([key,value]) => ` ${key}="${xml(value)}"`).join('');
    return `<${record.tag}${attributes}>${record.children.map(serialize).join('')}</${record.tag}>`;
  }
  const svg = add(null, 'svg', {xmlns: namespace});
  if (!/^aiz-mermaid-v1-sha256:[a-f0-9]{64}$/.test(process.env.AIZ_RENDERER_VERSION ?? "")) {
    throw new Error("Backend phải chạy qua Python với RENDERER_VERSION đã ghim.");
  }
  attribute(svg, "data-renderer-version", process.env.AIZ_RENDERER_VERSION);
  attribute(svg, "data-layout-engine", layoutEngine);
  if(requestedLayout==='auto') {
    attribute(svg,'data-layout-requested','auto');
    attribute(svg,'data-layout-policy','size-groups-v1');
    attribute(svg,'data-layout-stats',JSON.stringify(layoutStats));
  }
  if(layoutEngine==='elk' && elkSpacing!==1) attribute(svg,"data-elk-spacing",elkSpacing);
  attribute(svg, "data-edge-postprocessing", "none");
  attribute(svg, "data-edge-routing", layoutEngine === "elk" ? "elk-orthogonal" : "dagre-dijkstra");
  attribute(svg, 
    "viewBox",
    `0 0 ${graph.graph().width} ${graph.graph().height}`,
  );
  attribute(svg, "width", graph.graph().width);
  attribute(svg, "height", graph.graph().height);
  attribute(svg, "font-family", fontsUsed.join(", "));
  attribute(svg, "font-size", fontPx);
  if (palette.background!=="none") add(svg,"rect",{x:0,y:0,width:graph.graph().width,height:graph.graph().height,fill:palette.background,"data-background":"true"});
  function glyphAttributes(geometry, appearance) {
    return {fill:appearance.color,"font-family":geometry.fonts_used.join(", "),
      "font-size":geometry.font_px,"font-weight":geometry.font_weight,"font-style":geometry.font_style};
  }
  if (title) {
    const [bx,by,bw,bh]=titleGeometry.path_box;
    const tx=(graph.graph().width-bw)/2-bx, ty=16-by;
    add(svg,"path",{d:titleGeometry.path,transform:`translate(${tx} ${ty})`,
      "data-title-box":JSON.stringify([bx+tx,by+ty,bw,bh]),
      ...glyphAttributes(titleGeometry,{...globalFont,color:palette.title})});
  }

  const defs = add(svg, "defs");
  // Allocate IDs against every source ID, with deterministic collision resolution.
  const usedIds = new Set([
    ...vertices.map((node) => node.id),
    ...diagram.db.getSubGraphs().map((group) => group.id),
  ]);
  function allocateId(base) {
    let id = base;
    let suffix = 1;
    while (usedIds.has(id)) id = `${base}-${suffix++}`;
    usedIds.add(id);
    return id;
  }
  const markers = new Map();
  function markerFor(type, color, extent) {
    const key = JSON.stringify([type, color, extent]);
    if (markers.has(key)) return markers.get(key);
    const id = allocateId(`aiz-marker-${type}`);
    const marker = add(defs, "marker", {
      id,
      viewBox: "0 -5 8 10",
      refX: 0,
      refY: 0,
      markerWidth: extent,
      markerHeight: extent * 10 / 8,
      markerUnits: "userSpaceOnUse",
      orient: "auto-start-reverse",
      overflow: "visible",
      "data-marker-type": type,
    });
    // Marker geometry spans 8 units in its viewBox, scaled to the space
    // available on the terminal segment.
    if (type === "point") {
      add(marker, "path", { d: "M 0 -4 L 8 0 L 0 4 Z", fill: color });
    } else if (type === "circle") {
      add(marker, "circle", {
        cx: 4, cy: 0, r: 3.25, fill: palette.background === "none" ? "white" : palette.background, stroke: color, "stroke-width": 1.5,
      });
    } else {
      // Inset diagonal endpoints by half the stroke's x projection so the
      // painted cross, including its stroke, ends exactly at x = 8.
      add(marker, "path", {
        d: "M 0.5303300858899106 -3.4696699141100895 L 7.4696699141100895 3.4696699141100895 M 0.5303300858899106 3.4696699141100895 L 7.4696699141100895 -3.4696699141100895",
        fill: "none", stroke: color, "stroke-width": 1.5, "stroke-linecap": "butt",
      });
    }
    markers.set(key, id);
    return id;
  }
  function shortenEndpoint(points, start) {
    const index = start ? 0 : points.length - 1;
    const neighbor = points[start ? 1 : points.length - 2];
    const point = points[index];
    const dx = neighbor.x - point.x;
    const dy = neighbor.y - point.y;
    const distance = Math.hypot(dx, dy);
    if (!Number.isFinite(distance) || distance === 0) {
      throw new Error("Đoạn cuối edge không có hướng hữu hạn để đặt marker.");
    }
    const extent = Math.min(8, distance / 3);
    points[index] = {
      x: point.x + dx * extent / distance,
      y: point.y + dy * extent / distance,
    };
    return extent;
  }

  // Draw real cluster rectangles behind every edge and node, outermost first.
  const nestingDepth = (id) => {
    let depth = 0;
    let parent = sourceGroups.find((g) => g.nodes.includes(id));
    while (parent) { depth++; parent = sourceGroups.find((g) => g.nodes.includes(parent.id)); }
    return depth;
  };
  for (const sourceGroup of [...sourceGroups].sort((a,b) => nestingDepth(a.id)-nestingDepth(b.id))) {
    const node = graph.node(sourceGroup.id);
    const x = node.x-node.width/2, y = node.y-node.height/2;
    const [bx,by,bw,bh] = node.geometry.path_box;
    const tx = (node.titlePosition?.x??node.x)-bx-bw/2, ty = (node.titlePosition?.y??y+14)-by;
    const group = add(svg, "g", {
      id: sourceGroup.id,
      "data-subgraph-box": JSON.stringify([x,y,node.width,node.height]),
      "data-label-box": JSON.stringify([bx+tx,by+ty,bw,bh]),
      "data-direction": sourceGroup.effectiveDirection,
    });
    add(group, "rect", {x,y,width:node.width,height:node.height,...shapePaint(node.appearance)});
    add(group, "path", {d:node.geometry.path,transform:`translate(${tx} ${ty})`,...glyphAttributes(node.geometry,node.appearance)});
  }

  // ELK's off-centre ports must retain their horizontal/vertical approach.
  // A ray from the centre redirects that line and can cut neighbouring nodes.
  function orthogonalBoundaryPoint(node, boundary, neighbor) {
    const horizontal=Math.abs(neighbor.x-boundary.x)>Math.abs(neighbor.y-boundary.y);
    const sign=Math.sign(horizontal?neighbor.x-node.x:neighbor.y-node.y);
    let lo=-Math.PI/2+1e-9,hi=Math.PI/2-1e-9,result;
    for(let i=0;i<48;i++) {
      const angle=(lo+hi)/2;
      const toward=horizontal?{x:node.x+sign*Math.cos(angle)*node.width,y:node.y+Math.sin(angle)*node.height}:
        {x:node.x+Math.sin(angle)*node.width,y:node.y+sign*Math.cos(angle)*node.height};
      result=boundaryPoint(node,toward);
      if((horizontal?result.y-boundary.y:result.x-boundary.x)<0) lo=angle;else hi=angle;
    }
    return horizontal?{x:result.x,y:boundary.y}:{x:boundary.x,y:result.y};
  }

  for (const edge of graph.edges()) {
    const data = graph.edge(edge);
    let points = data.points.map((point) => ({ ...point }));

    if (points.length < 2) {
      throw new Error("Edge thiếu điểm hình học.");
    }
    // Cluster routing already chose a port on the actual rectangle. Leaves
    // still use the exact intersection for their own shape.
    const startPoint = data.clusterRoute && graph.node(edge.v).isSubgraph
      ? points[0] : layoutEngine==='elk' ? orthogonalBoundaryPoint(graph.node(edge.v),points[0],points[1]) : boundaryPoint(graph.node(edge.v), data.points[1]);
    const endPoint = data.clusterRoute && graph.node(edge.w).isSubgraph
      ? points.at(-1) : layoutEngine==='elk' ? orthogonalBoundaryPoint(graph.node(edge.w),points.at(-1),points.at(-2)) : boundaryPoint(graph.node(edge.w), data.points.at(-2));
    points[0] = startPoint;
    points[points.length - 1] = endPoint;
    const [startArrow, endArrow] = data.arrows;
    const markerAttributes = {};
    if (startArrow) {
      const extent = shortenEndpoint(points, true);
      markerAttributes["marker-start"] = `url(#${markerFor(startArrow, data.appearance.markerColor, extent)})`;
    }
    if (endArrow) {
      const extent = shortenEndpoint(points, false);
      markerAttributes["marker-end"] = `url(#${markerFor(endArrow, data.appearance.markerColor, extent)})`;
    }
    const pathData=points.map((p,i)=>`${i===0?'M':'L'} ${p.x} ${p.y}`).join(' ');
    add(svg, "path", {
      "data-source": edge.v,
      "data-target": edge.w,
      "data-ordinal": data.ordinal,
      "data-points": JSON.stringify(points.map(p=>[p.x,p.y])),
      "data-corner-radii": JSON.stringify(points.map(()=>0)),
      d: pathData,
      fill: "none",
      ...Object.fromEntries(Object.entries(shapePaint(data.appearance)).filter(([key])=>key!=="fill")),
      ...markerAttributes,
      ...(data.invisible ? { stroke: "none", visibility: "hidden" } : {}),
    });
  }

  for (const id of graph.nodes()) {
    const node = graph.node(id);
    if (node.isSubgraph) continue;
    const group = add(svg, "g", { id });

    const x = node.x - node.width / 2;
    const y = node.y - node.height / 2;

    attribute(group, 
      "data-node-box",
      JSON.stringify([x, y, node.width, node.height]),
    );

    const appearance = shapePaint(node.appearance);

    const polygon = polygonPoints(node);
    if (node.shape === "cylinder") {
      const radius = 12;
      const halfWidth = node.width / 2;
      const right = x + node.width;
      const topCenter = y + radius;
      const bottomCenter = y + node.height - radius;

      add(group, "path", {
        d: [
          `M ${x} ${topCenter}`,
          `A ${halfWidth} ${radius} 0 0 1 ${right} ${topCenter}`,
          `L ${right} ${bottomCenter}`,
          `A ${halfWidth} ${radius} 0 0 1 ${x} ${bottomCenter}`,
          "Z",
        ].join(" "),
        ...appearance,
      });

      add(group, "ellipse", {
        cx: node.x,
        cy: topCenter,
        rx: halfWidth,
        ry: radius,
        ...appearance,
        fill: "none",
      });
    } else if (polygon) {
      add(group, "polygon", {
        points: polygon.map((point) => `${point.x},${point.y}`).join(" "),
        ...appearance,
      });
    } else if (node.shape === "circle" || node.shape === "doublecircle") {
      add(group, "circle", {
        cx: node.x,
        cy: node.y,
        r: node.width / 2,
        ...appearance,
      });

      if (node.shape === "doublecircle") {
        add(group, "circle", {
          cx: node.x,
          cy: node.y,
          r: node.width / 2 - 6,
          ...appearance,
          fill: "none",
        });
      }
    } else if (node.shape === "diamond") {
      add(group, "polygon", {
        points: [
          `${node.x},${y}`,
          `${x + node.width},${node.y}`,
          `${node.x},${y + node.height}`,
          `${x},${node.y}`,
        ].join(" "),
        ...appearance,
      });
    } else {
      add(group, "rect", {
        x,
        y,
        width: node.width,
        height: node.height,
        rx:
          node.shape === "stadium"
            ? node.height / 2
            : node.shape === "round"
              ? 8
              : 0,
        ...appearance,
      });
    }
    if (node.shape === "subroutine") {
      for (const lineX of [x + 12, x + node.width - 12]) {
        add(group, "line", {
          x1: lineX,
          y1: y,
          x2: lineX,
          y2: y + node.height,
          ...appearance,
          fill: "none",
        });
      }
    }

    const [bx, by, bw, bh] = node.geometry.path_box;

    // Đặt tâm hộp nét chữ vào tâm node.
    const tx = node.x - bx - bw / 2;
    const ty = node.y - by - bh / 2;

    add(group, "path", {
      d: node.geometry.path,
      transform: `translate(${tx} ${ty})`,
      ...glyphAttributes(node.geometry,node.appearance),
    });

    // Hộp đường chữ đã đo, chuyển sang tọa độ SVG.
    attribute(group, 
      "data-label-box",
      JSON.stringify([bx + tx, by + ty, bw, bh]),
    );
  }
  for (const edge of graph.edges()) {
    const data = graph.edge(edge);

    if (!data.hasLabel) continue;

    const [bx, by, bw, bh] = data.geometry.path_box;
    const tx = data.x - bx - bw / 2;
    const ty = data.y - by - bh / 2;

    const group = add(svg, "g", {
      "data-edge-label": data.ordinal,
      "data-label-box": JSON.stringify([bx + tx, by + ty, bw, bh]),
    });

    add(group, "rect", {
      x: data.x - data.width / 2,
      y: data.y - data.height / 2,
      width: data.width,
      height: data.height,
      fill: palette.edgeBackground,
    });

    add(group, "path", {
      d: data.geometry.path,
      transform: `translate(${tx} ${ty})`,
      ...glyphAttributes(data.geometry,data.appearance),
    });
  }

  const nodes = records.filter((r) => r.tag === "g" && "data-node-box" in r.attributes).map((group) => ({
    id: group.attributes.id,
    box: JSON.parse(group.attributes["data-node-box"]),
    label_box: JSON.parse(group.attributes["data-label-box"]),
  }));

  const edgeLabelGroups = records.filter((r) => r.tag === "g" && "data-edge-label" in r.attributes);

  const edges = records.filter((r) => r.tag === "path" && "data-ordinal" in r.attributes).map(
    (line) => {
      const ordinal = Number(line.attributes["data-ordinal"]);
      const label = edgeLabelGroups.find(
        (group) => Number(group.attributes["data-edge-label"]) === ordinal,
      );

      return {
        source: line.attributes["data-source"],
        target: line.attributes["data-target"],
        ordinal,
        points: JSON.parse(line.attributes["data-points"]),
        corner_radii: JSON.parse(line.attributes["data-corner-radii"]),
        label_box: label
          ? JSON.parse(label.attributes["data-label-box"])
          : [0, 0, 0, 0],
      };
    },
  );

  const viewBox = svg.attributes["viewBox"].split(/\s+/).map(Number);

  const layout = {
    width: viewBox[2],
    height: viewBox[3],
    nodes,
    edges,
    subgraphs: sourceGroups.map((sourceGroup) => {
      const group = records.filter((r) => r.tag === "g" && "data-subgraph-box" in r.attributes).find((g) => g.attributes.id === sourceGroup.id);
      return {
        id: sourceGroup.id,
        box: JSON.parse(group.attributes["data-subgraph-box"]),
        label_box: JSON.parse(group.attributes["data-label-box"]),
        members: [...sourceGroup.nodes],
      };
    }),
    font_px: fontPx,
    font_family_used: fontsUsed.join(", "),
  };

  const svgPath = `${workDir}/diagram.svg`;
  const layoutPath = `${workDir}/layout.json`;

  const svgText = serialize(svg);
  const layoutText = JSON.stringify(layout, null, 2) + "\n";
  if (Buffer.byteLength(svgText)>32*1024*1024 || Buffer.byteLength(layoutText)>8*1024*1024) {
    throw Object.assign(new Error("SVG/layout vượt giới hạn kích thước đầu ra."), {code:"limit"});
  }
  await writeFile(svgPath, svgText, "utf8");
  await writeFile(layoutPath, layoutText, "utf8");
  await rename(workDir, destination);
  workDir = undefined;

} catch (error) {
  if (error.code === "ENOBUFS" || error.code === "ERR_CHILD_PROCESS_STDIO_MAXBUFFER") {
    error = Object.assign(new Error("Pango vượt giới hạn kích thước dữ liệu shaping."), {code:"limit"});
  }
  const location = error.hash?.loc;
  const parsedLine = error.kind !== "syntax" ? null : Number.isInteger(error.hash?.line)
    ? error.hash.line + 1
    : Number.isInteger(location?.first_line) ? location.first_line : null;
  const line = parsedLine === null ? null : parserLineMap?.length
    ? parserLineMap[parsedLine-1] ?? Math.min(sourceLineCount, parserLineMap.at(-1)+parsedLine-parserLineMap.length)
    : parsedLine;

  const syntaxError = line !== null;

  console.error(
    JSON.stringify(
      {
        kind: syntaxError ? "syntax" : error instanceof SourceError ? "source" : "engine",
        line,
        code: syntaxError ? "syntax" : error.code ?? (/Cannot find|ModuleNotFound|ImportError|ENOENT/.test(error.message ?? "") ? "dependency" : /maxEdges|Too many edges|exceeds|maxBuffer/.test(error.message ?? "") ? "limit" : "engine"),
        message: syntaxError
          ? (error.message ?? String(error)).replace(/Parse error on line \d+/, `Parse error on line ${line}`)
          : error.message ?? String(error),
      },
      null,
      2,
    ),
  );

  process.exitCode = 1;
} finally {

  if (workDir) {
    await rm(workDir, { recursive: true, force: true });
  }
}

}
