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
try {
  const request=JSON.parse(readFileSync(0,'utf8'));
  let result;
  if(request.action==='import')result=await importSource(request.source);
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
  process.stderr.write(JSON.stringify({code:'invalid_diagram',message:error.message}));process.exitCode=1;
}
