"""R1–R8 acceptance regressions on public artifacts and the real Python CLI.

Only flowchart is treated as implemented scope. Sequence/ER are rejection tests,
not decisions that they belong in v1. Private fixtures/tests are not substituted.
"""
from verify_geometry import *
import hashlib
import sys
sys.path.insert(0, '/app')
from renderer import RendererError, render, RENDERER_VERSION

ROOT = Path('/output/regression')
ROOT.mkdir()
report = {'status': 'running', 'renderer_version': RENDERER_VERSION, 'cases': [],
          'benchmark_25_35': {'status': 'unverified', 'measurements': None},
          'private_tests': 'unverified: not available', 'mentor_v1_scope': 'not decided here'}
REPORT = ROOT / 'report.json'


def record(name, **evidence):
    report['cases'].append({'name': name, 'status': 'passed', **evidence})
    REPORT.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')


def check_result(root, layout, nodes, edges, groups=0):
    assert len(layout['nodes']) == nodes and len(layout['edges']) == edges
    assert len(layout['subgraphs']) == groups
    assert [e['ordinal'] for e in layout['edges']] == list(range(edges))
    assert nodes > 0 and layout['width'] > 0 and layout['height'] > 0
    assert list(map(float, root.attrib['viewBox'].split())) == [0, 0, layout['width'], layout['height']]
    for edge in layout['edges']:
        line = root.find(f"s:path[@data-ordinal='{edge['ordinal']}']", NS)
        assert 'transform' not in line.attrib
        assert edge['points'] == json.loads(line.attrib['data-points'])
    # The current backend emits global primitive coordinates and translates
    # glyph paths. Fail rather than ignore a newly introduced parent transform.
    for group in root.findall('s:g', NS):
        assert 'transform' not in group.attrib, 'new group transform needs geometry QA support'
    check_geometry(root, layout)  # actual primitives, clipped endpoints and Cairo path extents
    entities = {item['id']: item for item in layout['nodes'] + layout['subgraphs']}
    for group in layout['subgraphs']:
        for id in group['members']:
            assert contained(entities[id]['box'], group['box'])
            assert not overlaps(group['label_box'], entities[id]['box'])
    assert root.attrib['data-renderer-version'] == RENDERER_VERSION
    # verify_common.run has already decoded PNG and compared it byte-for-byte
    # with a fresh rasterization of exactly the returned SVG.


def nested(levels):
    return 'flowchart TB\n' + ''.join(f'subgraph S{i} ["Tầng {i}"]\n' for i in range(levels)) + 'A --> B\n' + 'end\n' * levels


