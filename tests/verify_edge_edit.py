"""Local edge edits persist through PNG/SVG, fresh services and export."""
from pathlib import Path
import sys, json, tempfile
from copy import deepcopy
import xml.etree.ElementTree as ET
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'editing') if (repo/'editing').exists() else '/app')
from diagram_edit import DiagramEditor,DiagramEditError,_bridge
from edit_artifact import extract,pack,embed_svg

def expect(code,fn):
    try:fn()
    except DiagramEditError as e:
        assert e.code==code,(e.code,str(e));return
    raise AssertionError('Expected '+code)

def service():return DiagramEditor(scale=1,timeout=60)
def apply(r,ops,preview=False):
    return getattr(service(),'preview_diagram_edit' if preview else 'apply_diagram_edit')(
        r['rendered']['png'],r['diagram_id'],r['revision'],ops)

source='flowchart LR\nA[Start] -->|yes| B[End]\nA --> B\nC[Other]\n'
r=service().create_diagram(source)
a,b=[e['id'] for e in r['state']['edges']]
original=deepcopy(r)
ops=[{'op':'reroute_edge','edge_id':a,'prefer_side':'bottom','avoid_overlap_with':[b]}]
p=apply(r,ops,True)
assert p['preview'] and p['revision']==r['revision'] and r==original
expect('preview_artifact',lambda:service().get_diagram(p['rendered']['png'],r['diagram_id'],r['revision']))
s=apply(r,ops)
assert s['revision']==2 and extract(s['rendered']['png'])==extract(s['rendered']['svg'])
assert extract(s['rendered']['png'])['schema']==2
assert s['rendered']['layout']['nodes']==r['rendered']['layout']['nodes']
assert s['rendered']['layout']['subgraphs']==r['rendered']['layout']['subgraphs']
assert s['rendered']['layout']['edges'][1]==r['rendered']['layout']['edges'][1]
assert s['rendered']['layout']['edges'][0]['points']!=r['rendered']['layout']['edges'][0]['points']
assert a in extract(s['rendered']['png'])['geometry']['labels']
assert s['changes']['layout_changed']=={'nodes':[],'edges':[a],'subgraphs':[]}
assert s['state']==r['state'] and s['source']==r['source']
assert s['rendered']['layout']['edges'][0]['points'][0]==r['rendered']['layout']['edges'][0]['points'][0]
assert s['rendered']['layout']['edges'][0]['points'][-1]==r['rendered']['layout']['edges'][0]['points'][-1]
def outside_svg(result):
    root=ET.fromstring(result['rendered']['svg'])
    return [ET.tostring(child) for child in root
            if not child.tag.endswith('}metadata') and child.get('data-ordinal')!='0' and child.get('data-edge-label')!='0']
assert outside_svg(s)==outside_svg(r), 'all unselected SVG primitives must stay identical'
assert service().get_diagram(s['rendered']['svg'],s['diagram_id'],2)['geometry']['routes'][a]
direct=service().reroute_edge(r['rendered']['svg'],r['diagram_id'],1,a,avoid_overlap_with=[b],prefer_side='bottom')
assert direct['rendered']['layout']==s['rendered']['layout']

assert p['rendered']['layout']==s['rendered']['layout']
with tempfile.TemporaryDirectory() as folder:
    destination=Path(folder)/'export'
    service().export_diagram(s['rendered']['svg'],s['diagram_id'],2,destination)
    assert json.loads((destination/'layout.json').read_text())==s['rendered']['layout']
    assert (destination/'diagram.png').read_bytes()==s['rendered']['png']
    assert extract((destination/'diagram.svg').read_bytes())['geometry']==extract(s['rendered']['png'])['geometry']
