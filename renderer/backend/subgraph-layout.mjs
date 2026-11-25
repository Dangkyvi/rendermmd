import { SourceError } from "./theme-source.mjs";
// Hierarchical composition of the installed Dagre backend. All geometry is in
// final SVG coordinates; no browser measurements or synthetic cluster bounds.
// Hierarchical, port-aware connected placement and obstacle-aware routing.
// Independent siblings use packing; connected scopes never use row wrapping.
// Single-state placement: dependencies order the blocks; estimated boundary
// ports and wires choose their coordinates. There are no rows or wrap budget.
export function layoutConnectedScope(local, targetRatio=16/9) {
  const ids=local.nodes(), edges=local.edges(),order=new Map(ids.map((id,i)=>[id,i]));
  const visible=e=>!local.edge(e).invisible;
  const feedback=new Set(),visiting=new Map();
  function visit(id){visiting.set(id,1);for(const e of local.outEdges(id)??[]){
    if(visiting.get(e.w)===1)feedback.add(e.name);else if(!visiting.has(e.w))visit(e.w);
  }visiting.set(id,2);}
  for(const id of ids)if(!visiting.has(id))visit(id);
  const forward=edges.filter(e=>!feedback.has(e.name));
  const remaining=new Set(ids),sequence=[];
  while(remaining.size){
    const ready=[...remaining].filter(id=>!forward.some(e=>e.w===id&&remaining.has(e.v)));
    if(!ready.length)throw new Error('Không thể phân thứ tự dependency sau khi xử lý vòng lặp.');
    const last=sequence.at(-1);
    const affinity=id=>forward.reduce((s,e)=>s+(e.w===id&&!remaining.has(e.v)?(e.v===last?4:1):0),0);
    ready.sort((a,b)=>affinity(b)-affinity(a)||order.get(a)-order.get(b));
    sequence.push(ready[0]);remaining.delete(ready[0]);
  }
  const gap=48,padding=40,rootRatio=Math.sqrt(targetRatio);
  const scale=Math.max(64,ids.reduce((s,id)=>s+Math.sqrt(local.node(id).width*local.node(id).height),0)/ids.length);
  const rect=(id,pos=local.node(id))=>{const n=local.node(id);return [pos.x-n.width/2,pos.y-n.height/2,pos.x+n.width/2,pos.y+n.height/2];};
  const overlap=(a,b,p=24)=>a[0]<b[2]+p&&a[2]+p>b[0]&&a[1]<b[3]+p&&a[3]+p>b[1];
  const centre=(id,override)=>override?.id===id?override:local.node(id);
  function ports(id,anchor,override){
    const n=local.node(id),c=centre(id,override),b=rect(id,c);
    const ay=Math.max(b[1]+(n.header??0)+16,Math.min(b[3]-16,c.y+(anchor?.y??0)));
    const ax=Math.max(b[0]+16,Math.min(b[2]-16,c.x+(anchor?.x??0)));
    const result=[{x:b[2],y:ay,side:'E'},{x:b[0],y:ay,side:'W'},{x:ax,y:b[3],side:'S'}];
    if(!n.isSubgraph)result.push({x:ax,y:b[1],side:'N'});
    return result;
  }
  const point=(x,y)=>({x,y});
  function hits(a,b,box){return segmentHitsBox(a,b,box);}
  function intersections(path,other){let count=0;
    for(let i=1;i<path.length;i++)for(let j=1;j<other.length;j++){
      const a=path[i-1],b=path[i],c=other[j-1],d=other[j];
      const den=(b.x-a.x)*(d.y-c.y)-(b.y-a.y)*(d.x-c.x);if(Math.abs(den)<1e-8)continue;
      const t=((c.x-a.x)*(d.y-c.y)-(c.y-a.y)*(d.x-c.x))/den;
      const u=((c.x-a.x)*(b.y-a.y)-(c.y-a.y)*(b.x-a.x))/den;
      if(t>1e-7&&t<1-1e-7&&u>1e-7&&u<1-1e-7)count++;
    }return count;
  }
  function wire(e,placed,override){
    const data=local.edge(e);let best;
    for(const a of ports(e.v,data.sourceAnchor,override))for(const b of ports(e.w,data.targetAnchor,override)){
      // A small set of orthogonal port paths evaluates one block position;
      // this is not a set of alternative complete graph layouts.
      const lead=(p)=>({x:p.x+(p.side==='E'?16:p.side==='W'?-16:0),y:p.y+(p.side==='S'?16:p.side==='N'?-16:0)});
      const p=lead(a),q=lead(b);
      const horizontal=[a,p,point((p.x+q.x)/2,p.y),point((p.x+q.x)/2,q.y),q,b];
      const vertical=[a,p,point(p.x,(p.y+q.y)/2),point(q.x,(p.y+q.y)/2),q,b];
      for(const path of [horizontal,vertical]){
        let blocked=0;
        for(const id of placed)if(id!==e.v&&id!==e.w){const box=rect(id,centre(id,override));
          if(path.slice(1).some((p,i)=>hits(path[i],p,box)))blocked++;
        }
        const cost=routeLength(path)+blocked*scale*8;
        if(!best||cost<best.cost)best={path,cost,blocked,a,b};
      }
    }
    return best;
  }
  function energy(placed,override){
    const boxes=[...placed].map(id=>rect(id,centre(id,override)));
    const width=Math.max(...boxes.map(b=>b[2]))-Math.min(...boxes.map(b=>b[0]));
    const height=Math.max(...boxes.map(b=>b[3]))-Math.min(...boxes.map(b=>b[1]));
    let value=.24*(width/rootRatio+height*rootRatio)+.7*Math.abs(width/rootRatio-height*rootRatio),paths=[];
    for(const e of edges)if(placed.has(e.v)&&placed.has(e.w)&&e.v!==e.w&&visible(e)){
      const w=wire(e,placed,override),weight=feedback.has(e.name)?.25:1;
      value+=weight*w.cost;
      if(!feedback.has(e.name)){
        const a=centre(e.v,override),b=centre(e.w,override);
        // Prefer a flow that advances right or down, without prescribing rows.
        if(b.x<a.x&&b.y<a.y)value+=4*(a.x-b.x+a.y-b.y);
        // A forward connection should not send the eye back upwards between
        // its actual attachment ports merely because the target is to the right.
        value+=2*Math.max(0,w.a.y-w.b.y);
      }
      for(const old of paths)value+=intersections(w.path,old)*scale*2;
      paths.push(w.path);
    }
    return value;
  }
  function legal(id,pos,placed){const b=rect(id,pos);return ![...placed].some(other=>other!==id&&overlap(b,rect(other),24));}
  const placed=new Set();
  for(const id of sequence){
    const n=local.node(id);
    if(!placed.size){Object.assign(n,{x:n.width/2,y:n.height/2});placed.add(id);continue;}
    const incoming=edges.filter(e=>e.w===id&&placed.has(e.v)&&!feedback.has(e.name));
    const neighbours=incoming.length?incoming:edges.filter(e=>(e.v===id&&placed.has(e.w))||(e.w===id&&placed.has(e.v)));
    const candidates=[];
    for(const e of neighbours){
      const other=e.v===id?e.w:e.v,p=local.node(other),d=local.edge(e);
      const a=e.v===other?d.sourceAnchor:d.targetAnchor,b=e.v===other?d.targetAnchor:d.sourceAnchor;
      const gx=Math.max(gap,(d.width??0)+32),gy=Math.max(gap,(d.height??0)+32);
      candidates.push({id,x:p.x+p.width/2+gx+n.width/2,y:p.y+(a?.y??0)-(b?.y??0)},
        {id,x:p.x+(a?.x??0)-(b?.x??0),y:p.y+p.height/2+gy+n.height/2});
    }
    const boxes=[...placed].map(id=>rect(id)),right=Math.max(...boxes.map(b=>b[2])),bottom=Math.max(...boxes.map(b=>b[3]));
    candidates.push({id,x:right+gap+n.width/2,y:n.height/2},{id,x:n.width/2,y:bottom+gap+n.height/2});
    // Project colliding proposals to adjacent free space, preserving their
    // connection-derived alignment whenever a free position is available.
    const feasible=[];
    for(const candidate of candidates)for(const axis of ['x','y']){
      const p={...candidate};
      for(let attempt=0;attempt<=placed.size;attempt++){
        const colliding=[...placed].filter(other=>overlap(rect(id,p),rect(other),24));
        if(!colliding.length){feasible.push(p);break;}
        if(axis==='x')p.x=Math.max(...colliding.map(other=>rect(other)[2]))+gap+n.width/2;
        else p.y=Math.max(...colliding.map(other=>rect(other)[3]))+gap+n.height/2;
      }
    }
    const all=new Set([...placed,id]);let best=null,bestEnergy=Infinity;
    for(const p of feasible){const cost=energy(all,p);if(cost<bestEnergy-1e-7){best=p;bestEnergy=cost;}}
    if(!best)throw new Error('Không tìm được vị trí khối không chồng lấn.');
    Object.assign(n,{x:best.x,y:best.y});placed.add(id);
  }
  // Coordinate relaxation changes this same layout, using connected port
  // positions. Only strictly improving, collision-free moves are committed.
  function relax(){
    for(const id of [...sequence,...sequence.slice().reverse()]){
      const n=local.node(id),moves=[];
      for(const e of edges)if(e.v!==e.w&&(e.v===id||e.w===id)&&visible(e)&&!feedback.has(e.name)){
        const other=e.v===id?e.w:e.v,p=local.node(other),d=local.edge(e),w=wire(e,placed);
        const self=e.v===id?w.a:w.b,neighbour=e.v===id?w.b:w.a;
        moves.push({id,x:n.x,y:n.y+neighbour.y-self.y},{id,x:n.x+neighbour.x-self.x,y:n.y});
        if(e.w===id)moves.push({id,x:p.x+p.width/2+Math.max(gap,(d.width??0)+32)+n.width/2,y:n.y},
          {id,x:n.x,y:p.y+p.height/2+Math.max(gap,(d.height??0)+32)+n.height/2});
      }
      let current=energy(placed),best=null;
      for(const p of moves)if(legal(id,p,placed)){
        const cost=energy(placed,p);if(cost<current-1e-7){current=cost;best=p;}
      }
      if(best)Object.assign(n,{x:best.x,y:best.y});
    }
  }
  relax();
  // Probe real obstacle-avoiding paths, then feed long detours back into the
  // position stage before final rendering. Labels and exact leaf clipping are
  // still handled by the normal renderer after this bounded feedback pass.
  let probes=0,feedbackChanges=0;
  function probe(e,override){
    const estimate=wire(e,placed,override),a=estimate.a,b=estimate.b;
    const lead=p=>({x:p.x+(p.side==='E'?16:p.side==='W'?-16:0),y:p.y+(p.side==='S'?16:p.side==='N'?-16:0)});
    const obstacles=ids.map(id=>Object.assign(rect(id,centre(id,override)),{endpoint:id}));
    const bs=ids.map(id=>rect(id,centre(id,override)));
    const frame=[Math.min(...bs.map(b=>b[0]))-padding,Math.min(...bs.map(b=>b[1]))-padding,Math.max(...bs.map(b=>b[2]))+padding,Math.max(...bs.map(b=>b[3]))+padding];
    try{
      const path=orthogonalRoute([{boundary:a,gate:lead(a),node:e.v}],[{boundary:b,gate:lead(b),node:e.w}],obstacles,frame);
      return {length:routeLength(path),extra:Math.max(0,routeLength(path)-routeLength(estimate.path))};
    }catch(error){if(!error.message.includes('Không tìm được đường edge'))throw error;return {length:Infinity,extra:scale*12};}
  }
  const probeEdges=edges.filter(e=>e.v!==e.w&&visible(e)&&!feedback.has(e.name))
    .map(e=>({e,weight:wire(e,placed).cost})).sort((a,b)=>b.weight-a.weight).slice(0,6);
  for(const {e} of probeEdges){
    probes++;const actual=probe(e);
    if(actual.extra<48)continue;
    const n=local.node(e.w),p=local.node(e.v),d=local.edge(e);
    const moves=[{id:e.w,x:p.x+p.width/2+Math.max(gap,(d.width??0)+32)+n.width/2,y:p.y},
      {id:e.w,x:p.x,y:p.y+p.height/2+Math.max(gap,(d.height??0)+32)+n.height/2},
      {id:e.v,x:n.x-n.width/2-Math.max(gap,(d.width??0)+32)-p.width/2,y:p.y},
      {id:e.v,x:p.x,y:n.y-n.height/2-Math.max(gap,(d.height??0)+32)-p.height/2}];
    let best=null,value=energy(placed)+actual.extra;
    for(const move of moves)if(legal(move.id,move,placed)){
      const cost=energy(placed,move)+probe(e,move).extra;
      if(cost<value-1e-7){value=cost;best=move;}
    }
    if(best){Object.assign(local.node(best.id),{x:best.x,y:best.y});feedbackChanges++;}
  }
  const boxes=ids.map(id=>rect(id)),dx=padding-Math.min(...boxes.map(b=>b[0])),dy=padding-Math.min(...boxes.map(b=>b[1]));
  for(const id of ids){local.node(id).x+=dx;local.node(id).y+=dy;}
  let width=Math.max(...ids.map(id=>rect(id)[2]))+padding,height=Math.max(...ids.map(id=>rect(id)[3]))+padding;
  // Label rectangles first try the actual estimated connector midpoint. Only
  // labels without a free slot use the reserved strip below the blocks.
  const occupied=ids.map(id=>rect(id)),labelBoxes=[];let shelfX=padding,shelfY=height,shelfH=0;
  for(const e of edges){const d=local.edge(e);d.folded=true;d.flowOrder=feedback.has(e.name)?2:0;
    const selected=wire(e,placed);d.portPlan={source:selected.a.side,target:selected.b.side};
    if(d.width>0&&d.height>0){
      const c={x:(selected.a.x+selected.b.x)/2,y:(selected.a.y+selected.b.y)/2};
      const b=[c.x-d.width/2-10,c.y-d.height/2-10,c.x+d.width/2+10,c.y+d.height/2+10];
      if(b[0]>=12&&b[1]>=12&&!occupied.some(o=>overlap(b,o,0))&&!labelBoxes.some(o=>overlap(b,o,0))){d.x=c.x;d.y=c.y;labelBoxes.push(b);width=Math.max(width,b[2]+padding);height=Math.max(height,b[3]+padding);}
      else{
        width=Math.max(width,d.width+padding*2+20);
        if(shelfX+d.width+padding>width){shelfX=padding;shelfY+=shelfH+28;shelfH=0;}
        d.x=shelfX+d.width/2;d.y=shelfY+d.height/2;shelfX+=d.width+28;shelfH=Math.max(shelfH,d.height);
        labelBoxes.push([d.x-d.width/2-10,d.y-d.height/2-10,d.x+d.width/2+10,d.y+d.height/2+10]);
      }
    }
  }
  local.graph().width=Math.max(width,shelfX+padding);local.graph().height=shelfH>0?Math.max(height,shelfY+shelfH+padding):height;
  local.graph().wireAware=true;local.graph().placementStats={blocks:ids.length,probeCount:probes,feedbackMoves:feedbackChanges};
  return true;
}