def main():
    source = (APP / 'tests/fixtures/dense-25-35.mmd').read_text()
    (ROOT / 'dense-25-35.mmd').write_text(source)
    snapshots = []
    measurements = []
    for attempt in range(3):
        destination = ROOT / f'dense-{attempt}'
        measured = ROOT / f'measurement-{attempt}.json'
        completed = subprocess.run([sys.executable, '/app/tests/measure_render.py', str(ROOT / 'dense-25-35.mmd'), str(destination), '--report', str(measured)], capture_output=True, text=True, timeout=40)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        metric = json.loads(measured.read_text())
        assert metric['wall_seconds'] > 0 and metric['sampled_process_tree_peak_rss_bytes'] > 0 and metric['memory_samples'] > 0
        measurements.append(metric)
        # Independently check the measured artifacts using the shared geometry
        # oracle and exact reraster; do not rerender before taking hashes.
        root = ET.parse(destination / 'diagram.svg').getroot()
        layout = json.loads((destination / 'layout.json').read_text())
        check_result(root, layout, 25, 35)
        png = cairo.ImageSurface.create_from_png(str(destination / 'diagram.png'))
        assert png.get_width() == math.ceil(layout['width'] * 2) and png.get_height() == math.ceil(layout['height'] * 2)
        assert any(png.get_data())
        for edge in layout['edges']:
            line = root.find(f"s:path[@data-ordinal='{edge['ordinal']}']", NS)
            assert edge['points'] == json.loads(line.attrib['data-points'])
        subprocess.run(['rsvg-convert', '--zoom=2', f'--output={ROOT}/dense-reraster.png', str(destination / 'diagram.svg')], check=True)
        assert (ROOT / 'dense-reraster.png').read_bytes() == (destination / 'diagram.png').read_bytes()
        snapshots.append({name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in ['diagram.svg', 'diagram.png', 'layout.json']})
    assert snapshots[0] == snapshots[1] == snapshots[2]
    report['benchmark_25_35'] = {'status': 'measured', 'nodes': 25, 'edges': 35, 'measurements': measurements,
                               'independent_process_digests': snapshots, 'threshold_status': 'mentor decision pending; no invented SLA'}
    record('dense-25-35-three-independent-processes', byte_identical=True)

    # Metadata insertion is post-render engine work, not a new renderer feature.
    # Confirm that inserting inert metadata does not prevent rasterizing the SVG.
    root = ET.parse(ROOT / 'dense-0/diagram.svg').getroot()
    metadata = ET.Element('{http://www.w3.org/2000/svg}metadata')
    metadata.text = source
    root.insert(0, metadata)
    ET.ElementTree(root).write(ROOT / 'with-metadata.svg', encoding='utf-8')
    subprocess.run(['rsvg-convert', '--zoom=2', f'--output={ROOT}/with-metadata.png', str(ROOT / 'with-metadata.svg')], check=True)
    assert (ROOT / 'with-metadata.png').read_bytes() == (ROOT / 'dense-0/diagram.png').read_bytes()
    record('svg-inert-metadata-insertion', raster_unchanged=True)

    base = 'flowchart TB\n' + '\n'.join(f'N{i}["Nút {i}"]' for i in range(40)) + '\n'
    base += '\n'.join(f'N{i} --> N{i + 1}' for i in range(39)) + '\nN39 --> N0\n'
    base += '\n'.join(f'N{i} --> N{i + 4}' for i in range(10)) + '\n'
    padding = '%% comment padding, never diagram code\n'
    source = base + padding * ((45000 - len(base)) // len(padding))
    assert 44000 < len(source) < 50000
    root, layout = run(source)
    check_result(root, layout, 40, 50)
    record('large-valid-source', characters=len(source), nodes=40, edges=50, includes_cycle=True)

    root, layout = run(nested(16))
    check_result(root, layout, 2, 1, 16)
    assert {g['id'] for g in layout['subgraphs']} == {f'S{i}' for i in range(16)}
    record('sixteen-nesting-levels', groups=16)

    text = '<br />'.join(['Nhãn dài Tiếng Việt ' * 10] * 8)
    root, layout = run('flowchart LR\nA["' + text + '"] --> A\n')
    check_result(root, layout, 1, 1)
    assert layout['edges'][0]['source'] == layout['edges'][0]['target'] == 'A'
    record('long-multiline-label-self-cycle', label_characters=len(text))

    for name, source in [('source-over-limit', 'x' * 50001),
                         ('edge-count-over-limit', 'flowchart LR\n' + 'A --> B\n' * 501),
                         ('very-deep-output-limit', nested(256)),
                         ('long-single-line-raster-limit', 'flowchart TB\nA["' + 'W' * 4096 + '"]\n')]:
        try:
            render(source)
        except RendererError as error:
            assert error.code == 'limit', (name, error.code, str(error))
            assert str(error)
        else:
            raise AssertionError('expected explicit size limit: ' + name)
        record(name, expected_error_code='limit')

    # Valid non-flowchart sources remain explicitly unsupported until the mentor
    # decides v1. No blank SVG or partial directory is acceptable.
    for index, source in enumerate(['sequenceDiagram\nAlice->>Bob: hello\n',
                                    'erDiagram\nA ||--o{ B : contains\n',
                                    'pie\n"A" : 1\n']):
        input_path = ROOT / f'unsupported-{index}.mmd'
        input_path.write_text(source)
        destination = ROOT / f'unsupported-{index}'
        failed = subprocess.run([sys.executable, '/app/renderer.py', str(input_path), '--output', str(destination)], capture_output=True, text=True, timeout=35)
        assert failed.returncode != 0 and not destination.exists()
        detail = json.loads(failed.stderr)
        assert detail['kind'] == 'source' and detail['category']=='source' and detail['code'] == 'unsupported', detail
        record('unsupported-type-no-empty-svg-' + str(index), source_header=source.splitlines()[0])

    # These are the exact error categories requested by R6.4; if Mermaid accepts
    # a case, leave this test failing and record the gap, not an invented PASS.
    for name, bad in [('reserved-end-id', 'flowchart TB\nend --> A\n'),
                      ('reserved-end-class', 'flowchart TB\nA\nclassDef end fill:red\n'),
                      ('unquoted-parenthesis', 'flowchart TB\nA[bad (label)]\n'),
                      ('mismatched-delimiter', 'flowchart TB\nA["bad")\n')]:
        path = ROOT / 'invalid.mmd'
        path.write_text(bad)
        out = ROOT / ('invalid-' + name)
        failed = subprocess.run([sys.executable, '/app/renderer.py', str(path), '--output', str(out)], capture_output=True, text=True, timeout=35)
        assert failed.returncode != 0 and not out.exists(), (name, failed.stdout)
        detail = json.loads(failed.stderr)
        assert detail['kind'] == 'syntax' and type(detail['line']) is int and 1 <= detail['line'] <= len(bad.splitlines()) + 1, detail
        record(name, error_line=detail['line'])

    report['status'] = 'passed'
    REPORT.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print('REGRESSION_REPORT ' + json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        report['status'] = 'failed'
        report['failure'] = {'type': type(sys.exc_info()[1]).__name__, 'message': str(sys.exc_info()[1])[:1000]}
        print('REGRESSION_REPORT ' + json.dumps(report, sort_keys=True), flush=True)
        REPORT.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
        raise
