"""R6.3 responsibility classification using real API/CLI and isolated backend faults."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch
sys.path.insert(0, '/app')
import renderer
from renderer import render, DiagramSyntaxError, DiagramSourceError, RendererError
from runtime_version import BACKEND_FILES

ROOT = Path('/output/error-taxonomy')
ROOT.mkdir()
VALID = 'flowchart TB\nA["Tiếng Việt"] --> B\n'
rows = []


def expect(callback, name, kind, code):
    try:
        callback()
    except (DiagramSyntaxError, RendererError) as error:
        assert error.kind == kind, (name, type(error).__name__, str(error))
        assert error.category == ('engine' if kind == 'engine' else 'source'), (name, error.category)
        assert error.code == code, (name, error.code, code, str(error))
        if kind == 'source':
            assert isinstance(error, DiagramSourceError) and isinstance(error, RendererError)
        elif kind == 'engine':
            assert not isinstance(error, DiagramSourceError)
        else:
            assert isinstance(error, DiagramSyntaxError) and not isinstance(error, RendererError)
            assert error.line_number >= 1
        rows.append({'name': name, 'kind': kind, 'category': error.category, 'code': code, 'status': 'passed'})
        return error
    raise AssertionError('expected failure: ' + name)


cases = [
    ('flow-syntax', 'flowchart TB\nA["bad")\n', 'syntax', 'syntax'),
    ('yaml-syntax', '---\nconfig:\n  theme: [base\n---\nflowchart TB\nA\n', 'syntax', 'syntax'),
    ('unsupported-sequence', 'sequenceDiagram\nA->>B: hello\n', 'source', 'unsupported'),
    ('unknown-header', 'this is not Mermaid', 'source', 'unsupported'),
    ('empty-flowchart', 'flowchart TB\n', 'source', 'input'),
    ('unsafe-config', '---\nconfig:\n  securityLevel: loose\n---\nflowchart TB\nA\n', 'source', 'source_policy'),
    ('unknown-theme', '---\nconfig:\n  theme: not-a-theme\n---\nflowchart TB\nA\n', 'source', 'source_policy'),
    ('unsupported-style', 'flowchart TB\nA\nstyle A opacity:0.5\n', 'source', 'source_policy'),
    ('unsafe-style-grammar', 'flowchart TB\nA\nstyle A fill:url(file:///etc/passwd)\n', 'syntax', 'syntax'),
    ('unknown-font', '---\nconfig:\n  fontFamily: AIZ Missing Font\n---\nflowchart TB\nA\n', 'source', 'font'),
    # A source-controlled font name must not trick old dependency-message heuristics.
    ('font-name-looks-like-dependency', '---\nconfig:\n  fontFamily: Cannot find ModuleNotFoundError Font\n---\nflowchart TB\nA\n', 'source', 'font'),
    ('missing-glyph', 'flowchart TB\nA["\U0010ffff"]\n', 'source', 'glyph'),
    ('click-link', 'flowchart TB\nA\nclick A "https://example.invalid"\n', 'source', 'source_policy'),
    ('source-character-limit', 'x' * 50001, 'source', 'limit'),
    ('edge-count-limit', 'flowchart TB\n' + 'A --> B\n' * 501, 'source', 'limit'),
]
for name, source, kind, code in cases:
    expect(lambda source=source: render(source), name+'-api', kind, code)
    path=ROOT/(name+'.mmd');path.write_text(source)
    destination=ROOT/(name+'-output')
    result=subprocess.run([sys.executable, '/app/renderer.py', str(path), '--output', str(destination)], capture_output=True, text=True, timeout=35)
    assert result.returncode==1 and not destination.exists(), (name, result.stdout, result.stderr)
    detail=json.loads(result.stderr)
    assert detail['kind']==kind and detail['code']==code and detail['category']=='source', (name,detail)
    if kind=='syntax':assert type(detail['line']) is int and detail['line']>=1
    rows.append({'name': name+'-cli', 'kind': kind, 'category': detail['category'], 'code': code, 'status': 'passed'})

expect(lambda: render('a\0b'), 'nul-in-source', 'source', 'invalid_argument')
expect(lambda: render('\ud800'), 'invalid-source-unicode', 'source', 'invalid_argument')
expect(lambda: renderer._raster_dimensions({'width':1e308,'height':1}, 16), 'nonfinite-engine-layout', 'engine', 'limit')
expect(lambda: render('flowchart TB\nA["'+'W'*4096+'"]\n'), 'source-raster-limit', 'source', 'limit')
expect(lambda: render(VALID, scale=0), 'invalid-call-argument', 'engine', 'invalid_argument')
expect(lambda: render(None), 'invalid-call-source-type', 'engine', 'invalid_argument')
with patch.dict(os.environ, {'PATH': '/does-not-exist'}):
    expect(lambda: render(VALID), 'missing-node', 'engine', 'dependency')
with patch.object(renderer.tempfile, 'TemporaryDirectory', side_effect=PermissionError('synthetic scratch denial')):
    expect(lambda: render(VALID), 'scratch-permission', 'engine', 'output')


def backend_copy(name):
    directory=ROOT/name;directory.mkdir()
    for file in BACKEND_FILES:shutil.copyfile(Path('/app')/file,directory/file)
    (directory/'node_modules').symlink_to('/app/node_modules', target_is_directory=True)
    return directory


# A native helper returning malformed JSON is an engine bug, not Mermaid syntax.
broken=backend_copy('broken-shaper')
(broken/'text_geometry.py').write_text('print("invalid JSON")\n')
with patch.object(renderer, '_BACKEND', broken/'draw-probe.mjs'):
    expect(lambda: render(VALID), 'corrupt-shaper-json', 'engine', 'engine')

# Internal error location/message cannot impersonate a source grammar error.
broken=backend_copy('broken-backend')
p=broken/'draw-probe.mjs'
p.write_text(p.read_text().replace('  const inputPath = process.argv[3];', '  throw Object.assign(new Error("Synthetic font/style failure"), {hash:{line:0}});\n  const inputPath = process.argv[3];'))
with patch.object(renderer, '_BACKEND', p):
    expect(lambda: render(VALID), 'internal-error-with-location', 'engine', 'engine')

broken=backend_copy('timeout-backend')
(broken/'draw-probe.mjs').write_text('setTimeout(() => {}, 10000);\n')
with patch.object(renderer, '_BACKEND', broken/'draw-probe.mjs'):
    expect(lambda: render(VALID, timeout=0.2), 'backend-timeout', 'engine', 'timeout')

broken=backend_copy('invalid-diagnostic')
(broken/'draw-probe.mjs').write_text('console.error(JSON.stringify({kind:"source",code:"engine",line:0,message:"bad diagnostic"}));process.exit(1);\n')
with patch.object(renderer, '_BACKEND', broken/'draw-probe.mjs'):
    expect(lambda: render(VALID), 'malformed-source-diagnostic', 'engine', 'output')
(broken/'draw-probe.mjs').write_text('console.error(JSON.stringify({kind:"source",code:[],line:1,message:"bad code type"}));process.exit(1);\n')
with patch.object(renderer, '_BACKEND', broken/'draw-probe.mjs'):
    expect(lambda: render(VALID), 'malformed-source-code-type', 'engine', 'output')

# A missing required image font is an environment failure, even though asking
# for an arbitrary uninstalled font above was correctly a source failure.
import text_geometry
class EmptyContext:
    def list_families(self):return []
class EmptyLayout:
    def get_context(self):return EmptyContext()
with patch.object(text_geometry.PangoCairo, 'create_layout', return_value=EmptyLayout()):
    try:text_geometry.text_geometry({'text':'A'})
    except text_geometry.TextEngineError as error:
        assert error.code=='dependency'
        rows.append({'name':'missing-packaged-fonts', 'kind':'engine', 'category':'engine', 'code':'dependency', 'status':'passed'})
    else:raise AssertionError('missing packaged fonts accepted')

bad_utf8=ROOT/'invalid-utf8.mmd';bad_utf8.write_bytes(b'\xff')
result=subprocess.run([sys.executable, '/app/renderer.py', str(bad_utf8), '--output', str(ROOT/'invalid-utf8-output')],capture_output=True,text=True,timeout=35)
detail=json.loads(result.stderr)
assert result.returncode==1 and detail['kind']=='source' and detail['category']=='source' and detail['code']=='invalid_source',detail
assert not (ROOT/'invalid-utf8-output').exists()
rows.append({'name':'invalid-utf8-cli','kind':'source','category':'source','code':'invalid_source','status':'passed'})

# Engine-facing CLI failures retain engine category and publish no incomplete output.
valid=ROOT/'valid.mmd';valid.write_text(VALID)
existing=ROOT/'existing';existing.mkdir()
for name,args,code in [
    ('missing-input', [str(ROOT/'missing.mmd')], 'input'),
    ('output-exists', [str(valid),'--output',str(existing)], 'output_exists'),
    ('invalid-scale', [str(valid),'--scale','0'], 'invalid_argument'),
    ('cli-timeout', [str(valid),'--timeout','0.001','--output',str(ROOT/'timed-out')], 'timeout'),
]:
    result=subprocess.run([sys.executable,'/app/renderer.py',*args],capture_output=True,text=True,timeout=35)
    assert result.returncode==1, (name,result.stdout,result.stderr)
    detail=json.loads(result.stderr)
    assert detail['kind']=='engine' and detail['category']=='engine' and detail['code']==code, (name,detail)
    rows.append({'name':name+'-cli','kind':'engine','category':'engine','code':code,'status':'passed'})
assert not (ROOT/'timed-out').exists()
assert render(VALID).layout['nodes']
report={'status':'passed','cases':rows,'scope':'API/CLI source taxonomy and isolated engine fault injection on this image; company consumer integration unverified'}
(ROOT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('ERROR_TAXONOMY_REPORT '+json.dumps(report,ensure_ascii=False,sort_keys=True))
print('PASS contract: explicit syntax/source/engine classification, no dependency-message guessing for typed source errors')
