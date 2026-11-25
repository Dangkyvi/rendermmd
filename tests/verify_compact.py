"""Connection-aware Dagre integration: balanced placement and real routed geometry."""
from verify_geometry import *
import sys
sys.path.insert(0, str(APP))
assert TEST_LAYOUT == "dagre", "compact checks exercise Dagre only"
subprocess.run(['node',str(APP/'tests/verify_connected_layout.mjs')],check=True)


def hits(a, b, box):
    # Open segment/rectangle intersection, including diagonal Dagre segments.
    x, y, w, h = box
    lo, hi = 0., 1.
    for value, delta, lower, upper in ((a[0], b[0]-a[0], x+.01, x+w-.01),
                                       (a[1], b[1]-a[1], y+.01, y+h-.01)):
        if upper <= lower:
            return False
        if abs(delta) < 1e-12:
            if value <= lower or value >= upper:
                return False
        else:
            t, u = (lower-value)/delta, (upper-value)/delta
            lo, hi = max(lo, min(t, u)), min(hi, max(t, u))
    return lo < hi


def validate(result):
    root, layout = ET.fromstring(result.svg), result.layout
    check_geometry(root, layout)
    entities = {n['id']: n for n in layout['nodes'] + layout['subgraphs']}
    parents = {m: g['id'] for g in layout['subgraphs'] for m in g['members']}
    for i, a in enumerate(entities.values()):
        for b in list(entities.values())[i+1:]:
            if parents.get(a['id']) == parents.get(b['id']):
                assert not overlaps(a['box'], b['box']), (a['id'], b['id'])
    for g in layout['subgraphs']:
        for member in g['members']:
            assert contained(entities[member]['box'], g['box'], 20), (g['id'], member)
            assert not overlaps(entities[member]['box'], g['label_box'])
    for edge in layout['edges']:
        for node in layout['nodes']:
            assert not overlaps(edge['label_box'], node['box']), ('label/node', edge['ordinal'], node['id'])
            if node['id'] not in (edge['source'], edge['target']):
                assert not any(hits(a, b, node['box']) for a, b in zip(edge['points'], edge['points'][1:])), ('edge/node', edge['ordinal'], node['id'])
        for group in layout['subgraphs']:
            assert not overlaps(edge['label_box'], group['label_box'])
            assert not any(hits(a, b, group['label_box']) for a, b in zip(edge['points'], edge['points'][1:])), ('edge/title', edge['ordinal'], group['id'])
    return layout


for direction in ('TB', 'BT', 'LR', 'RL'):
    source = f'flowchart {direction}\n' + '\n'.join(f'N{i}[Step {i}] -->|next {i}| N{i+1}' for i in range(23))
    result = selected_render(source, scale=1, timeout=90)
    layout = validate(result)
    nodes = {n['id']: n['box'] for n in layout['nodes']}
    axis = 0 if direction in ('TB', 'BT') else 1
    assert len({round(b[axis]+b[axis+2]/2, 3) for b in nodes.values()}) == 1, 'ungrouped chain must retain Dagre ranks'
    again = selected_render(source, scale=1, timeout=90)
    assert result == again, 'layout, SVG and PNG must repeat exactly'
    print('PASS compact:', direction, layout['width'], layout['height'], 'labels, geometry, unchanged Dagre ranks and deterministic output')

for direction in ('TD', 'LR'):
    fan = f'flowchart {direction}\n' + '\n'.join(f'A --> N{i}[Branch {i}]\nN{i} --> Z' for i in range(16))
    layout = validate(selected_render(fan, scale=1, timeout=90))
    print('PASS compact: broad fan-out', direction, layout['width'], layout['height'])

# Connected stages are positioned by port/wire relationships, not row filling.
stages = 'flowchart TD\n' + '\n'.join(
    f'subgraph S{i}[Stage {i}]\nA{i} --> B{i}\nend' for i in range(9))
stages += '\n' + '\n'.join(f'S{i} --> S{i+1}' for i in range(8))
layout = validate(selected_render(stages, scale=1, timeout=90))
boxes = {g['id']:g['box'] for g in layout['subgraphs']}
assert len({round(b[0],3) for b in boxes.values()})>1
assert len({round(b[1],3) for b in boxes.values()})>1
assert .5<layout['width']/layout['height']<4
print('PASS connected stages: two-dimensional placement, disjoint groups and real routed geometry')

# Renaming IDs cannot change geometry: the policy uses topology, not names.
topology = 'flowchart TD\n' + '\n'.join(f'N{i}[Step] --> N{i+1}[Step]' for i in range(6))
topology += '\nN3 --> P[Branch]\nN3 --> Q[Branch]\nP --> J[Join]\nQ --> J\nJ --> N4\nN6 --> N0'
first = validate(selected_render(topology, scale=1, timeout=90))
import re
renamed = re.sub(r'\b(N[0-9]+|P|Q|J)\b', lambda m: 'X'+m[0], topology)
second = validate(selected_render(renamed, scale=1, timeout=90))
assert {n['id']: n['box'] for n in first['nodes']} == {
    n['id'][1:]: n['box'] for n in second['nodes']}
print('PASS compact: branch/join with feedback, ID-independent geometry')

nested = '''flowchart TD
subgraph pipeline[Pipeline]
subgraph first[First stage]
A --> B --> C --> D --> E --> F --> G --> H
end
subgraph second[Second stage]
I --> J --> K --> L --> M --> N --> O --> P
end
H -->|continue| I
end
P -->|retry| A
P --> Z
'''
validate(selected_render(nested, scale=1, timeout=90))
print('PASS compact: nested groups, cross-group labelled edge and retry')

independent = 'flowchart TD\nsubgraph S[Independent]\n' + '\n'.join(f'N{i}[Worker {i}]' for i in range(16)) + '\nend'
layout = validate(selected_render(independent, scale=1))
assert len({n['box'][1] for n in layout['nodes']}) == 1
print('PASS compact: independent leaf nodes retain original Dagre rank')

if len(sys.argv) > 1:
    source = Path(sys.argv[1]).read_text()
    layout = validate(selected_render(source, scale=1, timeout=120))
    print('PASS compact: real source', sys.argv[1], layout['width'], layout['height'])