export function foldDagreScope(local, direction, targetRatio = 16 / 9) {
  // Count direct child groups and distinct leaf nodes connected to those
  // groups. Repeated/parallel edges must not inflate the node threshold.
  const groups = new Set(local.nodes().filter(id => local.node(id).isSubgraph));
  const connectedNodes = new Set();
  for (const edge of local.edges()) {
    if (local.edge(edge).invisible) continue;
    if (groups.has(edge.v) && !groups.has(edge.w)) connectedNodes.add(edge.w);
    if (groups.has(edge.w) && !groups.has(edge.v)) connectedNodes.add(edge.v);
  }
  if (groups.size < 3 && !(groups.size === 2 && connectedNodes.size >= 4)) return false;
  const size = local.graph();
  // Independent siblings have no flow order to preserve. Pack them directly
  // into rows instead of keeping Dagre's single, potentially very wide rank.
  if (local.edgeCount() === 0) {
    const nodes = local.nodes().map(id => local.node(id));
    const gap = 36, margin = 28;
    const area = nodes.reduce((sum, d) => sum + (d.width + gap) * (d.height + gap), 0);
    const limit = Math.max(...nodes.map(d => d.width), Math.sqrt(area * targetRatio));
    let x = margin, y = margin, rowHeight = 0, width = 0;
    for (const d of nodes) {
      if (x > margin && x + d.width > margin + limit) {
        y += rowHeight + gap; x = margin; rowHeight = 0;
      }
      d.x = x + d.width / 2; d.y = y + d.height / 2;
      x += d.width + gap; rowHeight = Math.max(rowHeight, d.height);
      width = Math.max(width, x - gap + margin);
    }
    size.width = width; size.height = y + rowHeight + margin;
    size.folded = true;
    return true;
  }
  return layoutConnectedScope(local,targetRatio);
}

