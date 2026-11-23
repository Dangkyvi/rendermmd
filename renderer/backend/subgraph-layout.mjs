import { SourceError } from "./theme-source.mjs";
// Hierarchical composition of the installed Dagre backend. All geometry is in
// final SVG coordinates; no browser measurements or synthetic cluster bounds.
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
  function compose(scope, inherited) {
    const group = groupById.get(scope);
    const direction = normalize(group && !group.external ? group.dir ?? inherited : inherited);
    if (!['TB','BT','LR','RL'].includes(direction)) throw new SourceError(`Direction subgraph chưa hỗ trợ: ${direction}`, "source_structure");
    if (group) group.effectiveDirection = direction;
    for (const id of children.get(scope)) if (groupById.has(id)) compose(id, direction);
    const local = new dagre.graphlib.Graph({ multigraph: true });
    local.setGraph({rankdir: direction, nodesep: 48, ranksep: 96, marginx: 28, marginy: 28});
    local.setDefaultEdgeLabel(() => ({}));
    for (const id of children.get(scope)) {
      const {width, height} = graph.node(id);
      local.setNode(id, {width, height});
    }
    for (const edge of edges) {
      if (scopes.get(edge.name) !== scope) continue;
      const v = project(edge.v, scope), w = project(edge.w, scope);
      if (v === null || w === null || (v === w && edge.v !== edge.w)) continue;
      const data = graph.edge(edge);
      local.setEdge(v, w, {width:data.width, height:data.height, labelpos:'c', minlen:data.minlen}, edge.name);
    }
    if (local.nodeCount()) {
      dagre.layout(local);
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
      if (data.hasLabel) Object.assign(data, translate(route));
      data.direct = edge.v === original.v && edge.w === original.w &&
        !groupById.has(edge.v) && !groupById.has(edge.w);
    }
  }
  place(root, 0, 0);
  const size = localGraphs.get(root);
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
  for (const edge of edges) {
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
    function ports(id, other) {
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
      return candidates.map(([boundary,gate]) => ({boundary,gate,node:id}));
    }
    let starts = ports(edge.v, edge.w), ends = ports(edge.w, edge.v);
    if (edge.v === edge.w) { starts = [starts[1]]; ends = [ends[2]]; }
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
export function labelOnRoute(points,width,height,obstacles,frame,otherRoutes=[],preferredRoute=null) {
  const route=simplify(points,[points[1],points.at(-2)]);
  const candidates=[];
  let travelled=0;
  const total=routeLength(route);
  for(let i=1;i<route.length;i++) {
    const a=route[i-1],b=route[i],length=Math.abs(b.x-a.x)+Math.abs(b.y-a.y);
    if(i>1 && i<route.length-1 && length>0) {
      const horizontal=a.y===b.y, margin=(horizontal?width:height)/2+CLEARANCE;
      if(length>=margin*2) for(const distance of [length/2,margin,length-margin]) {
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
  const result=[...route];result.splice(best.index,0,best.position);
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
// are nonnegative: length + bends + shared/near wire length + crossings.
// Existing wires are soft costs; nodes, group titles and label boxes stay hard.
export function orthogonalRoute(starts, ends, obstacles, frame, options={}) {
  const wires=options.wires??[],lane=12;
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
    if(a.x===b.x) wireX.push(a.x-lane,a.x+lane);
    if(a.y===b.y) wireY.push(a.y-lane,a.y+lane);
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
    let cost=0;const horizontal=a.y===b.y;
    for(const [c,d] of segments) {
      const otherHorizontal=c.y===d.y,otherVertical=c.x===d.x;
      if((horizontal&&otherHorizontal)||(!horizontal&&otherVertical)) {
        const offset=Math.abs(horizontal?a.y-c.y:a.x-c.x);
        const shared=horizontal?Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x))-Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x)):
          Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y))-Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y));
        if(shared>0&&offset<lane) cost+=shared*(offset<1e-7?sharedPenalty:nearPenalty*(lane-offset)/lane);
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
    distance[state]=Math.abs(p.gate.x-p.boundary.x)+Math.abs(p.gate.y-p.boundary.y)+wireCost(p.boundary,p.gate);
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
        const total=cost+Math.abs(e.gate.x-e.boundary.x)+Math.abs(e.gate.y-e.boundary.y)+wireCost(e.gate,e.boundary)+
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
