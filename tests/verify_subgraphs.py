from verify_geometry import *

shapes=(APP/'tests/fixtures/node-shapes.mmd').read_text()
assert {n['id']:n['type'] for n in metadata(shapes)['nodes']}==LEGACY
for header in ['flowchart','graph']:
    for direction in ['TB','TD','BT','RL','LR']:
        source=shapes.replace('flowchart TB',f'{header} {direction}')
        root,layout=run(source)
        assert len(layout['nodes'])==14 and not layout['subgraphs']
        check_geometry(root,layout)
        positions={n['id']:n['box'] for n in layout['nodes']}
        a,b=positions['rect'],positions['rounded']
        if direction in ['TB','TD']: assert a[1]+a[3]<b[1]
        if direction=='BT': assert b[1]+b[3]<a[1]
        if direction=='LR': assert a[0]+a[2]<b[0]
        if direction=='RL': assert b[0]+b[2]<a[0]
    print(f'PASS subgraphs: 14 legacy shapes, labels and boundary contacts; {header} TB/TD/BT/RL/LR')

modern=(APP/'tests/fixtures/modern-shapes.mmd').read_text()
root,layout=run(modern)
check_geometry(root,layout)
assert len(layout['nodes'])==14
print('PASS subgraphs: modern aliases of the 14 legacy shapes (odd, not paper-tape flag)')

source=(APP/'tests/fixtures/subgraphs.mmd').read_text()
meta=metadata(source)
expected_members={g['id']:g['nodes'] for g in meta['subgraphs']}
assert expected_members=={'inner':['C','B'],'outer':['A','inner','D'],'other':['F','E']}

def check_clusters(root,layout,expected_members):
    check_geometry(root,layout)
    nodes={n['id']:n for n in layout['nodes']}
    groups={g['id']:g for g in layout['subgraphs']}
    assert {g['id']:g['members'] for g in layout['subgraphs']}==expected_members
    assert not (set(nodes)&set(groups))
    entities={**nodes,**groups}
    for group in groups.values():
        for member in group['members']:
            assert contained(entities[member]['box'],group['box'],20), (group['id'],member)
            assert not overlaps(group['label_box'],entities[member]['box'])
        for i,member in enumerate(group['members']):
            for other in group['members'][i+1:]:
                assert not overlaps(entities[member]['box'],entities[other]['box'])
        # No edge or edge-label may run through any subgraph title.
        title=group['label_box']
        for edge in layout['edges']:
            assert not overlaps(title,edge['label_box'])
            for a,b in edge_segments(root,edge):
                assert not segment_hits_box(a,b,title), (group['id'],edge['ordinal'],'title intersected')
    # Root siblings are disjoint too.
    members={m for g in groups.values() for m in g['members']}
    roots=[e for id,e in entities.items() if id not in members]
    for i,a in enumerate(roots):
        for b in roots[i+1:]: assert not overlaps(a['box'],b['box'])
    # Edges cannot run through unrelated nodes.
    for edge in layout['edges']:
        for id,node in nodes.items():
            if id in [edge['source'],edge['target']]: continue
            for a,b in edge_segments(root,edge):
                assert not segment_hits_box(a,b,node['box']), (edge['ordinal'],id,'node crossed')
    return entities

def segment_hits_box(a,b,box):
    # Liang-Barsky intersection with an inset open rectangle, works for diagonals.
    x,y,w,h=box
    x+=0.01;y+=0.01;w-=0.02;h-=0.02
    if w<=0 or h<=0:return False
    dx,dy=b[0]-a[0],b[1]-a[1]
    lo,hi=0,1
    for p,q in [(-dx,a[0]-x),(dx,x+w-a[0]),(-dy,a[1]-y),(dy,y+h-a[1])]:
        if p==0:
            if q<0:return False
        elif p<0:lo=max(lo,q/p)
        else:hi=min(hi,q/p)
    return lo<hi and hi>0 and lo<1

for direction in ['TB','TD','BT','RL','LR']:
    root,layout=run(source.replace('flowchart LR',f'flowchart {direction}'))
    check_clusters(root,layout,expected_members)
    assert [(e['source'],e['target']) for e in layout['edges']]==[(e['start'],e['end']) for e in meta['edges']]
    assert [e['ordinal'] for e in layout['edges']]==list(range(8))
    assert len(layout['nodes'])==7 and len(layout['subgraphs'])==3
    print(f'PASS subgraphs: nested boxes, members, titles, internal/cross-boundary/cluster edges in {direction}')

