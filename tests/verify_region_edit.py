"""Regional layout changes only selected nodes and their incident edges."""
from pathlib import Path
import sys,json,tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'editing') if (repo/'editing').exists() else '/app')
from diagram_edit import DiagramEditor,DiagramEditError
from edit_artifact import extract

def editor():return DiagramEditor(scale=1,timeout=90)
def expect(code,fn):
    try:fn()
    except DiagramEditError as e:
        assert e.code==code,(e.code,str(e),e.details);return e
    raise AssertionError('Expected '+code)
def op(r,ids,**kw):
    return editor().relayout_region(r['rendered']['png'],r['diagram_id'],r['revision'],ids,**kw)

source='flowchart LR\nX[Outside] --> A[First] -->|continue| B{Decision}\nB --> C([Done]) --> Y[Outside end]\nZ["Padding<br/>line<br/>line<br/>line<br/>line<br/>line<br/>line<br/>line<br/>line<br/>line<br/>line"]\n'
r=editor().create_diagram(source);original=deepcopy(r)
p=editor().preview_diagram_edit(r['rendered']['png'],r['diagram_id'],1,[{'op':'relayout_region','node_ids':['A','B','C'],'direction':'TB'}])
s=op(r,['A','B','C'],direction='TB')
assert p['revision']==1 and p['preview'] and r==original
assert s['revision']==2 and s['state']==r['state'] and s['source']==r['source']
assert p['rendered']['layout']==s['rendered']['layout']
successful_r,successful_s=r,s
selected_nodes={'A','B','C'}
affected={str(i) for i,e in enumerate(r['state']['edges']) if e['source'] in selected_nodes or e['target'] in selected_nodes}
def outside_svg(result):
    return [ET.tostring(child) for child in ET.fromstring(result['rendered']['svg'])
        if not child.tag.endswith('}metadata') and child.get('id') not in selected_nodes
        and child.get('data-ordinal') not in affected and child.get('data-edge-label') not in affected]
assert outside_svg(s)==outside_svg(r),'SVG outside the region and incident edges must be byte-equivalent'
assert s['rendered']['png']!=r['rendered']['png']

before={n['id']:n for n in r['rendered']['layout']['nodes']};after={n['id']:n for n in s['rendered']['layout']['nodes']}
assert before['X']==after['X'] and before['Y']==after['Y']
assert any(before[id]['box']!=after[id]['box'] for id in ['A','B','C'])
assert s['rendered']['layout']['subgraphs']==r['rendered']['layout']['subgraphs']
assert s['rendered']['layout']['width']==r['rendered']['layout']['width']
assert s['rendered']['layout']['height']==r['rendered']['layout']['height']
assert set(s['changes']['layout_changed']['nodes'])<=set(['A','B','C'])
assert extract(s['rendered']['svg'])==extract(s['rendered']['png'])
assert editor().get_diagram(s['rendered']['svg'],s['diagram_id'],2)['geometry']['positions']
with tempfile.TemporaryDirectory() as folder:
    dest=Path(folder)/'export';editor().export_diagram(s['rendered']['png'],s['diagram_id'],2,dest)
    assert json.loads((dest/'layout.json').read_text())==s['rendered']['layout']
    assert (dest/'diagram.png').read_bytes()==s['rendered']['png']
# Existing reroute API must work after a region edit, preserving moved nodes.
selected=s['state']['edges'][0]['id']
t=editor().reroute_edge(s['rendered']['png'],s['diagram_id'],2,selected)
assert t['rendered']['layout']['nodes']==s['rendered']['layout']['nodes']
u=op(s,['A','B','C'],direction='TB')
assert u['revision']==3
assert next(n for n in u['rendered']['layout']['nodes'] if n['id']=='X')==before['X']
assert next(n for n in u['rendered']['layout']['nodes'] if n['id']=='Y')==before['Y']
expect('id_not_found',lambda:editor().apply_diagram_edit(r['rendered']['png'],r['diagram_id'],1,[
    {'op':'relayout_region','node_ids':['A','B','C'],'direction':'TB'},
    {'op':'relayout_region','node_ids':['A','missing']}]))
assert r==original,'failed batch must not mutate input'

print('PASS region: preview/apply/export, moved nodes persist, outside nodes fixed, edge edit continues')

expect('invalid_argument',lambda:op(r,['A','A']))
expect('id_not_found',lambda:op(r,['A','missing']))
expect('invalid_argument',lambda:op(r,['A','B'],preserve_boundary=False))
expect('invalid_argument',lambda:op(r,['A','B'],goal='anything'))
expect('invalid_argument',lambda:op(r,['A','B'],bounds=[-1,-1,20,20]))
expect('region_too_small',lambda:op(r,['A','B'],bounds=[20,20,20,20]))
expect('stale_revision',lambda:editor().relayout_region(s['rendered']['png'],s['diagram_id'],1,['A','B']))
print('PASS region: bounds, IDs, unsupported requests and revisions validated')

source='flowchart LR\nsubgraph S[Selected area]\nA --> B --> C --> D\nend\nX --> A\nD --> Y\n'
r=editor().create_diagram(source)
s=op(r,['A','B'])
assert s['rendered']['layout']['subgraphs']==r['rendered']['layout']['subgraphs']
assert all(n==next(m for m in s['rendered']['layout']['nodes'] if m['id']==n['id']) for n in r['rendered']['layout']['nodes'] if n['id'] in ['X','Y'])
expect('invalid_argument',lambda:op(r,['X','A']))
print('PASS region: group frame and external nodes fixed, cross-group incident edges rerouted')

# Replay must not allow injected overlapping coordinates, even with a valid checksum.
from edit_artifact import pack,embed_svg
r,s=successful_r,successful_s
payload=extract(s['rendered']['png']);geometry=deepcopy(payload['geometry'])
old={n['id']:n for n in r['rendered']['layout']['nodes']}
geometry['positions']['A']=old['X']['box'][:2]
bad=embed_svg(editor()._render(s['source']).svg,pack(s['diagram_id'],2,s['source'],s['state'],geometry=geometry))
expect('invalid_geometry',lambda:editor().get_diagram(bad,s['diagram_id'],2))
print('PASS region: tampered node coordinates rejected')
