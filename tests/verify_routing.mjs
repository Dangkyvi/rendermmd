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

// A real neighbouring wire creates safe lanes, without synthetic guides.
const longStarts=[{boundary:p(0,0),gate:p(0,0)}],longEnds=[{boundary:p(1000,0),gate:p(1000,0)}];
const neighbour=[p(0,36),p(1000,36)],bundleFrame=[0,-48,1000,72];
const withoutBundle=orthogonalRoute(longStarts,longEnds,[],bundleFrame,{wires:[neighbour],parallelPreference:0});
const bundled=orthogonalRoute(longStarts,longEnds,[],bundleFrame,{wires:[neighbour]});
assert(withoutBundle.every(q=>q.y===0),'without affinity, shortest direct route wins');
assert(bundled.some(q=>q.y===24),'prefer a safe parallel lane at 12 units from a real wire');
for(let i=1;i<bundled.length;i++)if(bundled[i].y===bundled[i-1].y&&Math.abs(bundled[i].x-bundled[i-1].x)>100)
  assert(Math.abs(bundled[i].y-36)>=12,'bundling cannot follow too close');
assert.deepEqual(bundled,orthogonalRoute(longStarts,longEnds,[],bundleFrame,{wires:[neighbour]}));
const stillBlocked=orthogonalRoute(longStarts,longEnds,[[400,-20,600,50]],bundleFrame,{wires:[neighbour]});
assert(stillBlocked.slice(1).every((q,i)=>segmentClear(stillBlocked[i],q,[[400,-20,600,50]])));
const duplicateWires=Array.from({length:20},()=>neighbour);
const shortEnd=[{boundary:p(100,0),gate:p(100,0)}];
const short=orthogonalRoute(starts,shortEnd,[],[0,-48,100,72],{wires:duplicateWires});
assert(short.every(q=>q.y===0),'parallel credit cannot stack to justify a large detour');
console.log('PASS bundling: real-wire grid lanes, safe spacing, non-stacking preference, no forced waypoint and hard obstacles');
const shortJog=[p(0,0),p(24,0),p(50,0),p(50,2),p(76,2),p(100,2)];
assert.equal(labelOnRoute(shortJog,24,12,[],[-20,-30,120,30]),null);
const jogLabel=labelOnRoute(shortJog,24,12,[],[-20,-30,120,30],[],null,{allowAcrossGates:true});
assert(jogLabel,'a label can span a small bend if its box is clear');
assert.deepEqual(jogLabel.points[1],shortJog[1]);
assert.deepEqual(jogLabel.points.at(-2),shortJog.at(-2));
console.log('PASS label: short routed body supports a free label without artificial waypoints or changed endpoint gates');
