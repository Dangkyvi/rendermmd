// Editing-only adapter. Reuses the installed grammar and style validators;
// never changes the renderer's model, layout, SVG or JSON contracts.
import {readFileSync, existsSync} from 'node:fs';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
// Resolve against the renderer's dependency tree, not an editor-owned npm install.
const backendRoot = existsSync(new URL('../renderer/backend/mermaid-model.mjs',import.meta.url))
  ? new URL('../renderer/backend/',import.meta.url) : new URL('./',import.meta.url);
const {parseFlowchart} = await import(new URL('mermaid-model.mjs',backendRoot));
const {plainLabel,parseStyles,color} = await import(new URL('theme-source.mjs',backendRoot));
const rendererRequire=createRequire(new URL('theme-source.mjs',backendRoot));
const {toHex}=await import(pathToFileURL(rendererRequire.resolve('khroma')));

const shapes = new Map([
  ['square',['rect','squareRect','proc','process','rectangle']],
  ['round',['rounded','roundedRect','event']], ['stadium',['terminal','pill']],
  ['subroutine',['fr-rect','subprocess','subproc','framed-rectangle']],
  ['cylinder',['cyl','db','database']], ['circle',['circ']],
  ['diamond',['diam','decision','question']], ['hexagon',['hex','prepare']],
  ['lean_right',['parallelogram','lean-r','lean-right','in-out']],
  ['lean_left',['parallelogram_alt','lean-l','lean-left','out-in']],
  ['trapezoid',['trap-b','priority','trapezoid-bottom']],
  ['inv_trapezoid',['trapezoid_alt','trap-t','manual','trapezoid-top','inv-trapezoid']],
  ['odd',['flag','rect_left_inv_arrow']], ['doublecircle',['double_circle','dbl-circ','double-circle']],
].flatMap(([shape,aliases])=>[shape,...aliases].map(a=>[a,shape])));
const delimiters={square:['[',']'],round:['(',')'],stadium:['([','])'],
  subroutine:['[[',']]'],cylinder:['[(',')]'],circle:['((', '))'],
  diamond:['{','}'],hexagon:['{{','}}'],lean_right:['[/','/]'],
  lean_left:['[\\','\\]'],trapezoid:['[/','\\]'],inv_trapezoid:['[\\','/]'],
  odd:['>',']'],doublecircle:['(((',')))']};
const arrows={arrow_open:['',''],arrow_point:['','>'],arrow_circle:['','o'],
  arrow_cross:['','x'],double_arrow_point:['<','>'],double_arrow_circle:['o','o'],double_arrow_cross:['x','x']};
