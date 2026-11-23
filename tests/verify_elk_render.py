"""Real offline ELK SVG/PNG checks inside the renderer Docker runtime."""
from verify_geometry import *
import sys
sys.path.insert(0, '/app')
from renderer import render, RendererError

def check(source):
    result=render(source, scale=1, timeout=60, layout='elk')
    root=ET.fromstring(result.svg)
    assert root.attrib['data-layout-engine']=='elk'
    assert root.attrib['data-edge-routing']=='elk-orthogonal'
    check_geometry(root,result.layout)
    entities={n['id']:n for n in result.layout['nodes']+result.layout['subgraphs']}
    for g in result.layout['subgraphs']:
        assert contained(g['label_box'],g['box'])
        for id in g['members']:
            assert contained(entities[id]['box'],g['box'],20),(g['id'],id)
            assert not overlaps(entities[id]['box'],g['label_box'])
    return result,entities

source=(APP/'tests/fixtures/subgraphs.mmd').read_text()
for direction in ['LR','TB','RL','BT']:
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
