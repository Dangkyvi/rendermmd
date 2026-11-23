from verify_common import *

subprocess.run(['node','/app/tests/verify_routing.mjs'],check=True)

source = (APP / 'tests/fixtures/edges.mmd').read_text()
root, layout = run(source)
expected_pairs = [('arrow','A'), ('A','B'), ('B','C'), ('C','D'), ('D','E'), ('E','F'), ('F','G'),
                  ('G','H'), ('H','I'), ('I','J'), ('J','K'), ('K','L'), ('L','M'), ('M','N'),
                  ('N','O'), ('O','P'), ('P','Q'), ('Q','R'), ('A','B'), ('A','B'),
                  ('R','S'), ('S','T'), ('T','V'), ('T','W'), ('U','V'), ('U','W'),
                  ('W','arrow'), ('V','V'), ('aiz-marker-point','aiz-marker-point-1')]
assert [(e['source'],e['target']) for e in layout['edges']] == expected_pairs
assert [e['ordinal'] for e in layout['edges']] == list(range(29))
# Independent expectations for metadata, including none and double variants.
strokes = ['normal','normal','dotted','thick','invisible'] + ['normal']*5 + ['thick','dotted','thick','thick','dotted','dotted','dotted','thick'] + ['normal']*11
ends = ['point',None,'point','point',None,'circle','cross','point','circle','cross','point','point','circle','cross','circle','cross',None,None] + ['point']*11
starts = [None]*7 + ['point','circle','cross','point','point','circle','cross','circle','cross'] + [None]*13
for i, (stroke, start, end) in enumerate(zip(strokes, starts, ends)):
    line = root.find(f"s:path[@data-ordinal='{i}']", NS)
    attrs = line.attrib
    if stroke == 'invisible':
        assert attrs['stroke'] == 'none' and attrs['visibility'] == 'hidden'
        assert root.find(f"s:g[@data-edge-label='{i}']", NS) is None
    else:
        assert float(attrs['stroke-width']) == (3.5 if stroke == 'thick' else 1.5)
        assert attrs.get('stroke-dasharray') == ('3 3' if stroke == 'dotted' else None)
        assert attrs['stroke'] == ('#123456' if i == 18 else '#334155')
    for side, kind in [('start',start), ('end',end)]:
        ref = attrs.get(f'marker-{side}')
        if kind is None:
            assert ref is None
        else:
            marker_id = re.fullmatch(r'url\(#(.*)\)', ref).group(1)
            marker = next(e for e in root.findall('s:defs/s:marker', NS) if e.attrib['id'] == marker_id)
            assert marker.attrib['data-marker-type'] == kind
            assert marker.attrib['orient'] == 'auto-start-reverse'
            assert marker.attrib['markerUnits'] == 'userSpaceOnUse'
            assert marker.attrib['refX'] == '0'
            assert marker_id not in {n['id'] for n in layout['nodes']}
            if kind == 'point':
                assert marker.find('s:path', NS).attrib['d'] == 'M 0 -4 L 8 0 L 0 4 Z'
            elif kind == 'circle':
                c = marker.find('s:circle', NS)
                assert float(c.attrib['cx']) + float(c.attrib['r']) + float(c.attrib['stroke-width'])/2 == 8
            else:
                c = marker.find('s:path', NS)
                assert len(re.findall('M',c.attrib['d'])) == 2 and c.attrib['fill'] == 'none'
                context = path_context(c.attrib['d'])
                context.set_line_width(float(c.attrib['stroke-width']))
                context.set_line_cap(cairo.LINE_CAP_BUTT)
                assert abs(context.stroke_extents()[2] - 8) < 0.005