function fail(message){throw new Error(message);}
function shape(value){return shapes.get(value)??fail(`Shape chưa hỗ trợ: ${value}`);}
function id(value){
  if(typeof value!=='string'||!value||/[\s\u0000-\u001f\u007f]/u.test(value)||['end','subgraph','direction'].includes(value)) fail(`ID không thể xuất Mermaid an toàn: ${value}`);
  return value;
}
function text(value){
  if(typeof value!=='string'||value.includes('\0')) fail('Nhãn phải là chuỗi không chứa NUL.');
  if(value==='')return '" "'; // Mermaid rejects an empty quoted token, trims a blank one.
  // Escape once for Mermaid's quoted plain-text grammar. In particular do not
  // inject decoded HTML, quotes, pipes, hash entities or new source statements.
  return '"'+value.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/#/g,'#35;').replace(/\|/g,'#124;')
    .replace(/\\/g,'#92;').replace(/^[ \t]+|[ \t]+$/g,s=>[...s].map(c=>'#'+c.codePointAt(0)+';').join('')).replace(/\r/g,'#13;').replace(/\n/g,'<br/>')+'"';
}
function declarations(style){
  const entries=Object.entries(style);
  parseStyles(entries.map(([k,v])=>`${k}:${v}`),'edit style');
  return entries.map(([k,v])=>`${k}:${String(v).replace(/,/g,'\\,')}`).join(',');
}
function operator(edge){
  if(!Object.hasOwn(arrows,edge.arrow_type)) fail('Kiểu marker không được hỗ trợ.');
  const [left,right]=arrows[edge.arrow_type], n=Math.max(1,edge.length);
  if(!Number.isInteger(n)||n>500) fail('Độ dài cạnh không hợp lệ.');
  if(edge.line_style==='invisible')return '~'.repeat(n+2);
  const ch=edge.line_style==='thick'?'=':'-';
  if(!['normal','dotted','thick'].includes(edge.line_style))fail('Kiểu nét không được hỗ trợ.');
  const body=edge.line_style==='dotted'?'-'+'.'.repeat(n)+'-':ch.repeat(n+2);
  // Every non-dotted marked link uses one fewer dash than an open link.
  return left+(right&&edge.line_style!=='dotted'?body.slice(1):body)+right;
}
async function importSource(source){
  const {diagram,requested}=await parseFlowchart(source),db=diagram.db;
  const rawGroups=db.getSubGraphs(),groupIds=new Set(rawGroups.map(g=>g.id));
  const vertices=[...db.getVertices().values()],sourceEdges=db.getEdges();
  const parent=new Map();
  for(const group of rawGroups)for(const child of group.nodes) {
    if(parent.has(child)&&parent.get(child)!==group.id)fail(`Nhiều parent cho ${child}`);
    parent.set(child,group.id);
  }
  const style=(item,group=false)=>parseStyles([
    ...db.getCompiledStyles(group?item.classes??[]:['default','node',...(item.classes??[])]),
    ...(group?vertices.find(v=>v.id===item.id)?.styles??[]:item.styles??[]),
  ],`edit import ${item.id}`);
  const used=new Set();
  return {schema:1,direction:db.getDirection(),config:requested.config,
    title:plainLabel(db.getDiagramTitle()),
    node_defaults:parseStyles(db.getCompiledStyles(['default','node']),'node defaults'),
    edge_defaults:{fill:'none',...parseStyles(sourceEdges.defaultStyle??[],'edge defaults')},
    nodes:vertices.filter(v=>!groupIds.has(v.id)).map(v=>({id:v.id,label:plainLabel(v.text),shape:shape(v.type??'square'),style:style(v),subgraph_id:parent.get(v.id)??null})),
    subgraphs:rawGroups.map(g=>({id:g.id,label:plainLabel(g.title),direction:g.dir??null,style:style(g,true),parent_id:parent.get(g.id)??null,members:[...g.nodes]})),
    edges:sourceEdges.map(e=>{
      const edgeId=e.isUserDefinedId&&!used.has(e.id)?e.id:'e_'+randomUUID().replaceAll('-','');used.add(edgeId);
      return {id:edgeId,mermaid_id:e.id,source:e.start,target:e.end,label:plainLabel(e.text??''),line_style:e.stroke,arrow_type:e.type,length:e.length??1,
        style:{fill:'none',...parseStyles([...db.getCompiledStyles(e.classes??[]),...(sourceEdges.defaultStyle??[]),...(e.style??[])],'edge import')}};
    })};
}
function serialize(state){
  declarations(state.node_defaults);declarations(state.edge_defaults);
  const lines=[];
  if(state.title||Object.keys(state.config).length)lines.push('---',...(state.title?['title: '+text(state.title)]:[]),'config: '+JSON.stringify(state.config),'---');
  lines.push('flowchart '+state.direction);
  // Predeclare leaves in original model order to preserve Dagre tie-breaking.
  for(const node of state.nodes){const [a,b]=delimiters[shape(node.shape)];lines.push(id(node.id)+a+text(node.label)+b);}
  const groups=new Map(state.subgraphs.map(g=>[g.id,g]));
  const emit=(g)=>{
    lines.push('subgraph '+id(g.id)+' ['+text(g.label)+']');
    if(g.direction)lines.push('direction '+g.direction);
    // Bare member declarations reproduce the stored model order exactly.
    for(const member of g.members) {
      if(groups.has(member))emit(groups.get(member));else lines.push(id(member));
    }
    lines.push('end');
  };
  for(const group of state.subgraphs)if(group.parent_id===null)emit(group);
  for(const edge of state.edges)lines.push(id(edge.source)+' '+operator(edge)+(edge.label?'|'+text(edge.label)+'|':'')+' '+id(edge.target));
  for(const entity of [...state.nodes,...state.subgraphs])if(Object.keys(entity.style).length)lines.push('style '+id(entity.id)+' '+declarations(entity.style));
  state.edges.forEach((edge,i)=>{if(Object.keys(edge.style).length)lines.push('linkStyle '+i+' '+declarations(edge.style));});
  return lines.join('\n')+'\n';
}
function regionError(message,code='region_blocked',details={}){throw Object.assign(new Error(message),{code,details});}
function regionSeed(layout,state,positions={},labels={}) {
  if(!positions||typeof positions!=='object'||Array.isArray(positions)||!labels||typeof labels!=='object'||Array.isArray(labels))regionError('Geometry vùng không hợp lệ.','invalid_geometry');
  const original=structuredClone(layout), nodes=new Map(layout.nodes.map(n=>[n.id,n]));
  const shifts=new Map(),parent=new Map(layout.subgraphs.flatMap(g=>g.members.map(id=>[id,g])));
  const pair=v=>Array.isArray(v)&&v.length===2&&v.every(x=>typeof x==='number'&&Number.isFinite(x));
  const overlap=(a,b)=>a[0]<b[0]+b[2]-1e-6&&a[0]+a[2]>b[0]+1e-6&&a[1]<b[1]+b[3]-1e-6&&a[1]+a[3]>b[1]+1e-6;
  for(const [id,xy] of Object.entries(positions)){
    const n=nodes.get(id);if(!n||!pair(xy))regionError('Vị trí node không hợp lệ.','invalid_geometry');
    const delta=[xy[0]-n.box[0],xy[1]-n.box[1]];shifts.set(id,delta);
    n.box[0]=xy[0];n.box[1]=xy[1];n.label_box[0]+=delta[0];n.label_box[1]+=delta[1];
    const g=parent.get(id),b=g?g.box:[0,0,layout.width,layout.height];
    const top=g?Math.max(b[1]+20,g.label_box[1]+g.label_box[3]+16):b[1]+2;
    if(n.box[0]<b[0]+(g?20:2)||n.box[1]<top||n.box[0]+n.box[2]>b[0]+b[2]-(g?20:2)||n.box[1]+n.box[3]>b[1]+b[3]-(g?20:2))regionError('Node vượt khung nhóm hoặc viewport.','invalid_geometry');
    for(const other of [...layout.nodes,...layout.subgraphs])
      if(other.id!==id&&parent.get(other.id)===g&&overlap(n.box,other.box)){
        // Other selected nodes still have their old boxes; checked below once all move.
        if(!Object.hasOwn(positions,other.id))regionError('Node đè thành phần bị khóa.','invalid_geometry');
      }
  }
  for(const id of shifts.keys())for(const other of layout.nodes)
    if(id!==other.id&&parent.get(id)===parent.get(other.id)&&overlap(nodes.get(id).box,other.box))regionError('Node chồng lấn.','invalid_geometry');
  for(const [id,xy] of Object.entries(labels)){
    const i=state.edges.findIndex(e=>e.id===id),e=layout.edges.find(e=>e.ordinal===i);
    if(!e||!pair(xy)||e.label_box[2]<=0)regionError('Vị trí nhãn không hợp lệ.','invalid_geometry');
    e.label_box[0]=xy[0];e.label_box[1]=xy[1];
  }
  for(const e of layout.edges){
    const old=original.edges.find(x=>x.ordinal===e.ordinal),s=shifts.get(e.source)??[0,0],t=shifts.get(e.target)??[0,0];
    if(shifts.has(e.source)||shifts.has(e.target)){
      const move=(p,d)=>[p[0]+d[0],p[1]+d[1]];
      e.points=[move(old.points[0],s),move(old.points[1],s),move(old.points.at(-2),t),move(old.points.at(-1),t)];
      e.corner_radii=e.points.map(()=>0);
    }
  }
  return layout;
}