export function layoutSubgraphs(dagre, graph, groups, rankdir) {
  const root = Symbol('root');
  const groupById = new Map(groups.map((g) => [g.id, g]));
  const parent = new Map();
  for (const group of groups) {
    for (const id of group.nodes) {
      if (!graph.hasNode(id)) throw new Error(`Subgraph ${group.id}: member không tồn tại: ${id}`);
      if (parent.has(id) && parent.get(id) !== group.id) {
        throw new SourceError(`Node/subgraph ${id} có nhiều parent.`, "source_structure");
      }
      parent.set(id, group.id);
    }
  }
  for (const id of graph.nodes()) if (!parent.has(id)) parent.set(id, root);
  function ancestors(id) {
    const result = [];
    const seen = new Set();
    while (id !== root) {
      if (seen.has(id)) throw new SourceError('Cây subgraph có chu trình.', 'source_structure');
      seen.add(id);
      result.push(id);
      id = parent.get(id);
    }
    return [...result, root];
  }
  for (const id of graph.nodes()) ancestors(id);
  const contains = (group, id) => ancestors(id).includes(group);
  const children = new Map([[root, []], ...groups.map((g) => [g.id, []])]);
  for (const id of graph.nodes()) children.get(parent.get(id)).push(id);
  const edges = graph.edges();
  // A connection to the cluster itself does not disable its own direction.
  for (const group of groups) {
    group.external = edges.some((e) =>
      (e.v !== group.id && contains(group.id, e.v)) !==
      (e.w !== group.id && contains(group.id, e.w)) &&
      e.v !== group.id && e.w !== group.id);
  }
  const normalize = (dir) => dir === 'TD' ? 'TB' : dir;
  function scopeOf(edge) {
    const left = ancestors(parent.get(edge.v));
    const right = new Set(ancestors(parent.get(edge.w)));
    return left.find((id) => right.has(id));
  }
  function project(id, scope) {
    if (id === scope) return null;
    while (parent.get(id) !== scope) id = parent.get(id);
    return id;
  }
  const scopes = new Map(edges.map((e) => [e.name, scopeOf(e)]));
  const localGraphs = new Map();
  function internalAnchor(id,container){
    if(id===container)return {x:0,y:(graph.node(id).header??0)/2};
    const path=[];let current=id;
    while(current!==container){path.push(current);current=parent.get(current);}
    path.reverse();let x=-graph.node(container).width/2,y=-graph.node(container).height/2;
    current=container;
    for(const child of path){
      const scope=localGraphs.get(current),position=scope.local.node(child);
      x+=scope.dx+position.x;y+=scope.dy+position.y;
      if(child!==id){x-=graph.node(child).width/2;y-=graph.node(child).height/2;}
      current=child;
    }
    return {x,y};
  }
  function compose(scope, inherited) {
    const group = groupById.get(scope);
    const direction = normalize(group && !group.external ? group.dir ?? inherited : inherited);
    if (!['TB','BT','LR','RL'].includes(direction)) throw new SourceError(`Direction subgraph chưa hỗ trợ: ${direction}`, "source_structure");
    if (group) group.effectiveDirection = direction;
    for (const id of children.get(scope)) if (groupById.has(id)) compose(id, direction);
    const local = new dagre.graphlib.Graph({ multigraph: true });
    local.setGraph({rankdir: direction, nodesep: 36, ranksep: 64, marginx: 28, marginy: 28});
    local.setDefaultEdgeLabel(() => ({}));
    for (const id of children.get(scope)) {
      const {width, height} = graph.node(id);
      local.setNode(id, {width, height, header:graph.node(id).header??0, isSubgraph: !!graph.node(id).isSubgraph});
    }
    for (const edge of edges) {
      if (scopes.get(edge.name) !== scope) continue;
      const v = project(edge.v, scope), w = project(edge.w, scope);
      if (v === null || w === null || (v === w && edge.v !== edge.w)) continue;
      const data = graph.edge(edge);
      local.setEdge(v, w, {width:data.width, height:data.height, labelpos:'c', minlen:data.minlen, invisible:data.invisible,
        sourceAnchor:internalAnchor(edge.v,v),targetAnchor:internalAnchor(edge.w,w)}, edge.name);
    }
    if (local.nodeCount()) {
      dagre.layout(local);
      foldDagreScope(local, direction);
    }
    else local.setGraph({...local.graph(), width:56, height:40});
    let width = local.graph().width, height = local.graph().height;
    let dx = 0, dy = 0;
    if (group) {
      const geometry = graph.node(scope).geometry;
      group.header = Math.max(geometry.logical_box[3], geometry.path_box[3]) + 28;
      const extra = Math.max(0, Math.max(geometry.logical_box[2], geometry.path_box[2]) + 48 - width);
      dx = extra / 2;
      dy = group.header;
      width += extra;
      height += group.header;
      Object.assign(graph.node(scope), {width, height, header:group.header});
    }
    localGraphs.set(scope, {local, dx, dy, width, height});
  }
  compose(root, rankdir);
  function place(scope, ox, oy) {
    const {local, dx, dy} = localGraphs.get(scope);
    for (const id of local.nodes()) {
      const position = local.node(id), data = graph.node(id);
      data.x = ox + dx + position.x;
      data.y = oy + dy + position.y;
      if (groupById.has(id)) place(id, data.x - data.width/2, data.y - data.height/2);
    }
    for (const edge of local.edges()) {
      const original = edges.find((e) => e.name === edge.name);
      const data = graph.edge(original), route = local.edge(edge);
      const translate = (p) => ({x:p.x + ox + dx, y:p.y + oy + dy});
      data.points = route.points.map(translate);
      data.flowOrder = route.flowOrder ?? 0;
      data.preferredPorts=route.portPlan?{
        source:edge.v===original.v?route.portPlan.source:null,
        target:edge.w===original.w?route.portPlan.target:null}:null;
      if (data.hasLabel) Object.assign(data, translate(route));
      data.direct = !route.folded && edge.v === original.v && edge.w === original.w &&
        !groupById.has(edge.v) && !groupById.has(edge.w);
    }
  }
  place(root, 0, 0);
  const size = localGraphs.get(root);
  // Integer viewport bounds avoid a near-integer float being rounded
  // differently by librsvg and the Python raster-size contract.
  size.width = Math.ceil(size.width); size.height = Math.ceil(size.height);
  graph.graph().width = size.width;
  graph.graph().height = size.height;
  const box = (id, padding = 0) => {
    const n = graph.node(id);
    return [n.x-n.width/2-padding, n.y-n.height/2-padding,
            n.x+n.width/2+padding, n.y+n.height/2+padding];
  };
  const labelBoxes = edges.filter((e) => graph.edge(e).hasLabel && Number.isFinite(graph.edge(e).x))
    .map((e) => {
      const d = graph.edge(e);
      return {ordinal:d.ordinal, box:[d.x-d.width/2-CLEARANCE,d.y-d.height/2-CLEARANCE,d.x+d.width/2+CLEARANCE,d.y+d.height/2+CLEARANCE]};
    });
  // Local Dagre paths and earlier routed edges occupy space, without becoming
  // hard obstacles: crossings remain possible when the topology requires them.
  const wires=edges.filter(e=>graph.edge(e).direct&&!graph.edge(e).invisible).map(e=>graph.edge(e).points);
  const routingEdges = [...edges].sort((a,b) =>
    (graph.edge(a).flowOrder ?? 0) - (graph.edge(b).flowOrder ?? 0) ||
    graph.edge(a).ordinal - graph.edge(b).ordinal);
  for (const edge of routingEdges) {
    const data = graph.edge(edge);
    if (data.direct) continue;
    const scope = scopes.get(edge.name);
    const frame = scope === root ? [2,2,size.width-2,size.height-2] : (() => {
      const b = box(scope); return [b[0]+8,b[1]+graph.node(scope).header,b[2]-8,b[3]-8];
    })();
    const obstacles = [];
    for (const id of graph.nodes()) {
      if (groupById.has(id)) {
        const endpointAncestor = (id !== edge.v && contains(id, edge.v)) ||
          (id !== edge.w && contains(id, edge.w));
        if (endpointAncestor) {
          obstacles.push(...ancestorObstacles(box(id), graph.node(id).header));
        }
        else if (id===edge.v||id===edge.w) obstacles.push(box(id),...ancestorObstacles(box(id),graph.node(id).header));
        else obstacles.push(box(id,CLEARANCE));
      } else {
        const obstacle=box(id,CLEARANCE);
        if(id===edge.v||id===edge.w) obstacle.endpoint=id;
        obstacles.push(obstacle);
      }
    }
    for (const label of labelBoxes) if (label.ordinal !== data.ordinal) obstacles.push(label.box);
    function ports(id, other, preferred) {
      const n = graph.node(id), b = box(id);
      const into = groupById.has(id) && id !== other && contains(id, other);
      const direction = into ? -1 : 1;
      const cy = n.y + (n.header ?? 0)/2;
      const candidates = [
        [{x:b[0],y:cy},{x:b[0]-direction*16,y:cy}],
        [{x:b[2],y:cy},{x:b[2]+direction*16,y:cy}],
        [{x:n.x,y:b[3]},{x:n.x,y:b[3]+direction*16}],
      ];
      if (!groupById.has(id)) candidates.push([{x:n.x,y:b[1]},{x:n.x,y:b[1]-16}]);
      else {
        // Offer ports near the other endpoint instead of forcing entry at the
        // middle of a tall cluster. Keep the complete title strip protected.
        const otherNode=graph.node(other);
        const y=Math.max(b[1]+n.header+CLEARANCE+16,Math.min(b[3]-CLEARANCE-16,otherNode.y));
        if(y>=b[1]+n.header+CLEARANCE+16 && y<=b[3]-CLEARANCE-16) {
          candidates.push([{x:b[0],y},{x:b[0]-direction*16,y}],
                          [{x:b[2],y},{x:b[2]+direction*16,y}]);
        }
      }
      const otherNode = graph.node(other);
      candidates.sort((a,b) =>
        Math.abs(a[1].x-otherNode.x)+Math.abs(a[1].y-otherNode.y) -
        Math.abs(b[1].x-otherNode.x)-Math.abs(b[1].y-otherNode.y));
      return candidates.map(([boundary,gate]) => {
        const side=boundary.x===b[0]?'W':boundary.x===b[2]?'E':boundary.y===b[3]?'S':'N';
        return {boundary,gate,node:id,bias:preferred&&side!==preferred?16:0};
      });
    }
    let starts = ports(edge.v, edge.w, data.preferredPorts?.source), ends = ports(edge.w, edge.v, data.preferredPorts?.target);
    if (edge.v === edge.w) {
      starts = [starts.find(p => p.boundary.x === box(edge.v)[2]) ?? starts[0]];
      ends = [ends.find(p => p.boundary.y === box(edge.w)[3]) ?? ends.at(-1)];
    }
    // Endpoints which are clusters use their actual rectangular boundary.
    // Leaf endpoints are clipped against the existing shape implementation later.
    function routeFor(...args) {
      try { return orthogonalRoute(...args,{wires}); }
      catch(e) { throw new Error(`Edge ${edge.v} -> ${edge.w}: ${e.message}`); }
    }
    let route;
    if (data.hasLabel && Number.isFinite(data.x)) {
      const waypoint = {x:data.x,y:data.y};
      const left = routeFor(starts, [{gate:waypoint,boundary:waypoint}], obstacles, frame);
      const right = routeFor([{gate:waypoint,boundary:waypoint}], ends, obstacles, frame);
      route = [...left, ...right.slice(1)];
      if(edge.v!==edge.w) {
        // Dagre positions labels on projected cluster edges, not on the final
        // port route. Try the ordinary shortest route and move the label onto
        // a free straight segment only when this removes an actual detour.
        // Any failed optional adjustment leaves the valid labelled route.
        try {
          const direct=routeFor(starts,ends,obstacles,frame);
          if(routeLength(direct)<routeLength(route)-1e-6) {
            const otherRoutes=edges.filter(e=>e.name!==edge.name &&
              (graph.edge(e).direct||graph.edge(e).clusterRoute)).map(e=>graph.edge(e).points);
            const candidate=labelOnRoute(direct,data.width,data.height,obstacles,frame,otherRoutes) ??
              labelOnRoute(route,data.width,data.height,obstacles,frame,otherRoutes,direct);
            if(candidate) {
              const port={gate:candidate.position,boundary:candidate.position};
              const before=routeFor(starts,[port],obstacles,frame);
              const after=routeFor([port],ends,obstacles,frame);
              const adjusted=[...before,...after.slice(1)];
              if(routeLength(adjusted)<routeLength(route)-1e-6) {
                route=adjusted;
                Object.assign(data,candidate.position);
                labelBoxes.find(l=>l.ordinal===data.ordinal).box=candidate.box;
              }
            }
          }
        } catch(error) {
          // Only routing infeasibility is optional; programming errors surface.
          if(!error.message.includes('Không tìm được đường edge')) throw error;
        }
      }
    } else {
      route = routeFor(starts, ends, obstacles, frame);
      if (data.hasLabel) {
        // Ancestor/descendant edges have no projected rank edge. Place their
        // label on a free segment of the actual routed path or fail explicitly.
        let position;
        for (let i=1; i<route.length; i++) {
          const a=route[i-1], b=route[i];
          const x=(a.x+b.x)/2, y=(a.y+b.y)/2;
          const candidate=[x-data.width/2-CLEARANCE,y-data.height/2-CLEARANCE,x+data.width/2+CLEARANCE,y+data.height/2+CLEARANCE];
          if (!obstacles.some((o) => rectanglesOverlap(o,candidate)) &&
              candidate[0]>=frame[0] && candidate[1]>=frame[1] && candidate[2]<=frame[2] && candidate[3]<=frame[3]) {
            position={x,y}; route.splice(i,0,position); break;
          }
        }
        if (!position) throw new Error(`Edge ${data.ordinal}: không đủ chỗ cho nhãn nối ancestor/descendant subgraph.`);
        Object.assign(data,position);
        labelBoxes.push({ordinal:data.ordinal,box:[data.x-data.width/2-CLEARANCE,data.y-data.height/2-CLEARANCE,data.x+data.width/2+CLEARANCE,data.y+data.height/2+CLEARANCE]});
      }
    }
    data.points = simplify(route, [route[1],route.at(-2), ...(data.hasLabel ? [{x:data.x,y:data.y}] : [])]);
    data.clusterRoute = true;
    if(!data.invisible) wires.push(data.points);
  }
}