assert layout['edges'][18]['points'] != layout['edges'][19]['points']
assert layout['edges'][18]['label_box'] != layout['edges'][19]['label_box']
assert all(layout['edges'][i]['label_box'][2] > 0 for i in [18,19])
# Repeated processes must return the same bytes.
first = [(OUT / name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
subprocess.run(['python3','/app/renderer.py',*layout_args(),'/output/input.mmd',
                '--raw-edges','--output','/output/raw-compat'],check=True,timeout=35)
assert first==[(Path('/output/raw-compat')/name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
run(source)
assert first == [(OUT / name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
print('PASS edges: strokes, markers, invisible, ordinal, parallel, chain, &, cycles, geometry, PNG, deterministic')
print('PASS edges: legacy --raw-edges and default output are byte-identical')

metadata = json.loads(subprocess.check_output([
    'node', '/app/tests/inspect-edges.mjs', '/app/tests/fixtures/edges.mmd']))['edges']
assert [e['stroke'] for e in metadata] == strokes
for i, e in enumerate(metadata):
    kind = ends[i]
    expected_type = 'arrow_open' if kind is None else ('double_' if starts[i] else '') + 'arrow_' + kind
    assert e['type'] == expected_type
assert metadata[18]['id'].endswith('_2')  # This is NOT ordinal 18.

# Invisible labels (even unsupported glyphs) cannot affect paths, labels or raster.
run(source.replace('|hidden|', '|invisible label changed: 🫠|'))
assert first == [(OUT / name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]

shapes = (APP / 'tests/fixtures/edge-shapes.mmd').read_text()
for direction in ['TB','BT','LR','RL']:
    root, layout = run(shapes.replace('flowchart TB', f'flowchart {direction}'))
    assert len(layout['nodes']) == 14 and len(layout['edges']) == 14
    outlines = {g.attrib['id']: outline(g) for g in root.findall('s:g[@data-node-box]',NS)}
    for edge in layout['edges']:
        line = root.find(f"s:path[@data-ordinal='{edge['ordinal']}']",NS)
        points = edge['points']
        for side,node,index,neighbor in [('start',edge['source'],0,1),('end',edge['target'],-1,-2)]:
            p, q = points[index], points[neighbor]
            tip = p
            if f'marker-{side}' in line.attrib:
                dx,dy = p[0]-q[0], p[1]-q[1]
                length = math.hypot(dx,dy)
                marker_id = re.fullmatch(r'url\(#(.*)\)', line.attrib[f'marker-{side}']).group(1)
                marker = next(e for e in root.findall('s:defs/s:marker', NS) if e.attrib['id'] == marker_id)
                extent = float(marker.attrib['markerWidth'])
                tip = [p[0]+extent*dx/length,p[1]+extent*dy/length]
            distance = distance_to_outline(tip, outlines[node])
            assert distance < 0.025, (direction, node, side, tip, distance)
    print(f'PASS edges: all 14 shape boundaries in {direction}, marker offsets and body points')

# Explicit invisible rank constraint, plus a real negative check of entry point errors.
_, layout = run('flowchart LR\nA["A"] ~~~|hidden| B["B"]\n')
boxes = {n['id']:n['box'] for n in layout['nodes']}
assert boxes['A'][0] + boxes['A'][2] < boxes['B'][0]
assert layout['edges'][0]['ordinal'] == 0 and len(layout['edges'][0]['points']) >= 2
Path('/output/input.mmd').write_text('flowchart LR\nA["broken"\n')
result = subprocess.run(['python3','/app/renderer.py',*layout_args(),'/output/input.mmd','--output','/output/rejected'], capture_output=True, text=True)
assert result.returncode != 0
assert json.loads(result.stderr)['kind'] == 'syntax'
assert not Path('/output/rejected').exists(), 'stale success output after failed render'
print('PASS edges: invisible rank constraint and invalid-source nonzero exit')

# Plain Mermaid chains/groups create vertices with no explicit shape metadata.
_, layout = run('flowchart LR\nA --> B --> C\nC & D --> E & F\nF --> A\n')
assert [(e['source'],e['target']) for e in layout['edges']] == [
    ('A','B'),('B','C'),('C','E'),('C','F'),('D','E'),('D','F'),('F','A')]
assert [e['ordinal'] for e in layout['edges']] == list(range(7))
print('PASS edges: implicit nodes in plain chains, groups and cycles')

# All single-ended point/circle/cross variants on all visible line styles.
operators = ['-->', '--o', '--x', '==>', '==o', '==x', '-.->', '-.-o', '-.-x']
variant_source = 'flowchart LR\n' + '\n'.join(f'A{i} {op} B{i}' for i,op in enumerate(operators))
root, layout = run(variant_source)
assert len(layout['edges']) == 9
for i, edge in enumerate(layout['edges']):
    line = root.find(f"s:path[@data-ordinal='{i}']", NS)
    marker_id = re.fullmatch(r'url\(#(.*)\)',line.attrib['marker-end']).group(1)
    marker = next(e for e in root.findall('s:defs/s:marker', NS) if e.attrib['id'] == marker_id)
    assert marker.attrib['data-marker-type'] == ['point','circle','cross'][i%3]
    assert 'marker-start' not in line.attrib
    assert float(line.attrib['stroke-width']) == (3.5 if 3 <= i < 6 else 1.5)
    assert ('stroke-dasharray' in line.attrib) == (i >= 6)
print('PASS edges: all single-ended arrow variants for solid, thick, dotted')