async function validateRegionGeometry(request) {
  const {layout,state}=request, positions=request.positions??{},labels=request.labels??{};
  const {segmentHitsBox}=await import(new URL('subgraph-layout.mjs',backendRoot));
  const overlap=(a,b)=>a[2]>0&&b[2]>0&&a[0]<b[0]+b[2]-1e-6&&a[0]+a[2]>b[0]+1e-6&&a[1]<b[1]+b[3]-1e-6&&a[1]+a[3]>b[1]+1e-6;
  for(const e of layout.edges){
    for(const n of layout.nodes){
      if(Object.hasOwn(positions,n.id)&&n.id!==e.source&&n.id!==e.target){
        const b=n.box,box=[b[0]-2,b[1]-2,b[0]+b[2]+2,b[1]+b[3]+2];
        if(e.points.slice(1).some((p,i)=>segmentHitsBox({x:e.points[i][0],y:e.points[i][1]},{x:p[0],y:p[1]},box)))regionError('Node mới che đường cạnh bên ngoài.','invalid_geometry');
      }
      if((Object.hasOwn(positions,n.id)||Object.hasOwn(labels,state.edges[e.ordinal].id))&&overlap(n.box,e.label_box))regionError('Nhãn đè node sau khi sửa vùng.','invalid_geometry');
    }
    if(Object.hasOwn(labels,state.edges[e.ordinal].id)){
      const b=e.label_box;
      if(b[0]<0||b[1]<0||b[0]+b[2]>layout.width||b[1]+b[3]>layout.height)regionError('Nhãn ra ngoài hình.','invalid_geometry');
      for(const other of layout.edges)if(other.ordinal!==e.ordinal&&overlap(b,other.label_box))regionError('Hai nhãn chồng lấn.','invalid_geometry');
      const box=[b[0]-2,b[1]-2,b[0]+b[2]+2,b[1]+b[3]+2];
      for(const other of layout.edges)if(other.ordinal!==e.ordinal&&state.edges[other.ordinal].line_style!=='invisible')
        if(other.points.slice(1).some((p,i)=>segmentHitsBox({x:other.points[i][0],y:other.points[i][1]},{x:p[0],y:p[1]},box)))regionError('Nhãn che đường cạnh khác.','invalid_geometry');
      for(const g of layout.subgraphs)if(overlap(b,g.label_box))regionError('Nhãn đè tiêu đề nhóm.','invalid_geometry');
    }
  }
  return {valid:true};
}