export const CLEARANCE = 10;

const routeLength=points=>points.slice(1).reduce((sum,p,i)=>sum+Math.abs(p.x-points[i].x)+Math.abs(p.y-points[i].y),0);

// Place a label on the actual route, outside endpoint leads, keeping its whole
// clearance box free. Bounded candidates per segment avoid pairwise searches.
export function labelOnRoute(points,width,height,obstacles,frame,otherRoutes=[],preferredRoute=null,options={}) {
  const across=options.allowAcrossGates===true;
  const route=simplify(points,across?[]:[points[1],points.at(-2)]);
  const candidates=[];
  let travelled=0;
  const total=routeLength(route);
  for(let i=1;i<route.length;i++) {
    const a=route[i-1],b=route[i],length=Math.abs(b.x-a.x)+Math.abs(b.y-a.y);
    if((across || i>1 && i<route.length-1) && length>0) {
      const horizontal=a.y===b.y, margin=(horizontal?width:height)/2+CLEARANCE;
      if(across || length>=margin*2) for(const distance of [length/2,Math.min(margin,length),Math.max(0,length-margin)]) {
        if(across){
          const first=Math.abs(points[1].x-points[0].x)+Math.abs(points[1].y-points[0].y);
          const last=Math.abs(points.at(-1).x-points.at(-2).x)+Math.abs(points.at(-1).y-points.at(-2).y);
          if(travelled+distance<=first+1e-7||travelled+distance>=total-last-1e-7)continue;
        }
        const t=distance/length,position={x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t};
        const box=[position.x-width/2-CLEARANCE,position.y-height/2-CLEARANCE,
                   position.x+width/2+CLEARANCE,position.y+height/2+CLEARANCE];
        if(box[0]<frame[0]||box[1]<frame[1]||box[2]>frame[2]||box[3]>frame[3]||
           obstacles.some(o=>rectanglesOverlap(o,box))||
           otherRoutes.some(ps=>ps.slice(1).some((p,j)=>segmentHitsBox(ps[j],p,box)))) continue;
        const score=preferredRoute ? Math.min(...preferredRoute.slice(1).map((q,j)=>{
          const p=preferredRoute[j],dx=q.x-p.x,dy=q.y-p.y;
          const t=Math.max(0,Math.min(1,((position.x-p.x)*dx+(position.y-p.y)*dy)/(dx*dx+dy*dy||1)));
          return Math.hypot(position.x-p.x-dx*t,position.y-p.y-dy*t);
        })) : Math.abs(travelled+distance-total/2);
        candidates.push({position,box,index:i,score});
      }
    }
    travelled+=length;
  }
  candidates.sort((a,b)=>a.score-b.score);
  const best=candidates[0];
  if(!best) return null;
  const result=[...(across?points:route)];
  if(across){
    if(!result.some(p=>Math.hypot(p.x-best.position.x,p.y-best.position.y)<1e-7)){
      const index=result.findIndex((b,i)=>i>0&&Math.abs((b.x-result[i-1].x)*(best.position.y-result[i-1].y)-(b.y-result[i-1].y)*(best.position.x-result[i-1].x))<1e-7&&best.position.x>=Math.min(b.x,result[i-1].x)-1e-7&&best.position.x<=Math.max(b.x,result[i-1].x)+1e-7&&best.position.y>=Math.min(b.y,result[i-1].y)-1e-7&&best.position.y<=Math.max(b.y,result[i-1].y)+1e-7);
      if(index<1)return null;result.splice(index,0,best.position);
    }
  }else result.splice(best.index,0,best.position);
  return {points:result,position:best.position,box:best.box};
}