# Official direction example: edges to clusters preserve private directions.
private='''flowchart LR
subgraph TOP ["Top level"]
  direction TB
  subgraph B1 ["Right to left"]
    direction RL
    i1 --> f1
  end
  subgraph B2 ["Bottom to top"]
    direction BT
    i2 --> f2
  end
  B1 --> B2
end
A --> TOP --> Z
'''
root,layout=run(private)
members={g['id']:g['nodes'] for g in metadata(private)['subgraphs']}
entities=check_clusters(root,layout,members)
assert entities['i1']['box'][0]>entities['f1']['box'][0]
assert entities['i2']['box'][1]>entities['f2']['box'][1]
assert entities['B1']['box'][1]<entities['B2']['box'][1]
print('PASS subgraphs: nested independent RL/BT directions and cluster-level TB ordering')

# Real regression: projected Dagre label waypoints and midpoint-only cluster
# ports used to send these edges far away and then back across the diagram.
detours=(APP/'tests/fixtures/cluster-port-detours.mmd').read_text()
root,layout=run(detours)
check_clusters(root,layout,{g['id']:g['nodes'] for g in metadata(detours)['subgraphs']})
if TEST_LAYOUT == 'dagre':
    for pair,limit in [(('INTENT','LOOP'),500),(('PICK','AGENTS'),850),(('PICK','LEAVES'),450)]:
        edge=next(e for e in layout['edges'] if (e['source'],e['target'])==pair)
        length=sum(math.dist(a,b) for a,b in zip(edge['points'],edge['points'][1:]))
        assert length<limit,(pair,length,'unnecessary cluster/label detour')
        assert edge['label_box'][2]>0
        # No upward excursion on these forward edges. Feedback edges elsewhere in
        # the fixture intentionally retain their original direction and topology.
        assert all(b[1]>=a[1]-1e-7 for a,b in zip(edge['points'],edge['points'][1:]))
print('PASS subgraphs: actual Intent/tool cluster detours, movable labels and near-side ports')

# Official limitation: same private direction, one link to cluster vs one to leaf.
limitation='''flowchart LR
subgraph kept ["Direction preserved"]
  direction TB
  top1 --> bottom1
end
subgraph inherited ["Direction inherited"]
  direction TB
  top2 --> bottom2
end
outside --> kept
outside --> top2
'''
root,layout=run(limitation)
entities=check_clusters(root,layout,{g['id']:g['nodes'] for g in metadata(limitation)['subgraphs']})
assert entities['top1']['box'][1]<entities['bottom1']['box'][1]
assert entities['top2']['box'][0]<entities['bottom2']['box'][0]
if TEST_LAYOUT == 'dagre': assert_close([entities['top2']['box'][1]],[entities['bottom2']['box'][1]])
print('PASS subgraphs: documented external-leaf direction fallback; cluster endpoint preserves direction')

# Real empty boxes, auto IDs, long/multiline titles, ancestor and self links.
extras='''graph TD
subgraph empty ["Nhãn nhóm rỗng rất dài và có dấu tiếng Việt"]
end
subgraph "Nhóm tự sinh ID"
  Q --> R
end
subgraph parent ["Tiêu đề nhiều dòng
Dòng thứ hai"]
  subgraph child ["Nhóm con"]
    N --> M
  end
  P
end
empty --> parent
parent --> N
M --> parent
child --> child
'''
root,layout=run(extras)
check_clusters(root,layout,{g['id']:g['nodes'] for g in metadata(extras)['subgraphs']})
assert any(g['id']=='subGraph1' for g in layout['subgraphs'])
assert next(g for g in layout['subgraphs'] if g['id']=='empty')['members']==[]
print('PASS subgraphs: empty/auto-ID/multiline groups, ancestor/descendant and cluster self-loop')