async function relayoutRegion(request) {
  const {layout,state}=request,ids=request.node_ids;
  if(!Array.isArray(ids)||ids.length<2||ids.length>150||new Set(ids).size!==ids.length||ids.some(id=>typeof id!=='string'))regionError('Cần 2..150 node_ids duy nhất.','invalid_argument');
  const direction=request.direction??'LR',goal=request.goal??'compact';
  if(!['LR','RL','TB','BT','TD'].includes(direction)||!['compact','reduce_crossings'].includes(goal)||(request.preserve_boundary!==undefined&&request.preserve_boundary!==true))regionError('direction/goal/preserve_boundary không hỗ trợ.','invalid_argument');
  const nodes=new Map(layout.nodes.map(n=>[n.id,n])),parent=new Map(layout.subgraphs.flatMap(g=>g.members.map(id=>[id,g]))), selected=new Set(ids);
  if(ids.some(id=>!nodes.has(id)))regionError('node_ids chỉ nhận ID node, không nhận khung nhóm.','id_not_found');
  const group=parent.get(ids[0]);if(ids.some(id=>parent.get(id)!==group))regionError('Các node cần có cùng nhóm cha trực tiếp.','invalid_argument');
  const outer=group?group.box:[0,0,layout.width,layout.height];
  const inner=[outer[0]+(group?24:12),group?Math.max(outer[1]+24,group.label_box[1]+group.label_box[3]+20):12,
    outer[0]+outer[2]-(group?24:12),outer[1]+outer[3]-(group?24:12)];
  let frame=inner;
  if(request.bounds!==undefined){const b=request.bounds;
    if(!Array.isArray(b)||b.length!==4||b.some(x=>typeof x!=='number'||!Number.isFinite(x))||b[2]<=0||b[3]<=0)regionError('bounds cần [x,y,width,height].','invalid_argument');
    frame=[b[0],b[1],b[0]+b[2],b[1]+b[3]];
    if(frame[0]<inner[0]||frame[1]<inner[1]||frame[2]>inner[2]||frame[3]>inner[3])regionError('bounds vượt khung cha.','invalid_argument');
  }
  const dagre=rendererRequire('@dagrejs/dagre'),g=new dagre.graphlib.Graph({multigraph:true});
  g.setGraph({rankdir:direction==='TD'?'TB':direction,nodesep:goal==='compact'?24:40,ranksep:goal==='compact'?40:64,marginx:8,marginy:8});
  g.setDefaultEdgeLabel(()=>({}));
  // Stable model order, not node ID spelling or input selection order.
  for(const n of layout.nodes)if(selected.has(n.id))g.setNode(n.id,{width:n.box[2],height:n.box[3]});
  for(const e of layout.edges)if(selected.has(e.source)&&selected.has(e.target))
    g.setEdge(e.source,e.target,{width:e.label_box[2]?e.label_box[2]+24:0,height:e.label_box[3]?e.label_box[3]+20:0,labelpos:'c'},String(e.ordinal));
  dagre.layout(g);
  if(g.edgeCount()===0){
    const ns=g.nodes().map(id=>g.node(id));
    const area=ns.reduce((sum,n)=>sum+(n.width+24)*(n.height+24),0);
    const limit=Math.min(frame[2]-frame[0],Math.max(...ns.map(n=>n.width+16),Math.sqrt(area*(frame[2]-frame[0])/(frame[3]-frame[1]))));
    let x=8,y=8,height=0,width=0;
    for(const n of ns){
      if(x>8&&x+n.width+8>limit){x=8;y+=height+24;height=0;}
      n.x=x+n.width/2;n.y=y+n.height/2;x+=n.width+24;height=Math.max(height,n.height);width=Math.max(width,x-24+8);
    }
    g.graph().width=width;g.graph().height=y+height+8;
  }
  const w=g.graph().width,h=g.graph().height;
  if(w>frame[2]-frame[0]||h>frame[3]-frame[1])regionError('Vùng không đủ chỗ cho bố cục yêu cầu.','region_too_small',{required_size:[w,h],available_size:[frame[2]-frame[0],frame[3]-frame[1]]});
  const old=ids.map(id=>nodes.get(id).box),cx=old.reduce((s,b)=>s+b[0]+b[2]/2,0)/old.length,cy=old.reduce((s,b)=>s+b[1]+b[3]/2,0)/old.length;
  // Search empty origins for this single measured layout, not alternative layouts.
  const locked=[...layout.nodes,...layout.subgraphs].filter(n=>!selected.has(n.id)&&parent.get(n.id)===group);
  const xs=[Math.max(frame[0],Math.min(frame[2]-w,cx-w/2)),frame[0],frame[2]-w,...locked.map(n=>n.box[0]+n.box[2]+16)];
  const ys=[Math.max(frame[1],Math.min(frame[3]-h,cy-h/2)),frame[1],frame[3]-h,...locked.map(n=>n.box[1]+n.box[3]+16)];
  const {segmentHitsBox}=await import(new URL('subgraph-layout.mjs',backendRoot));
  async function finish(seed,positions){
  const affected=seed.edges.filter(e=>selected.has(e.source)||selected.has(e.target));
  const labelSizes=new Map(affected.map(e=>[e.ordinal,[e.label_box[2],e.label_box[3]]]));
  const first=ids[0], localFirst=g.node(first);
  const ox=positions[first][0]-(localFirst.x-localFirst.width/2),oy=positions[first][1]-(localFirst.y-localFirst.height/2);
  const plannedLabels=new Set();
  for(const e of affected){
    const [lw,lh]=labelSizes.get(e.ordinal),local=g.edge({v:e.source,w:e.target,name:String(e.ordinal)});
    if(lw>0&&local&&Number.isFinite(local.x)){
      e.label_box=[ox+local.x-lw/2,oy+local.y-lh/2,lw,lh];plannedLabels.add(e.ordinal);
    }else e.label_box=[0,0,0,0];
  }
  const routes={},labels={};
  for(const e of affected){
    const id=state.edges[e.ordinal].id;
    const routed=await routeEdge({layout:seed,state,edge_id:id,allow_invisible:true,
      relocate_label:!plannedLabels.has(e.ordinal),label_size:labelSizes.get(e.ordinal),
      ignore_wire_ordinals:affected.filter(x=>x.ordinal>e.ordinal).map(x=>x.ordinal)});
    e.points=routed.points;e.corner_radii=e.points.map(()=>0);e.label_box=routed.label_box??e.label_box;
    routes[id]=e.points;if(e.label_box[2]>0)labels[id]=e.label_box.slice(0,2);
  }
  await validateRegionGeometry({layout:seed,state,positions,labels});
  return {positions,labels,routes,affected_edge_ids:Object.keys(routes),bounds:[frame[0],frame[1],frame[2]-frame[0],frame[3]-frame[1]],required_size:[w,h]};
  }
  let positions=null,seed=null,planned=null,lastFailure='không đủ khoảng trống';
  let attempts=0;
  for(const y of [...new Set(ys)]){for(const x of [...new Set(xs)]){
    if(++attempts>128)break;
    if(x<frame[0]||y<frame[1]||x+w>frame[2]||y+h>frame[3])continue;
    const candidate=Object.fromEntries(ids.map(id=>{const n=g.node(id);return [id,[x+n.x-n.width/2,y+n.y-n.height/2]];}));
    try{
      seed=regionSeed(structuredClone(layout),state,candidate,{});
      // A node must not cover the route of a completely locked edge.
      for(const e of seed.edges)if(!selected.has(e.source)&&!selected.has(e.target))
        for(const id of ids){const b=seed.nodes.find(n=>n.id===id).box,box=[b[0]-8,b[1]-8,b[0]+b[2]+8,b[1]+b[3]+8];
          if(e.points.slice(1).some((p,i)=>segmentHitsBox({x:e.points[i][0],y:e.points[i][1]},{x:p[0],y:p[1]},box)))regionError('Node che đường cạnh bị khóa.','invalid_geometry');}
      planned=await finish(seed,candidate);positions=candidate;break;
    }catch(e){lastFailure=e.message;if(!['invalid_geometry','routing_failed'].includes(e.code))throw e;}
  }if(positions||attempts>128)break;}
  if(!planned)regionError('Không tìm được chỗ đặt và đường dây hợp lệ trong vùng bị khóa: '+lastFailure,'region_blocked',{required_size:[w,h]});
  return planned;
}

