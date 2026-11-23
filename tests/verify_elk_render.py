"""Real offline ELK SVG/PNG checks inside the renderer Docker runtime."""
from verify_geometry import *
import sys
sys.path.insert(0, '/app')
from renderer import render, RendererError

def check(source,raw=False):
    result=render(source, scale=1, timeout=60, layout='elk',raw_edges=raw)
    root=ET.fromstring(result.svg)
    assert root.attrib['data-layout-engine']=='elk'
    assert root.attrib['data-edge-routing']=='elk-orthogonal'
    assert root.attrib['data-edge-postprocessing']=='none'
    assert all(r==0 for edge in result.layout['edges'] for r in edge['corner_radii'])
    check_geometry(root,result.layout)
    entities={n['id']:n for n in result.layout['nodes']+result.layout['subgraphs']}
    for g in result.layout['subgraphs']:
        assert contained(g['label_box'],g['box'])
        for id in g['members']:
            assert contained(entities[id]['box'],g['box'],20),(g['id'],id)
            assert not overlaps(entities[id]['box'],g['label_box'])
    return result,entities

def check_raw_ports(source):
    result,_=check(source,True)
    for edge in result.layout['edges']:
        for a,b in zip(edge['points'],edge['points'][1:]):
            assert abs(a[0]-b[0])<1e-6 or abs(a[1]-b[1])<1e-6,(edge['ordinal'],'port clipping changed ELK segment axis')
            for n in result.layout['nodes']:
                if n['id'] in (edge['source'],edge['target']):continue
                x,y,w,h=n['box'];eps=.01
                hit=(abs(a[1]-b[1])<1e-6 and y+eps<a[1]<y+h-eps and max(a[0],b[0])>x+eps and min(a[0],b[0])<x+w-eps) or (
                    abs(a[0]-b[0])<1e-6 and x+eps<a[0]<x+w-eps and max(a[1],b[1])>y+eps and min(a[1],b[1])<y+h-eps)
                assert not hit,(edge['ordinal'],n['id'],'node crossed after port clipping')

source=(APP/'tests/fixtures/subgraphs.mmd').read_text()
for direction in ['LR','TB','TD','RL','BT']:
    result,_=check(source.replace('flowchart LR',f'flowchart {direction}'))
    assert len(result.layout['nodes'])==7 and len(result.layout['edges'])==8 and len(result.layout['subgraphs'])==3
    print(f'PASS ELK real {direction}: nested groups, leaf/cluster endpoints, shapes, glyphs and marker contacts')

private='''flowchart LR
subgraph S ["Nhóm hướng riêng"]
 direction TB
 A --> B
end
X --> S --> Z
'''
_,entities=check(private)
assert entities['A']['box'][1]<entities['B']['box'][1]
print('PASS ELK real: private group TB direction inside LR diagram')

extras='''flowchart TB
subgraph empty ["Nhóm rỗng với tiêu đề rất dài để kiểm tra kích thước"]
end
subgraph parent ["Nhóm cha"]
 subgraph child ["Nhóm con"]
  A --> B
 end
end
empty --> parent
parent --> A
B --> parent
child --> child
'''
check(extras)
print('PASS ELK real: empty long-title group, ancestor/descendant edges and cluster self-loop')

shapes=(APP/'tests/fixtures/node-shapes.mmd').read_text()
check(shapes)
print('PASS ELK real: all 14 node shapes, exact outline/marker contacts')

styled='''---
config:
  theme: dark
---
flowchart LR
subgraph outer ["Ngoài"]
 subgraph inner ["Trong"]
  A["Tiếp nhận"] -->|hợp lệ| B{"Xác nhận"}
 end
end
subgraph target ["Đích"]
 C["Hoàn tất"]
end
B --> C
outer --> target
classDef special fill:#ffdddd,stroke:#aa0033,color:#111111
class A special
style inner fill:#eeeeff,stroke:#3333aa
linkStyle 1 stroke:#ee9900,stroke-width:3px
'''
a=render(styled,scale=1,layout='dagre');b,_=check(styled)
def paints(root):
    return [(e.attrib.get('id'),{k:v for k,v in e.attrib.items() if k in ('fill','stroke','stroke-width','font-family','font-size','font-weight','font-style')}) for child in root if not child.tag.endswith('}defs') for e in child.iter()]