// Border bands permit transverse crossings for endpoint ancestors, but never
// a route parallel to their painted border. Titles remain solid obstacles.
export function ancestorObstacles(b, header) {
  const c=CLEARANCE;
  const band=(box,crossing)=>Object.assign(box,{crossing});
  return [[b[0]-c,b[1]-c,b[2]+c,b[1]+header-5+c],
    band([b[0]-c,b[1],b[0]+c,b[3]+c],'x'),
    band([b[2]-c,b[1],b[2]+c,b[3]+c],'x'),
    band([b[0]-c,b[3]-c,b[2]+c,b[3]+c],'y')];
}

// Open-rectangle intersection (Liang–Barsky), including the entire segment.
// Touching the inflated boundary is safe: clearance includes stroke allowance.
export function segmentHitsBox(a,b,box) {
  let lo=0,hi=1;
  for (const [v,d,min,max] of [[a.x,b.x-a.x,box[0]+1e-7,box[2]-1e-7],
                              [a.y,b.y-a.y,box[1]+1e-7,box[3]-1e-7]]) {
    if (Math.abs(d)<1e-12) {if (v<=min || v>=max) return false;}
    else {const t1=(min-v)/d,t2=(max-v)/d;lo=Math.max(lo,Math.min(t1,t2));hi=Math.min(hi,Math.max(t1,t2));}
  }
  return lo<hi;
}
export function segmentClear(a,b,obstacles) {
  return !obstacles.some(o=>segmentHitsBox(a,b,o) &&
    (!o.crossing || (o.crossing==='x' ? Math.abs(b.x-a.x)<Math.abs(b.y-a.y)+1e-7 :
                                                     Math.abs(b.y-a.y)<Math.abs(b.x-a.x)+1e-7)));
}