async function routeEdge(request) {
  const {orthogonalRoute,segmentClear,ancestorObstacles,CLEARANCE,labelOnRoute}=await import(new URL('subgraph-layout.mjs',backendRoot));
  const error=(message,code='routing_failed')=>{throw Object.assign(new Error(message),{code});};
  const {layout,state,edge_id,points:stored}=request;
  const index=state.edges.findIndex(e=>e.id===edge_id);
  if(index<0)error('Không tìm thấy edge_id.','id_not_found');
  const semantic=state.edges[index],edge=layout.edges.find(e=>e.ordinal===index);
  if(semantic.line_style==='invisible'&&!request.allow_invisible)error('Không chỉnh đường cạnh invisible.','invalid_argument');
  const entities=new Map([...layout.nodes,...layout.subgraphs].map(n=>[n.id,n]));
  const groups=new Map(layout.subgraphs.map(g=>[g.id,g]));
  const parent=new Map(layout.subgraphs.flatMap(g=>g.members.map(id=>[id,g.id])));
  const contains=(group,id)=>{const seen=new Set();while(id!==undefined&&!seen.has(id)){if(id===group)return true;seen.add(id);id=parent.get(id);}return false;};
  const box=(b,c=0)=>[b[0]-c,b[1]-c,b[0]+b[2]+c,b[1]+b[3]+c];
  const p=a=>({x:a[0],y:a[1]});
  const ends=[edge.points[0],edge.points.at(-1)];
  const lead=Math.max(12,Math.min(24,Math.hypot(ends[1][0]-ends[0][0],ends[1][1]-ends[0][1])/4));
  const gate=(point,neighbour,nodeId)=>{
    const dx=neighbour[0]-point[0],dy=neighbour[1]-point[1],length=Math.hypot(dx,dy);
    if(length<1e-8)error('Cổng nối không hợp lệ.','invalid_geometry');
    const ux=dx/length,uy=dy/length,b=box(entities.get(nodeId).box,CLEARANCE);
    let distance=lead;
    if(!groups.has(nodeId)&&point[0]>=b[0]&&point[0]<=b[2]&&point[1]>=b[1]&&point[1]<=b[3]){
      const exits=[];
      if(Math.abs(ux)>1e-10)exits.push(((ux>0?b[2]:b[0])-point[0])/ux);
      if(Math.abs(uy)>1e-10)exits.push(((uy>0?b[3]:b[1])-point[1])/uy);
      distance=Math.max(distance,Math.min(...exits.filter(t=>t>=0))+1);
    }
    return {x:point[0]+distance*ux,y:point[1]+distance*uy};
  };
  const start={boundary:p(ends[0]),gate:gate(ends[0],edge.points[1],edge.source),node:edge.source};
  const end={boundary:p(ends[1]),gate:gate(ends[1],edge.points.at(-2),edge.target),node:edge.target};
  let scope=parent.get(edge.source);
  while(scope!==undefined&&!contains(scope,edge.target))scope=parent.get(scope);
  const frame=scope===undefined?[2,2,layout.width-2,layout.height-2]:(()=>{
    const g=groups.get(scope),b=box(g.box);return [b[0]+8,Math.max(b[1]+8,g.label_box[1]+g.label_box[3]+10),b[2]-8,b[3]-8];
  })();
  const obstacles=[];
  for(const n of entities.values()) {
    if(groups.has(n.id)) {
      if((n.id!==edge.source&&contains(n.id,edge.source))||(n.id!==edge.target&&contains(n.id,edge.target))) {
        const b=box(n.box),header=Math.max(0,n.label_box[1]+n.label_box[3]-b[1])+16;
        obstacles.push(...ancestorObstacles(b,header));
      } else {
        const b=box(n.box,n.id===edge.source||n.id===edge.target?0:CLEARANCE);
        if(n.id===edge.source||n.id===edge.target)b.endpoint=n.id;
        obstacles.push(b);
      }
    } else {
      const b=box(n.box,CLEARANCE);if(n.id===edge.source||n.id===edge.target)b.endpoint=n.id;obstacles.push(b);
    }
  }
  for(const e of layout.edges)if(e.ordinal!==index&&e.label_box[2]>0)obstacles.push(box(e.label_box,CLEARANCE));
  const avoid=request.avoid_overlap_with??[];
  if(!Array.isArray(avoid)||avoid.length>state.edges.length||new Set(avoid).size!==avoid.length)error('avoid_overlap_with không hợp lệ.','invalid_argument');
  for(const id of avoid){
    if(id===edge_id)error('Không thể tránh chính cạnh đang sửa.','invalid_argument');
    const ordinal=state.edges.findIndex(e=>e.id===id);
    if(ordinal<0)error('Không tìm thấy cạnh cần tránh.','id_not_found');
    const other=layout.edges.find(e=>e.ordinal===ordinal);
    for(let i=1;i<other.points.length;i++){
      const a=other.points[i-1],b=other.points[i];
      // Crossing is allowed, following the same occupied lane is not.
      const o=[Math.min(a[0],b[0])-3,Math.min(a[1],b[1])-3,Math.max(a[0],b[0])+3,Math.max(a[1],b[1])+3];
      if(a[0]===b[0])o.crossing='x';else if(a[1]===b[1])o.crossing='y';
      if(i===1&&other.source===edge.source)o.endpoint=edge.source;
      if(i===other.points.length-1&&other.target===edge.target)o.endpoint=edge.target;
      o.wireAvoid=true;obstacles.push(o);
    }
  }
  const valid=(points)=>{
    if(!Array.isArray(points)||points.length<4||points.length>4096||points.some(a=>!Array.isArray(a)||a.length!==2||a.some(v=>typeof v!=='number'||!Number.isFinite(v))))error('Điểm đường cạnh không hợp lệ.','invalid_geometry');
    const near=(a,b)=>Math.hypot(a[0]-b.x,a[1]-b.y)<1e-6;
    if(!near(points[0],start.boundary)||!near(points[1],start.gate)||!near(points.at(-1),end.boundary)||!near(points.at(-2),end.gate))error('Đường cạnh không giữ cổng nối gốc.','invalid_geometry');
    for(let i=0;i<points.length;i++){
      const a=p(points[i]);if(a.x<frame[0]||a.y<frame[1]||a.x>frame[2]||a.y>frame[3])error('Đường ra ngoài vùng được phép.','invalid_geometry');
      if(i){const b=p(points[i-1]);const lead=i===1?edge.source:i===points.length-1?edge.target:null;
        if(!segmentClear(b,a,obstacles.filter(o=>o.endpoint!==lead||lead===null)))error('Đường xuyên vật cản.','invalid_geometry');
        if(i>1&&i<points.length-1&&Math.abs(a.x-b.x)>1e-6&&Math.abs(a.y-b.y)>1e-6)error('Đường thân cạnh phải vuông góc.','invalid_geometry');
      }
    }
    if(edge.label_box[2]>0){const b=edge.label_box,c={x:b[0]+b[2]/2,y:b[1]+b[3]/2};
      if(!points.some(a=>near(a,c)))error('Đường không đi qua vị trí nhãn đã lưu.','invalid_geometry');}
    return {points};
  };
  if(stored!==undefined)return valid(stored);
  const side=request.prefer_side??null;
  if(![null,'left','right','top','bottom'].includes(side))error('prefer_side không hợp lệ.','invalid_argument');
  const wires=layout.edges.filter(e=>e.ordinal!==index&&state.edges[e.ordinal].line_style!=='invisible'&&!request.ignore_wire_ordinals?.includes(e.ordinal)).map(e=>e.points.map(p));
  // Validated legacy parameter retained for compatibility; no routing effect.
  // Labels need extra separation from parallel neighbours to avoid covering
  // their wires. Unlabelled edges retain the 12-unit bundle pitch.
  const labelHeight=request.relocate_label?(request.label_size?.[1]??0):edge.label_box[3];
  const laneSpacing=labelHeight>0?Math.min(256,Math.ceil((labelHeight+28)/24)*12):12;
  const options={wires,sharedPenalty:80,laneSpacing};
  const anchors=[start];
  if(!request.relocate_label&&edge.label_box[2]>0){const b=edge.label_box,m={x:b[0]+b[2]/2,y:b[1]+b[3]/2};anchors.push({gate:m,boundary:m});}
  anchors.push(end);
  let route=[];
  try{for(let i=1;i<anchors.length;i++){
    const part=orthogonalRoute([anchors[i-1]],[anchors[i]],obstacles,frame,options);
    route.push(...(i===1?part:part.slice(1)));
  }}catch(e){error('Không tìm được đường trong vùng với cổng nối hiện tại: '+e.message);}
  // Remove duplicate waypoints, but retain both endpoint gates and label.
  route=route.filter((q,i)=>!i||q.x!==route[i-1].x||q.y!==route[i-1].y);
  if(request.relocate_label&&request.label_size?.[0]>0){
    const [w,h]=request.label_size;
    // Avoid-wire boxes constrain routing conservatively; label collision uses
    // the actual wire segments, so diagonal bounding boxes do not reject space.
    const labelObstacles=obstacles.filter(o=>!o.wireAvoid);
    const placed=labelOnRoute(route,w+12,h+8,labelObstacles,frame,wires) ??
      labelOnRoute(route,w+12,h+8,labelObstacles,frame,wires,null,{allowAcrossGates:true});
    if(!placed)error('Không đủ đoạn dây trống để đặt nhãn trong vùng.');
    route=placed.points;
    const b=[placed.position.x-w/2,placed.position.y-h/2,w,h];
    edge.label_box=b;
    return {...valid(route.map(q=>[q.x,q.y])),label_box:b};
  }
  return valid(route.map(q=>[q.x,q.y]));
}