assert paints(ET.fromstring(a.svg))==paints(ET.fromstring(b.svg))
print('PASS ELK real: theme, custom node/edge/group styles and fonts preserved')
try: render(source,layout='unknown')
except RendererError as error: assert error.code=='invalid_argument'
else: raise AssertionError('invalid layout accepted')

# Spacing changes geometry, never node/font sizes. Default 1 remains identical.
for grouped in (False,True):
    source='flowchart TB\n'+('subgraph S\n' if grouped else '')+'A --> B\n'+('end\n' if grouped else '')
    baseline=render(source,scale=1,layout='elk')
    assert baseline==render(source,scale=1,layout='elk',elk_spacing=1)
    expanded=render(source,scale=1,layout='elk',elk_spacing=1.5)
    nodes={n['id']:n['box'] for n in baseline.layout['nodes']}
    larger={n['id']:n['box'] for n in expanded.layout['nodes']}
    gap=nodes['B'][1]-nodes['A'][1]-nodes['A'][3]
    gap2=larger['B'][1]-larger['A'][1]-larger['A'][3]
    assert abs(gap2-gap*1.5)<1e-6,(grouped,gap,gap2)
    assert {id:b[2:] for id,b in nodes.items()}=={id:b[2:] for id,b in larger.items()}
    check_geometry(ET.fromstring(expanded.svg),expanded.layout)
for value in (0,-1,float('nan'),float('inf'),5,True):
    try: render('flowchart TB\nA --> B',layout='elk',elk_spacing=value)
    except RendererError as error: assert error.code=='invalid_argument'
    else: raise AssertionError(('invalid spacing accepted',value))
print('PASS ELK spacing: exact simple-chain factor at root and in group, unchanged nodes, default bytes and invalid arguments')

# Multi-level compound ports, parallel labelled wires and independent groups.
check((APP/'tests/fixtures/compound-boundaries.mmd').read_text())
print('PASS ELK: compound boundary regression fixture')
check_raw_ports(shapes)
check_raw_ports((APP/'tests/fixtures/cluster-port-detours.mmd').read_text())
print('PASS ELK raw ports: all 14 shapes and dense fixture preserve segment axes and avoid unrelated nodes')
native_source=(APP/'tests/fixtures/cluster-port-detours.mmd').read_text()
assert render(native_source,layout='elk',scale=1)==render(native_source,layout='elk',scale=1,raw_edges=True)
assert render(native_source,layout='elk',scale=1,raw_edges=False)==render(native_source,layout='elk',scale=1,raw_edges=True)
print('PASS ELK default: explicit false, true and omitted raw_edges keep identical original routing')

# Prove this branch cannot silently fall back to Dagre layout or Dijkstra.
import tempfile, shutil
from unittest.mock import patch
import renderer
from runtime_version import BACKEND_FILES
with tempfile.TemporaryDirectory() as folder:
    backend=Path(folder)
    for name in BACKEND_FILES: shutil.copyfile(APP/name,backend/name)
    (backend/'node_modules').symlink_to(APP/'node_modules',target_is_directory=True)
    helper=backend/'subgraph-layout.mjs'
    helper.write_text(helper.read_text().replace('dagre.layout(local);',
        "(()=>{throw new Error('FORBIDDEN_DAGRE');})();").replace(
        'export function orthogonalRoute(starts, ends, obstacles, frame, options={}) {',
        'export function orthogonalRoute(starts, ends, obstacles, frame, options={}) { throw new Error("FORBIDDEN_DIJKSTRA");'))
    main=backend/'draw-probe.mjs'
    main.write_text(main.read_text().replace('dagre.layout(graph);',
        "(()=>{throw new Error('FORBIDDEN_DAGRE');})();"))
    with patch.object(renderer,'_BACKEND',main):
        check((APP/'tests/fixtures/compound-boundaries.mmd').read_text())
        check('flowchart LR\nA --> B\n')
        try: render('flowchart LR\nA --> B\n',layout='dagre')
        except RendererError as error: assert 'FORBIDDEN_DAGRE' in str(error)
        else: raise AssertionError('guard did not disable Dagre')
print('PASS ELK pure branch: renders with Dagre layout and Dijkstra disabled')