print('PASS edge edit: preview/apply, only selected edge changes, export replays same geometry')
t=apply(s,[{'op':'reroute_edge','edge_id':b,'prefer_side':'top','avoid_overlap_with':[a]}])
assert t['rendered']['layout']['edges'][0]==s['rendered']['layout']['edges'][0]
assert len(extract(t['rendered']['png'])['geometry']['routes'])==2
expect('stale_revision',lambda:service().reroute_edge(s['rendered']['png'],s['diagram_id'],1,a))
expect('id_not_found',lambda:apply(r,[{'op':'reroute_edge','edge_id':'missing'}]))
expect('invalid_argument',lambda:apply(r,[{'op':'reroute_edge','edge_id':a,'prefer_side':'wrong'}]))
expect('invalid_argument',lambda:apply(r,[{'op':'reroute_edge','edge_id':a,'avoid_overlap_with':[a]}]))
expect('invalid_argument',lambda:apply(r,[{'op':'reroute_edge','edge_id':a},{'op':'delete_edge','edge_id':b}]))
expect('geometry_edit_conflict',lambda:apply(s,[{'op':'update_node_label','node_id':'A','label':'changed'}]))
# A recomputed checksum is not authority to inject arbitrary geometry.
payload=extract(s['rendered']['png']);g=deepcopy(payload['geometry']);g['routes'][a][0][0]+=10
bad=embed_svg(service()._render(payload['source']).svg,pack(s['diagram_id'],2,s['source'],s['state'],geometry=g))
with tempfile.TemporaryDirectory() as folder:
    expect('invalid_geometry',lambda:service().export_diagram(bad,s['diagram_id'],2,Path(folder)/'bad'))
g=deepcopy(payload['geometry']);g['renderer_version']='changed'
bad=embed_svg(service()._render(payload['source']).svg,pack(s['diagram_id'],2,s['source'],s['state'],geometry=g))
with tempfile.TemporaryDirectory() as folder:
    expect('layout_incompatible',lambda:service().export_diagram(bad,s['diagram_id'],2,Path(folder)/'bad'))
print('PASS edge edit: successive edits, revisions, argument validation, tampered routes and incompatible renderer rejected')

# Contacts remain correct on real shape outlines, compound and double arrows.
for name,source in [
    ('double','flowchart LR\nA([Start]) <--> B{End}\n'),
    ('nested','flowchart LR\nsubgraph S[Outer]\nA -->|go| B\nend\nB --> C\n'),
    ('ancestor','flowchart LR\nsubgraph S[Outer]\nA --> B\nend\nS --> A\n'),
]:
    r=service().create_diagram(source)
    selected=r['state']['edges'][-1]['id']
    s=apply(r,[{'op':'reroute_edge','edge_id':selected}])
    assert s['rendered']['layout']['nodes']==r['rendered']['layout']['nodes']
    assert s['rendered']['layout']['subgraphs']==r['rendered']['layout']['subgraphs']
    print('PASS edge edit:',name,'endpoints, labels and compound obstacles')

r=service().create_diagram('flowchart LR\nA --> B\nC\n')
blocked=deepcopy(r['rendered']['layout'])
next(n for n in blocked['nodes'] if n['id']=='C')['box']=[0,0,blocked['width'],blocked['height']]
expect('routing_failed',lambda:_bridge({'action':'route_edge','state':r['state'],
    'layout':blocked,'edge_id':r['state']['edges'][0]['id']},60))
print('PASS edge edit: no-space routing fails explicitly')

# Old label coordinates cannot constrain the newly computed route/label.
r=service().create_diagram('flowchart LR\nA -->|yes| B\nC[Obstacle]\n')
layout=r['rendered']['layout'];id=r['state']['edges'][0]['id']
request={'action':'route_edge','state':r['state'],'edge_id':id,'prefer_side':'bottom',
         'relocate_label':True,'label_size':layout['edges'][0]['label_box'][2:]}
normal=_bridge({**request,'layout':deepcopy(layout)},60)
moved=deepcopy(layout);obstacle=next(n for n in moved['nodes'] if n['id']=='C')
moved['edges'][0]['label_box'][:2]=obstacle['box'][:2]
assert _bridge({**request,'layout':moved},60)==normal
assert _bridge({**request,'layout':deepcopy(layout),'prefer_side':'top'},60)==normal, 'legacy side cannot impose a waypoint'
print('PASS edge label: route first, label placed afterwards; old label position has no influence')