function rectanglesOverlap(a,b) {
  return a[0]<b[2] && a[2]>b[0] && a[1]<b[3] && a[3]>b[1];
}
function simplify(points, protectedPoints=[]) {
  const result=[];
  for (const p of points) {
    if (result.length && p.x===result.at(-1).x && p.y===result.at(-1).y) continue;
    while (result.length>1) {
      const a=result.at(-2),b=result.at(-1);
      if(protectedPoints.some(p=>p.x===b.x&&p.y===b.y)) break;
      if ((a.x===b.x && b.x===p.x && (b.y-a.y)*(p.y-b.y)>=0) ||
          (a.y===b.y && b.y===p.y && (b.x-a.x)*(p.x-b.x)>=0)) result.pop();
      else break;
    }
    result.push(p);
  }
  return result;
}

// Dijkstra on (grid point, incoming axis), not just a grid point. All costs
// Full step costs stay nonnegative: length + bends + wire penalties minus
// a bounded discount for safely spaced parallel runs.
// Existing wires are soft costs; nodes, group titles and label boxes stay hard.
export function orthogonalRoute(starts, ends, obstacles, frame, options={}) {
  const wires=options.wires??[],lane=options.laneSpacing??12;
  if(!Number.isFinite(lane)||lane<12||lane>256)throw new Error('laneSpacing phải từ 12 đến 256.');
  const parallelPreference=Math.max(0,Math.min(.25,options.parallelPreference??.15));
  const bendPenalty=options.bendPenalty??24;
  const sharedPenalty=options.sharedPenalty??40;
  const nearPenalty=options.nearPenalty??2;
  const crossingPenalty=options.crossingPenalty??120;
  const inside = (p,b) => p.x>b[0]+1e-7 && p.x<b[2]-1e-7 && p.y>b[1]+1e-7 && p.y<b[3]-1e-7;
  const valid = (p) => p.x>=frame[0] && p.x<=frame[2] && p.y>=frame[1] && p.y<=frame[3] && !obstacles.some((b)=>!b.crossing && inside(p,b));
  const leadValid=p=>valid(p.gate) && segmentClear(p.boundary,p.gate,
    obstacles.filter(o=>p.node===undefined || o.endpoint!==p.node));
  starts=starts.filter(leadValid); ends=ends.filter(leadValid);
  const all=[...starts,...ends].map(p=>p.gate);
  const segments=wires.flatMap(ps=>ps.slice(1).map((b,i)=>[ps[i],b]));
  // Nearby parallel lanes let the search avoid following an occupied line.
  // Only axis-aligned wires contribute lanes; original Dagre paths may be diagonal.
  const wireX=[],wireY=[];
  for(const [a,b] of segments) {
    if(a.x===b.x) wireX.push(a.x-lane,a.x+lane,a.x-2*lane,a.x+2*lane);
    if(a.y===b.y) wireY.push(a.y-lane,a.y+lane,a.y-2*lane,a.y+2*lane);
  }
  const xs=[...new Set([frame[0],frame[2],...all.map(p=>p.x),...obstacles.flatMap(b=>[b[0],b[2]]),...wireX])].filter(x=>x>=frame[0]&&x<=frame[2]).sort((a,b)=>a-b);
  const ys=[...new Set([frame[1],frame[3],...all.map(p=>p.y),...obstacles.flatMap(b=>[b[1],b[3]]),...wireY])].filter(y=>y>=frame[1]&&y<=frame[3]).sort((a,b)=>a-b);
  const nx=xs.length,count=nx*ys.length;
  const index=p=>ys.indexOf(p.y)*nx+xs.indexOf(p.x);
  const point=i=>({x:xs[i%nx],y:ys[Math.floor(i/nx)]});
  // 0 = horizontal, 1 = vertical, 2 = zero-length endpoint lead.
  const axis=(a,b)=>a.x===b.x?(a.y===b.y?2:1):0;
  const distance=new Float64Array(count*3).fill(Infinity);
  const previous=new Int32Array(count*3).fill(-1);
  const startAt=new Map(starts.map(p=>[index(p.gate),p]));
  const endAt=new Map(ends.map(p=>[index(p.gate),p]));
  const heap=[];
  function push(item) {
    heap.push(item);let i=heap.length-1;
    while(i) {const p=(i-1)>>1;if(heap[p][0]<=item[0]) break;heap[i]=heap[p];i=p;}
    heap[i]=item;
  }
  function pop() {
    const first=heap[0],last=heap.pop();
    if(heap.length) {
      let i=0;
      while(i*2+1<heap.length) {
        let c=i*2+1;
        if(c+1<heap.length&&heap[c+1][0]<heap[c][0]) c++;
        if(heap[c][0]>=last[0]) break;
        heap[i]=heap[c];i=c;
      }
      heap[i]=last;
    }
    return first;
  }
  function wireCost(a,b) {
    let cost=0;const horizontal=a.y===b.y,events=[];
    for(const [c,d] of segments) {
      const otherHorizontal=c.y===d.y,otherVertical=c.x===d.x;
      if((horizontal&&otherHorizontal)||(!horizontal&&otherVertical)) {
        const offset=Math.abs(horizontal?a.y-c.y:a.x-c.x);
        const shared=horizontal?Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x))-Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x)):
          Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y))-Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y));
        if(shared>0&&offset<lane) cost+=shared*(offset<1e-7?sharedPenalty:nearPenalty*(lane-offset)/lane);
        if(shared>0&&parallelPreference>0&&offset<lane*3){
          const lo=horizontal?Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x)):Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y));
          const hi=lo+shared;
          // Unsafe proximity to ANY wire cancels bundling credit on that span.
          const strength=offset<lane?-1:1-(offset-lane)/(lane*2);
          events.push([lo,1,strength],[hi,-1,strength]);
        }
      } else {
        // Half at each endpoint counts a grid-vertex crossing once, symmetrically.
        const cross=(u,v)=>u.x*v.y-u.y*v.x;
        const r={x:b.x-a.x,y:b.y-a.y},q={x:d.x-c.x,y:d.y-c.y},delta={x:c.x-a.x,y:c.y-a.y};
        const den=cross(r,q);
        if(Math.abs(den)<1e-9) continue;
        const t=cross(delta,q)/den,u=cross(delta,r)/den;
        if(t>=-1e-9&&t<=1+1e-9&&u>1e-9&&u<1-1e-9) cost+=crossingPenalty*(t<1e-9||t>1-1e-9?.5:1);
      }
    }
    if(events.length){
      events.sort((a,b)=>a[0]-b[0]);
      const active=new Map();let blocked=0,last=events[0][0],credit=0;
      for(let i=0;i<events.length;){
        const x=events[i][0];
        if(!blocked&&active.size)credit+=(x-last)*Math.max(...active.keys());
        while(i<events.length&&events[i][0]===x){
          const [,change,strength]=events[i++];
          if(strength<0)blocked+=change;
          else {const count=(active.get(strength)??0)+change;if(count)active.set(strength,count);else active.delete(strength);}
        }
        last=x;
      }
      // Credit never stacks for multiple neighbours, and cannot exceed 25%
      // of physical step length. No negative edges or reward-seeking loops.
      cost-=parallelPreference*credit;
    }
    return cost;
  }
  const validity=new Int8Array(count),stepCosts=new Map();
  function stepCost(i,j,p,q) {
    if(!validity[j]) validity[j]=valid(q)?1:-1;
    if(validity[j]<0) return Infinity;
    const key=Math.min(i,j)*count+Math.max(i,j);
    if(!stepCosts.has(key)) stepCosts.set(key,segmentClear(p,q,obstacles)?Math.abs(p.x-q.x)+Math.abs(p.y-q.y)+wireCost(p,q):Infinity);
    return stepCosts.get(key);
  }
  const dot=(a,b,c,d)=>(b.x-a.x)*(d.x-c.x)+(b.y-a.y)*(d.y-c.y);
  for(const [i,p] of startAt) {
    const state=i*3+axis(p.boundary,p.gate);
    distance[state]=(p.bias??0)+Math.abs(p.gate.x-p.boundary.x)+Math.abs(p.gate.y-p.boundary.y)+wireCost(p.boundary,p.gate);
    push([distance[state],state]);
  }
  let winner=-1,best=Infinity;
  while(heap.length) {
    const [cost,state]=pop();
    if(cost!==distance[state]) continue;
    if(cost>best) break;
    const i=Math.floor(state/3),incoming=state%3,p=point(i);
    if(endAt.has(i)) {
      const e=endAt.get(i),lastAxis=axis(e.gate,e.boundary);
      const from=previous[state]<0?startAt.get(i)?.boundary:point(Math.floor(previous[state]/3));
      if(!from||dot(e.boundary,e.gate,p,from)>=-1e-7) {
        const total=cost+(e.bias??0)+Math.abs(e.gate.x-e.boundary.x)+Math.abs(e.gate.y-e.boundary.y)+wireCost(e.gate,e.boundary)+
          (incoming!==2&&lastAxis!==2&&incoming!==lastAxis?bendPenalty:0);
        if(total<best) {best=total;winner=state;}
      }
    }
    const ix=i%nx,iy=Math.floor(i/nx);
    const adjacent=[ix>0?i-1:-1,ix+1<nx?i+1:-1,iy>0?i-nx:-1,iy+1<ys.length?i+nx:-1];
    for(const j of adjacent) {
      if(j<0) continue;
      const q=point(j),step=stepCost(i,j,p,q);
      if(!Number.isFinite(step)) continue;
      const start=previous[state]===-1?startAt.get(i):null,end=endAt.get(j);
      if(start&&dot(start.boundary,start.gate,p,q)<-1e-7) continue;
      if(end&&dot(end.boundary,end.gate,q,p)<-1e-7) continue;
      const outgoing=axis(p,q),nextState=j*3+outgoing;
      const next=cost+step+(incoming!==2&&incoming!==outgoing?bendPenalty:0);
      if(next<distance[nextState]) {distance[nextState]=next;previous[nextState]=state;push([next,nextState]);}
    }
  }
  if(winner<0) throw new Error('Không tìm được đường edge qua ranh giới subgraph mà tránh node/tiêu đề.');
  const path=[];let cursor=winner;
  while(cursor!==-1) {path.push(point(Math.floor(cursor/3)));if(previous[cursor]===-1) break;cursor=previous[cursor];}
  path.reverse();
  return [startAt.get(Math.floor(cursor/3)).boundary,...path,endAt.get(Math.floor(winner/3)).boundary];
}