try {
  const request=JSON.parse(readFileSync(0,'utf8'));
  let result;
  if(request.action==='validate_region_geometry')result=await validateRegionGeometry(request);
  else if(request.action==='relayout_region')result=await relayoutRegion(request);
  else if(request.action==='region_seed')result=regionSeed(request.layout,request.state,request.positions,request.labels);
  else if(request.action==='route_edge')result=await routeEdge(request);
  else if(request.action==='import')result=await importSource(request.source);
  else if(request.action==='serialize') {
    const source=serialize(request.state);
    // Reparse so generated syntax and unsupported paints/shapes fail before
    // reaching the renderer; callers still render before committing anything.
    const parsed=await importSource(source);
    result={source,parsed};
  } else if(request.action==='validate') {
    if(request.shape!==undefined)shape(request.shape);
    if(request.fill_color!==undefined)color(request.fill_color);
    result={shape:request.shape!==undefined?shape(request.shape):null,
      fill_color:request.fill_color!==undefined?(request.fill_color.includes('(')?toHex(request.fill_color):request.fill_color):null};
  } else fail('Unknown editing adapter action.');
  process.stdout.write(JSON.stringify(result));
} catch(error) {
  process.stderr.write(JSON.stringify({code:error.code??'invalid_diagram',message:error.message,details:error.details??{}}));process.exitCode=1;
}
