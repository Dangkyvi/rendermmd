// Pure geometry regressions run offline alongside the edge integration suite.
import assert from 'node:assert/strict';
import {segmentClear,segmentHitsBox,orthogonalRoute,ancestorObstacles,labelOnRoute} from '../subgraph-layout.mjs';
const p=(x,y)=>({x,y});
const box=[4,4,6,6];
assert(!segmentHitsBox(p(0,0),p(0,10),box));
assert(!segmentHitsBox(p(0,0),p(0,0),box));
assert(!segmentClear(p(0,0),p(10,10),[box]),'a segment must avoid the obstacle throughout its length');
const bands=ancestorObstacles([0,0,100,100],20);
assert(segmentClear(p(-20,50),p(20,50),bands));
assert(!segmentClear(p(5,30),p(5,80),bands),'no parallel travel next to ancestor border');
assert(!segmentClear(p(30,-10),p(30,40),bands),'title is solid');
assert.throws(()=>orthogonalRoute([{boundary:p(0,5),gate:p(10,5)}],[{boundary:p(20,5),gate:p(20,5)}],[[4,4,6,6]],[0,0,25,10]),'blocked boundary-to-gate lead must be rejected');
console.log('PASS routing: segment intersections, blocked endpoint leads and ancestor title/border bands');
const sourceHalo=Object.assign([-10,-10,10,20],{endpoint:'A'});
const targetHalo=Object.assign([40,-10,60,20],{endpoint:'B'});
const withHalos=orthogonalRoute([{boundary:p(0,5),gate:p(16,5),node:'A'}],[{boundary:p(50,5),gate:p(34,5),node:'B'}],[sourceHalo,targetHalo],[-20,-20,70,30]);
assert(withHalos.slice(2,-1).every((q,i)=>segmentClear(withHalos[i+1],q,[sourceHalo,targetHalo])));
console.log('PASS routing: endpoint halos are exempt only on their selected leads');

const labelRoute=[p(0,0),p(16,0),p(116,0),p(132,0)];
const placed=labelOnRoute(labelRoute,20,10,[],[-30,-30,160,30]);
assert(placed && placed.points.some(q=>q===placed.position));
assert(placed.position.x>=36 && placed.position.x<=96,'label avoids endpoint leads');
assert.equal(labelOnRoute(labelRoute,200,10,[],[-30,-30,160,30]),null,'retain original if label cannot fit');
assert.equal(labelOnRoute(labelRoute,20,10,[[16,-20,116,20]],[-30,-30,160,30]),null,'whole label clearance box must fit');
assert.equal(labelOnRoute(labelRoute,20,10,[],[-30,-30,160,30],[[p(16,0),p(116,0)]]),null,'moving a label must not cover an already routed edge');
console.log('PASS routing: labels on actual route, protected leads, clearance and optional fallback');

// Same endpoints, same hard geometry. Occupancy must influence the chosen
// Dijkstra route, rather than merely changing metadata or postprocessing it.
const ends=[{boundary:p(100,0),gate:p(100,0)}],starts=[{boundary:p(0,0),gate:p(0,0)}];
const occupied=[p(0,0),p(100,0)],frame=[0,-30,100,30];
const baseline=orthogonalRoute(starts,ends,[],frame);
const separated=orthogonalRoute(starts,ends,[],frame,{wires:[occupied]});
assert(baseline.every(q=>q.y===0));
assert(separated.some(q=>Math.abs(q.y)>=12),'use a separate lane instead of retracing the occupied wire');
assert.deepEqual(separated,orthogonalRoute(starts,ends,[],frame,{wires:[occupied]}),'stable tie breaking');
const bends=ps=>ps.slice(1,-1).filter((b,i)=>{
  const a=ps[i],c=ps[i+2];return Math.abs((b.x-a.x)*(c.y-b.y)-(b.y-a.y)*(c.x-b.x))>1e-7;
}).length;
assert.equal(bends(separated),2,'two bends suffice for a parallel bypass');
const blocked=[40,-20,60,20];
const aroundBlock=orthogonalRoute(starts,ends,[blocked],frame,{wires:[occupied]});
assert(aroundBlock.slice(1).every((q,i)=>segmentClear(aroundBlock[i],q,[blocked])),'soft wire costs cannot bypass hard obstacles');
const crossing=[p(50,-10),p(50,10)];
const avoidCrossing=orthogonalRoute(starts,ends,[],frame,{wires:[crossing]});
assert(avoidCrossing.some(q=>Math.abs(q.y)>=12),'a modest detour avoids a crossing');
console.log('PASS Dijkstra: occupied lanes, crossing costs, two-bend bypass, hard obstacles and deterministic output');
