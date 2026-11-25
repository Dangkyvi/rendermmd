import assert from 'node:assert/strict';
import dagre from '@dagrejs/dagre';
import {layoutConnectedScope,foldDagreScope} from '../subgraph-layout.mjs';
function graph(ids,links,anchors={}){
  const g=new dagre.graphlib.Graph({multigraph:true});g.setGraph({rankdir:'TB'});g.setDefaultEdgeLabel(()=>({}));
  for(const id of ids)g.setNode(id,{width:100,height:60,isSubgraph:true,header:20});
  links.forEach(([v,w],i)=>g.setEdge(v,w,{width:0,height:0,sourceAnchor:anchors[v]??{x:0,y:0},targetAnchor:anchors[w]??{x:0,y:0}},String(i)));
  dagre.layout(g);layoutConnectedScope(g);return g;
}
function disjoint(g){for(const [i,a] of g.nodes().entries())for(const b of g.nodes().slice(i+1)){
  const x=g.node(a),y=g.node(b);assert(Math.abs(x.x-y.x)>=(x.width+y.width)/2||Math.abs(x.y-y.y)>=(x.height+y.height)/2,[a,b]);
}}
const ids=['A','B','C','D','E','F'],links=[['A','B'],['A','C'],['B','D'],['C','D'],['D','E'],['E','F']];
const g=graph(ids,links);disjoint(g);
assert(g.graph().wireAware);assert(g.graph().placementStats.probeCount>0,'real obstacle router must feed placement');
const changed=graph(ids,[['A','E'],['A','C'],['E','D'],['C','D'],['D','B'],['B','F']]);
assert.notDeepEqual(ids.map(id=>[g.node(id).x,g.node(id).y]),ids.map(id=>[changed.node(id).x,changed.node(id).y]),'changing edges must change block placement');
const anchored=graph(ids,links,{A:{x:0,y:20},B:{x:0,y:-5},C:{x:0,y:20}});
assert.notDeepEqual(ids.map(id=>[g.node(id).x,g.node(id).y]),ids.map(id=>[anchored.node(id).x,anchored.node(id).y]),'changing internal attachment offsets must change placement');
const again=graph(ids,links);assert.deepEqual(ids.map(id=>g.node(id)),ids.map(id=>again.node(id)));
const renamed=graph(ids.map(id=>'X'+id),links.map(([a,b])=>['X'+a,'X'+b]));
assert.deepEqual(ids.map(id=>[g.node(id).x,g.node(id).y]),ids.map(id=>[renamed.node('X'+id).x,renamed.node('X'+id).y]));
const cyclic=graph(ids,[...links,['F','A']]);disjoint(cyclic);
assert(Object.values(cyclic.graph()).every(v=>typeof v!=='number'||Number.isFinite(v)));
console.log('PASS connected layout: edge-dependent and port-dependent positions, cycles, real routing probes, stable IDs, non-overlap, deterministic single layout');

// The public integration gate must leave plain Dagre geometry untouched.
function gated(groups, leaves, links, invisible=false){
  const local=new dagre.graphlib.Graph({multigraph:true});local.setGraph({rankdir:'TB'});local.setDefaultEdgeLabel(()=>({}));
  for(let i=0;i<groups;i++)local.setNode('G'+i,{width:160,height:100,isSubgraph:true,header:20});
  for(let i=0;i<leaves;i++)local.setNode('N'+i,{width:100,height:60,isSubgraph:false});
  links.forEach(([a,b],i)=>local.setEdge(a,b,{width:0,height:0,invisible},String(i)));
  dagre.layout(local);
  const before=structuredClone({nodes:local.nodes().map(id=>local.node(id)),graph:local.graph(),edges:local.edges().map(e=>local.edge(e))});
  const changed=foldDagreScope(local,'TB');
  if(!changed)assert.deepEqual({nodes:local.nodes().map(id=>local.node(id)),graph:local.graph(),edges:local.edges().map(e=>local.edge(e))},before);
  disjoint(local);return changed;
}
assert.equal(gated(0,6,[['N0','N1'],['N1','N2']]),false);
assert.equal(gated(1,6,[['N0','G0']]),false);
assert.equal(gated(2,3,[['N0','G0'],['N1','G0'],['G1','N2']]),false);
assert.equal(gated(2,4,[['N0','G0'],['N1','G0'],['G1','N2'],['G1','N3']]),true);
assert.equal(gated(2,4,[['N0','G0'],['N0','G0'],['G0','N0'],['N0','G1']]),false);
assert.equal(gated(2,4,[['N0','G0'],['N1','G0'],['G1','N2'],['G1','N3']],true),false);
assert.equal(gated(3,0,[['G0','G1'],['G1','G2']]),true);
assert.equal(gated(3,0,[]),true);
console.log('PASS layout gate: plain/one-group unchanged, two-group distinct connected node threshold, invisible edges excluded, exactly three groups enabled');