# Nested shape regression with private direction and real enclosing boxes.
lines=shapes.splitlines()
nested='flowchart LR\nsubgraph allshapes ["Tất cả shape"]\ndirection BT\nsubgraph nested ["Nhãn con rất dài để kiểm tra chiều rộng thực tế"]\ndirection RL\n'+'\n'.join(lines[1:])+'\nend\nend\n'
root,layout=run(nested)
check_clusters(root,layout,{g['id']:g['nodes'] for g in metadata(nested)['subgraphs']})
assert len(layout['nodes'])==14
snapshot=[(OUT/name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
run(nested)
assert snapshot==[(OUT/name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
print('PASS subgraphs: 14 shapes inside two nested groups and deterministic SVG/PNG/layout')

# Features outside this scope must fail explicitly, not disappear.
for source,expected in [
    ('flowchart TB\nA@{shape: flag}\n', 'Shape chưa được hỗ trợ'),
    ('flowchart TB\nsubgraph S\n A\nend\nS@{view: collapsed}\n', 'metadata chưa hỗ trợ'),
]:
    Path('/output/input.mmd').write_text(source)
    result=subprocess.run(['python3','/app/renderer.py',*layout_args(),'/output/input.mmd','--output','/output/rejected'],capture_output=True,text=True)
    assert result.returncode!=0
    detail=json.loads(result.stderr)
    assert detail['kind']=='source' and detail['category']=='source',detail
    assert expected in detail['message']
    assert not Path('/output/rejected').exists()
print('PASS subgraphs: unsupported paper-tape flag and collapsed metadata fail explicitly')

# br/entity conversion must shape the intended text, not literal markup or
# Mermaid's internal entity sentinels. Blank labels still resolve a real font.
source=(APP/'tests/fixtures/node-labels.mmd').read_text()
root,layout=run(source)
check_clusters(root,layout,{g['id']:g['nodes'] for g in metadata(source)['subgraphs']})
expected=json.loads(subprocess.check_output(['python3','/app/text_geometry.py'],input=json.dumps(['Nhãn\nDòng hai " &','','Tiêu đề\nDòng hai']).encode()))
for id,geometry in zip(['A','B','S'],expected):
    group=next(g for g in root.findall('s:g',NS) if g.attrib.get('id')==id)
    path=next(p for p in group.findall('s:path',NS) if 'transform' in p.attrib)
    assert path.attrib['d']==geometry['path']
assert layout['font_family_used']=='Noto Sans'
run('flowchart LR\nA[" "] --> B[" "]\n')
print('PASS subgraphs: br/entities rendered as text, blank labels resolve real font')

for direction in ['TB','LR']:
    root,layout=run(shapes.replace('flowchart TB',f'graph {direction}').replace('Nhãn rộng tiếng Việt','Nhãn nhiều dòng<br>Tiếng Việt có dấu<br>Dòng cuối'))
    check_geometry(root,layout)
print('PASS subgraphs: multiline label boxes inside all 14 shapes')

# Parallel edges across a cluster boundary retain independent labels/ordinals.
parallel='''flowchart LR
subgraph S ["Nhóm bên trái"]
 A --> B
end
subgraph T ["Nhóm bên phải"]
 C --> D
end
B -->|nhánh một| C
B -->|nhánh hai| C
S <-->|hai đầu| T
'''
root,layout=run(parallel)
check_clusters(root,layout,{g['id']:g['nodes'] for g in metadata(parallel)['subgraphs']})
assert [e['ordinal'] for e in layout['edges']]==list(range(5))
assert layout['edges'][2]['points']!=layout['edges'][3]['points']
assert not overlaps(layout['edges'][2]['label_box'],layout['edges'][3]['label_box'])
print('PASS subgraphs: parallel cross-boundary labels and double-headed cluster edge')

# No unsafe fallback when a generated ancestor label cannot fit at full clearance.
labelled_extras=extras.replace('parent --> N','parent -->|entry| N')
Path('/output/input.mmd').write_text(labelled_extras)
result=subprocess.run(['python3','/app/renderer.py',*layout_args(),'/output/input.mmd','--output','/output/no-label-room'],capture_output=True,text=True)
if TEST_LAYOUT == 'dagre':
    assert result.returncode!=0 and not Path('/output/no-label-room').exists()
    assert 'không đủ chỗ cho nhãn' in json.loads(result.stderr)['message']
    print('PASS subgraphs: no unsafe fallback for ancestor label without clearance')
else:
    assert result.returncode==0,result.stderr
    elk_root=ET.parse('/output/no-label-room/diagram.svg').getroot()
    elk_layout=json.loads(Path('/output/no-label-room/layout.json').read_text())
    check_clusters(elk_root,elk_layout,{g['id']:g['nodes'] for g in metadata(labelled_extras)['subgraphs']})
    print('PASS subgraphs ELK: labelled ancestor edge has real geometry and clear title')

if TEST_LAYOUT == 'elk':
    subprocess.run(['python3','/app/tests/verify_elk_render.py'],check=True,timeout=180)
