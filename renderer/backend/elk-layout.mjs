import ELK from 'elkjs/lib/elk.bundled.js';
import { SourceError } from './theme-source.mjs';

// ELK coordinates are top-left relative to the parent; the renderer uses
// absolute centres. Keep all style/shape/text objects in the existing graph.
export async function layoutElk(graph, groups, rankdir) {
  const root = {id:'elk:root', children:[], edges:[]};
  const groupById = new Map(groups.map(g => [g.id,g]));
  const parent = new Map();
  for (const group of groups) for (const id of group.nodes) {
    if (!graph.hasNode(id)) throw new SourceError(`Subgraph ${group.id}: member không tồn tại: ${id}`, 'source_structure');
    if (parent.has(id) && parent.get(id)!==group.id)
      throw new SourceError(`Node/subgraph ${id} có nhiều parent.`, 'source_structure');
    parent.set(id,group.id);
  }
  function ancestors(id) {
    const seen = new Set();
    while (id!==undefined) {
      if (seen.has(id)) throw new SourceError('Cây subgraph có chu trình.', 'source_structure');
      seen.add(id); id=parent.get(id);
    }
    return seen;
  }
  for (const id of graph.nodes()) ancestors(id);
  const edges=graph.edges();
  const directions={TB:'DOWN',BT:'UP',LR:'RIGHT',RL:'LEFT',TD:'DOWN'};
  const effective=new Map();
  function direction(id) {
    if (effective.has(id)) return effective.get(id);
    const group=groupById.get(id);
    const inherited=parent.has(id)?direction(parent.get(id)):rankdir;
    const external=edges.some(e => e.v!==id && e.w!==id &&
      ancestors(e.v).has(id)!==ancestors(e.w).has(id));
    const value=group && !external ? group.dir ?? inherited : inherited;
    if (!directions[value]) throw new SourceError(`Direction subgraph chưa hỗ trợ: ${value}`, 'source_structure');
    effective.set(id,value);
    if (group) group.effectiveDirection=value==='TD'?'TB':value;
    return value;
  }
  const elkNodes=new Map(graph.nodes().map((id,i)=>[id,{id:`elk:node:${i}`} ]));
  for (const [id,node] of elkNodes) {
    const data=graph.node(id), group=groupById.get(id);
    if (group) {
      // Included hierarchy shares one layered direction. An isolated subtree
      // can use a separate run, preserving Mermaid's private group direction.
      const crosses=edges.some(e =>
        (e.v!==id && ancestors(e.v).has(id)) !== (e.w!==id && ancestors(e.w).has(id)));
      const geometry=data.geometry;
      data.header=Math.max(geometry.logical_box[3],geometry.path_box[3])+28;
      const minimum=Math.max(geometry.logical_box[2],geometry.path_box[2])+56;
      const dir=direction(id);
      // elkjs 0.12.1 applies compound minimum size in the pre-transposed
      // layered frame for included vertical hierarchies. Leaf/separate nodes
      // use ordinary x/y. Swapping here keeps measured titles inside TB/BT boxes.
      const minSize=crosses && ['TB','TD','BT'].includes(dir)
        ? [data.header+56,minimum] : [minimum,data.header+56];
      Object.assign(node,{children:[],layoutOptions:{
        'elk.direction':directions[dir],
        'elk.hierarchyHandling':crosses?'INCLUDE_CHILDREN':'SEPARATE_CHILDREN',
        'elk.padding':`[top=${data.header+28},left=28,bottom=28,right=28]`,
        'elk.nodeSize.constraints':'[MINIMUM_SIZE]',
        'elk.nodeSize.minimum':`(${minSize.join(',')})`,
      }});
    } else Object.assign(node,{width:data.width,height:data.height});
  }
  for (const [id,node] of elkNodes)
    (parent.has(id)?elkNodes.get(parent.get(id)):root).children.push(node);
  for (const edge of edges) {
    const data=graph.edge(edge);
    root.edges.push({id:`elk:edge:${edge.name}`,sources:[elkNodes.get(edge.v).id],
      targets:[elkNodes.get(edge.w).id],
      ...(data.hasLabel?{labels:[{id:`elk:label:${edge.name}`,text:data.label,width:data.width,height:data.height}]}:{}),
    });
  }
  root.layoutOptions={
    'elk.algorithm':'layered', 'elk.direction':directions[rankdir],
    'elk.hierarchyHandling':'INCLUDE_CHILDREN', 'elk.edgeRouting':'ORTHOGONAL',
    'elk.padding':'[top=28,left=28,bottom=28,right=28]',
    'elk.spacing.nodeNode':'48', 'elk.layered.spacing.nodeNodeBetweenLayers':'96',
    'elk.spacing.edgeNode':'20', 'elk.spacing.edgeLabel':'10',
    'elk.randomSeed':'1',
  };
  // The bundled build uses its in-process worker shim: no browser or worker URL.
  const result=await new ELK().layout(root);
  const originals=new Map([...elkNodes].map(([id,n])=>[n.id,id]));
  const origins=new Map();
  const containers=[];
  function place(container,ox,oy) {
    const x=ox+(container.x??0),y=oy+(container.y??0);
    origins.set(container.id,{x,y}); containers.push(container);
    const id=originals.get(container.id);
    if (id!==undefined) Object.assign(graph.node(id),{
      x:x+container.width/2,y:y+container.height/2,width:container.width,height:container.height,
    });
    for (const child of container.children??[]) place(child,x,y);
  }
  place(result,0,0);
  const byEdge=new Map(edges.map(e=>[`elk:edge:${e.name}`,e]));
  for (const owner of containers) for (const route of owner.edges??[]) {
    const edge=byEdge.get(route.id),data=graph.edge(edge);
    const origin=origins.get(route.container??owner.id);
    if (!origin || route.sections?.length!==1)
      throw new Error(`ELK edge ${edge.name}: thiếu container hoặc section đơn.`);
    const section=route.sections[0];
    const translate=p=>({x:p.x+origin.x,y:p.y+origin.y});
    data.points=[section.startPoint,...(section.bendPoints??[]),section.endPoint].map(translate);
    data.clusterRoute=true;
    if (data.hasLabel) {
      const label=route.labels?.[0];
      if (!Number.isFinite(label?.x)||!Number.isFinite(label?.y))
        throw new Error(`ELK edge ${edge.name}: thiếu vị trí nhãn.`);
      Object.assign(data,translate({x:label.x+label.width/2,y:label.y+label.height/2}));
    }
  }
  for (const edge of edges) if (!graph.edge(edge).points) throw new Error(`ELK edge ${edge.name}: thiếu routing.`);
  Object.assign(graph.graph(),{width:result.width,height:result.height});
}
