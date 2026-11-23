// Run from the repository root: node tests/verify_elk.mjs
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {layoutElk} from '../renderer/backend/elk-layout.mjs';
const require=createRequire(new URL('../renderer/package.json',import.meta.url));
const dagre=require('@dagrejs/dagre');
const contains=(p,c)=>c[0]>=p[0] && c[1]>=p[1] && c[2]<=p[2] && c[3]<=p[3];
const box=n=>[n.x-n.width/2,n.y-n.height/2,n.x+n.width/2,n.y+n.height/2];
for (const dir of ['LR','RL','TB','BT']) {
  const graph=new dagre.graphlib.Graph({multigraph:true}); graph.setGraph({});
  const paint={fill:'#123456',stroke:'#654321'};
  for (const id of ['A','B','C','D']) graph.setNode(id,{width:100,height:50,appearance:paint});
  const groups=[{id:'inner',nodes:['A','B']},{id:'outer',nodes:['inner']},{id:'other',nodes:['C','D']}];
  for (const g of groups) graph.setNode(g.id,{isSubgraph:true,appearance:paint,
    geometry:{logical_box:[0,0,150,20],path_box:[0,0,150,20]}});
  const pairs=[['A','B'],['C','D'],['B','C'],['outer','other'],['inner','D'],['B','C']];
  for (const [i,[v,w]] of pairs.entries()) graph.setEdge(v,w,{
    minlen:1,hasLabel:true,label:`nhãn ${i}`,width:65,height:25,appearance:paint,
  },String(i));
  await layoutElk(graph,groups,dir);
  for (const g of groups) for (const member of g.nodes) {
    const p=box(graph.node(g.id)),c=box(graph.node(member));
    assert(contains(p,c),`${dir}: ${member} escaped ${g.id}`);
    assert(c[1]>=p[1]+graph.node(g.id).header, 'child overlaps group title');
  }
  for (const id of graph.nodes()) {
    const n=graph.node(id); assert.equal(n.appearance,paint);
    assert(box(n).every(Number.isFinite));
    if (!n.isSubgraph) assert.deepEqual([n.width,n.height],[100,50]);
  }
  for (const e of graph.edges()) {
    const d=graph.edge(e); assert.equal(d.appearance,paint);
    assert(d.points.length>=2 && d.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
    assert(Number.isFinite(d.x)&&Number.isFinite(d.y));
    // Both ends must touch the absolute endpoint rectangles, including clusters.
    for (const [id,p] of [[e.v,d.points[0]],[e.w,d.points.at(-1)]]) {
      const b=box(graph.node(id)),eps=1e-6;
      assert(p.x>=b[0]-eps&&p.x<=b[2]+eps&&p.y>=b[1]-eps&&p.y<=b[3]+eps);
      assert(Math.min(Math.abs(p.x-b[0]),Math.abs(p.x-b[2]),Math.abs(p.y-b[1]),Math.abs(p.y-b[3]))<eps);
    }
  }
  const a=graph.node('A'),b=graph.node('B');
  assert(dir==='LR'?b.x>a.x:dir==='RL'?b.x<a.x:dir==='TB'?b.y>a.y:b.y<a.y);
  assert.notDeepEqual(graph.edge({v:'B',w:'C',name:'2'}).points,graph.edge({v:'B',w:'C',name:'5'}).points);
  console.log(`PASS ELK ${dir}: nested coordinates, cross-group/compound/parallel edges, labels, size and style`);
}
