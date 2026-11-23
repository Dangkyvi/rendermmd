"""Integration checks for the public Python API and CLI, inside offline Docker."""
from verify_common import *
import sys
sys.path.insert(0, '/app')
from renderer import render, Rendered, DiagramSyntaxError, RendererError
import renderer
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import tempfile
import time

SOURCE='flowchart LR\nA["Tiếp nhận"] -->|hợp lệ| B["Hoàn tất"]\n'
ROOT=Path('/output/contract');ROOT.mkdir()


def expect_error(callback, code=None, contains=None):
    try:
        callback()
    except RendererError as error:
        if code is not None: assert error.code==code,(error.code,str(error))
        if contains: assert contains.lower() in str(error).lower(),str(error)
        return error
    raise AssertionError('expected RendererError')


def cli(input_path, output=None, *args):
    command=[sys.executable,'/app/renderer.py',str(input_path),*args]
    if output is not None:command+=['--output',str(output)]
    return subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=35)


def artifact_set(directory):
    assert {p.name for p in directory.iterdir()}=={'diagram.svg','diagram.png','layout.json'}
    return ((directory/'diagram.svg').read_text(),(directory/'diagram.png').read_bytes(),json.loads((directory/'layout.json').read_text()))


# API contract, independent reraster and immutable return values across retries.
result=render(SOURCE)
assert isinstance(result,Rendered) and isinstance(result.svg,str) and isinstance(result.png,bytes) and isinstance(result.layout,dict)
assert [n['id'] for n in result.layout['nodes']]==['A','B']
assert [(e['source'],e['target'],e['ordinal']) for e in result.layout['edges']]==[('A','B',0)]
assert render(SOURCE)==result
Path('/output/api.svg').write_text(result.svg)
subprocess.run(['rsvg-convert','--zoom=2','--output=/output/check-api.png','/output/api.svg'],check=True)
assert Path('/output/check-api.png').read_bytes()==result.png
print('PASS contract: Rendered API, SVG/PNG/layout correspondence, retry')

# True source-line mapping: front matter, removed comments, blank lines,
# multiline labels and CRLF. YAML parse errors are also source errors.
cases=[
 ('flowchart TB\n A --> B\n B --> C\n D["x")\n',4),
 ('---\ntitle: "Test"\nconfig:\n  theme: base\n---\nflowchart TB\n A --> B\n %% middle comment\n B --> C\n D["x")\n',10),
 ('%% leading\n\nflowchart TB\n A["one\ntwo"]\n\n %% middle\n A --> B\n D["x")\n',9),
 ('---\nconfig:\n  theme: [base\n---\nflowchart TB\nA\n',4),
]
for bad,line in cases:
    for source in [bad,bad.replace('\n','\r\n')]:
        try:render(source)
        except DiagramSyntaxError as error:
            assert error.line_number==line,(error.line_number,line,str(error))
            assert f'dòng {line}:' in str(error)
            if 'Parse error on line' in str(error): assert f'Parse error on line {line}:' in str(error)
            assert not isinstance(error,RendererError)
        else:raise AssertionError('invalid source accepted')
try:render(' \n')
except DiagramSyntaxError as error:assert error.line_number==1
else:raise AssertionError('empty source accepted')
expect_error(lambda:render('sequenceDiagram\nA->>B: hello\n'),'unsupported','chưa được hỗ trợ')
expect_error(lambda:render('this is not Mermaid'),'unsupported')
expect_error(lambda:render('flowchart TB\n'),'input','không có node')
assert render(SOURCE)==result
print('PASS contract: distinct syntax/engine errors and exact 1-based source lines (YAML/comments/multiline/CRLF)')

# Validation is before dependency execution; types, nonfinite values and limits.
for key,values in {'scale':[0,-1,True,'2',None,float('nan'),float('inf'),17,10**1000],
                   'timeout':[0,-1,True,'30',None,float('nan'),float('inf'),301,10**1000]}.items():
    for value in values:expect_error(lambda key=key,value=value:render(SOURCE,**{key:value}),'invalid_argument')
for bad in [None,b'flowchart TB',123,'\ud800','a\0b']:
    expect_error(lambda:render(bad),'invalid_argument')
expect_error(lambda:render('x'*(renderer.MAX_SOURCE_CHARS+1)),'limit','ký tự')
expect_error(lambda:render('flowchart LR\n'+'A --> B\n'*501),'limit','edge')
with patch.object(renderer,'MAX_SVG_BYTES',16):expect_error(lambda:render(SOURCE),'limit')
with patch.object(renderer,'MAX_LAYOUT_BYTES',16):expect_error(lambda:render(SOURCE),'limit')
with patch.object(renderer,'MAX_PNG_BYTES',16):expect_error(lambda:render(SOURCE),'limit')
with patch.object(renderer,'MAX_TOTAL_BYTES',16):expect_error(lambda:render(SOURCE),'limit')
with patch.object(renderer,'MAX_RASTER_PIXELS',4):expect_error(lambda:render(SOURCE),'limit','raster')
with patch.object(renderer,'MAX_RASTER_DIMENSION',4):expect_error(lambda:render(SOURCE),'limit','raster')
print('PASS contract: source/argument/output bytes, total size and raster dimension/pixel limits')

# The larger diagram budget is still bounded, independently of per-axis limits.
assert renderer._raster_dimensions({'width':6423,'height':14956},1)==(6423,14956)
assert renderer._raster_dimensions({'width':10000,'height':10000},1)==(10000,10000)
expect_error(lambda:renderer._raster_dimensions({'width':10000,'height':10001},1),'limit','raster')
expect_error(lambda:renderer._raster_dimensions({'width':16385,'height':1},1),'limit','raster')
print('PASS contract: 96MP requested raster and 100MP boundary accepted; above 100MP or 16384 per axis rejected')


# Public CLI supports options, positional scale/timeout, and legacy Node adapter.
input_path=ROOT/'input.mmd';input_path.write_text(SOURCE)
first=ROOT/'first'
completed=cli(input_path,first,'--scale','1.5','--timeout','30')
assert completed.returncode==0,completed.stderr
assert json.loads(completed.stdout)['output']==str(first)
svg,png,layout=artifact_set(first)
scaled=render(SOURCE,scale=1.5)
assert (svg,png,layout)==(scaled.svg,scaled.png,scaled.layout)
image=cairo.ImageSurface.create_from_png(str(first/'diagram.png'))
assert image.get_width()==math.ceil(layout['width']*1.5)
assert image.get_height()==math.ceil(layout['height']*1.5)
assert cli(input_path,ROOT/'positional','0.5','30').returncode==0
legacy=subprocess.run(['node','/app/draw-probe.mjs',str(input_path),'1','30','--output',str(ROOT/'legacy')],capture_output=True,text=True,timeout=35)
assert legacy.returncode==0,legacy.stderr
artifact_set(ROOT/'legacy')
auto=cli(input_path)
assert auto.returncode==0,auto.stderr
auto_path=Path(json.loads(auto.stdout)['output'])
assert auto_path.parent==ROOT and auto_path.name.startswith('input-render-')
artifact_set(auto_path)
old=artifact_set(first)
failed=cli(input_path,first)
assert failed.returncode!=0 and json.loads(failed.stderr)['code']=='output_exists'
assert artifact_set(first)==old
bad_path=ROOT/'bad.mmd';bad_path.write_text(cases[1][0])
failed_target=ROOT/'retry'
failed=cli(bad_path,failed_target)
assert failed.returncode!=0
error=json.loads(failed.stderr)
assert error['kind']=='syntax' and error['line']==10
assert not failed_target.exists() and artifact_set(first)==old
assert cli(input_path,failed_target).returncode==0
assert artifact_set(failed_target)[1]==result.png
missing=cli(ROOT/'missing.mmd',ROOT/'no-input')
assert missing.returncode!=0 and json.loads(missing.stderr)['code']=='input'
invalid_cli=cli(input_path,ROOT/'invalid','--scale','nan')
assert invalid_cli.returncode!=0 and json.loads(invalid_cli.stderr)['code']=='invalid_argument'
large_input=ROOT/'large.mmd';large_input.write_bytes(b'x'*(renderer.MAX_SOURCE_BYTES+1))
assert json.loads(cli(large_input,ROOT/'large').stderr)['code']=='limit'
fifo=ROOT/'input-fifo';os.mkfifo(fifo)
assert json.loads(cli(fifo,ROOT/'fifo').stderr)['code']=='input'
print('PASS contract: CLI/legacy adapter, scale, unique default output, immutable publication, failed retry and clear CLI errors')

# Concurrency in one Python process and in separate CLI processes. Outputs from
# a completed call remain valid while another fails or publishes another set.
with ThreadPoolExecutor(max_workers=2) as pool:
    f1=pool.submit(render,SOURCE)
    f2=pool.submit(render,'flowchart TB\nX --> Y --> Z\n',scale=1)
    r1,r2=f1.result(),f2.result()
assert r1==result and [n['id'] for n in r2.layout['nodes']]==['X','Y','Z']
second_input=ROOT/'second.mmd';second_input.write_text('flowchart TB\nX --> Y --> Z\n')
with ThreadPoolExecutor(max_workers=2) as pool:
    f1=pool.submit(cli,input_path,ROOT/'parallel-1')
    f2=pool.submit(cli,second_input,ROOT/'parallel-2')
    assert f1.result().returncode==0 and f2.result().returncode==0
assert artifact_set(ROOT/'parallel-1')[1]==result.png
assert [n['id'] for n in artifact_set(ROOT/'parallel-2')[2]['nodes']]==['X','Y','Z']
# Two publishers to the same destination cannot combine or replace each other.
with ThreadPoolExecutor(max_workers=2) as pool:
    shared=ROOT/'same-destination'
    f1=pool.submit(cli,input_path,shared)
    f2=pool.submit(cli,second_input,shared)
    done=[f1.result(),f2.result()]
assert sorted(p.returncode for p in done)==[0,1]
whole=artifact_set(shared)
second_result=render(second_input.read_text())
assert whole in [(result.svg,result.png,result.layout),(second_result.svg,second_result.png,second_result.layout)]
assert artifact_set(first)==old
assert not list(ROOT.glob('.aiz-publish-*'))
print('PASS contract: concurrent API calls, separate CLI outputs and racing atomic publishers')

# Missing dependencies are real failures, without changing the image or relaxing
# the sandbox. Only private test copies and PATH shims are used for fault injection.
with patch.dict(os.environ,{'PATH':'/does-not-exist'}):
    expect_error(lambda:render(SOURCE),'dependency','node')
node_bin=ROOT/'node-only';node_bin.mkdir()
(node_bin/'node').symlink_to(shutil.which('node'))
with patch.dict(os.environ,{'PATH':str(node_bin)}):
    expect_error(lambda:render(SOURCE),'dependency','rsvg-convert')


def backend_copy(name, node_modules=True):
    directory=ROOT/name;directory.mkdir()
    for file in ['draw-probe.mjs','text_geometry.py','subgraph-layout.mjs','elk-layout.mjs','theme-source.mjs','mermaid-model.mjs']:
        shutil.copyfile(Path('/app')/file,directory/file)
    if node_modules:(directory/'node_modules').symlink_to('/app/node_modules',target_is_directory=True)
    return directory


no_npm=backend_copy('without-npm',node_modules=False)
with patch.object(renderer,'_BACKEND',no_npm/'draw-probe.mjs'):
    expect_error(lambda:render(SOURCE),'dependency','mermaid')
no_helper=backend_copy('without-helper');(no_helper/'text_geometry.py').unlink()
with patch.object(renderer,'_BACKEND',no_helper/'draw-probe.mjs'):
    expect_error(lambda:render(SOURCE),'dependency','text_geometry.py')
no_pango=backend_copy('without-pango')
(no_pango/'text_geometry.py').write_text('import aiz_missing_pango_dependency\n')
with patch.object(renderer,'_BACKEND',no_pango/'draw-probe.mjs'):
    expect_error(lambda:render(SOURCE),'dependency','aiz_missing_pango_dependency')
assert render(SOURCE)==result
print('PASS contract: missing Node/rsvg/npm/helper/Pango dependency diagnostics and successful retry')

# A stalled actual Pango stage creates a grandchild. The API must kill Node,
# Pango and the grandchild in the same group, then remove only its own scratch.
def assert_stopped(pids):
    for pid in pids:
        status=Path(f'/proc/{pid}/stat')
        assert not status.exists(),f'descendant remains: {pid}'


stalled=backend_copy('stalled-pango')
pid_file=ROOT/'pango-pids.json'
(stalled/'text_geometry.py').write_text(f'''import os,sys,time,json,subprocess
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
open({str(pid_file)!r},'w').write(json.dumps([os.getppid(),os.getpid(),child.pid]))
time.sleep(60)
''')
private_tmp=ROOT/'private-tmp';private_tmp.mkdir()
# Use a private test-owned temp root, so cleanup can be asserted without touching
# scratch from any other render (including unrelated processes).
with patch.object(renderer,'_BACKEND',stalled/'draw-probe.mjs'),patch.object(tempfile,'tempdir',str(private_tmp)):
    started=time.monotonic()
    expect_error(lambda:render(SOURCE,timeout=2),'timeout')
    elapsed=time.monotonic()-started
assert elapsed<3.5,elapsed
assert pid_file.exists(),'timeout must reach real Pango stage, not merely Node startup'
assert_stopped(json.loads(pid_file.read_text()))
assert not list(private_tmp.iterdir())
assert artifact_set(first)==old
print('PASS contract: global timeout kills Node/Pango/grandchild and removes private scratch')

# Prove the deadline is shared across stages. Both synthetic delays are less
# than the total timeout, but their combined time plus actual Node/Pango exceeds
# it. A fresh per-stage timeout would incorrectly succeed or run much longer.
delayed=backend_copy('delayed-pango')
helper=delayed/'text_geometry.py'
helper.write_text('import time\ntime.sleep(1.2)\n'+helper.read_text())
raster_script=ROOT/'slow-raster.py'
raster_pid_file=ROOT/'raster-pids.json'
raster_script.write_text(f'''
import os,sys,time,json,subprocess
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
open({str(raster_pid_file)!r},'w').write(json.dumps([os.getpid(),child.pid]))
time.sleep(2.5)
os.execv({shutil.which('rsvg-convert')!r},[{shutil.which('rsvg-convert')!r},*sys.argv[1:]])
''')
# Scratch is noexec; keep that protection. Read the test worker through the
# existing interpreter, then use the real supervisor and real rsvg binary.
original_run=renderer._run
def raster_worker(script):
    def run(command,scratch,stage,deadline,watched=()):
        if stage=='rsvg-convert':command=[sys.executable,str(script),*command[1:]]
        return original_run(command,scratch,stage,deadline,watched)
    return run

with patch.object(renderer,'_BACKEND',delayed/'draw-probe.mjs'),patch.object(renderer,'_run',side_effect=raster_worker(raster_script)),patch.object(tempfile,'tempdir',str(private_tmp)):
    started=time.monotonic()
    expect_error(lambda:render(SOURCE,timeout=3.5),'timeout')
    elapsed=time.monotonic()-started
assert 3.4<=elapsed<4.8,elapsed
assert raster_pid_file.exists(),'test must enter rasterization after Node/Pango'
assert_stopped(json.loads(raster_pid_file.read_text()))
assert not list(private_tmp.iterdir())
# CLI timeout does not publish an incomplete set and preserves prior artifacts.
failed=cli(input_path,ROOT/'timed-out','--timeout','0.001')
assert failed.returncode!=0 and json.loads(failed.stderr)['code']=='timeout'
assert not (ROOT/'timed-out').exists()
assert artifact_set(first)==old
assert render(SOURCE)==result
print('PASS contract: one deadline across Node/Pango and raster; no partial CLI publication; retry succeeds')

# A raster dependency returning success with corrupt bytes cannot publish a
# Rendered value. This exercises real artifact validation, not a mocked validator.
bad_raster=ROOT/'bad-raster.py'
bad_raster.write_text(f'''
import sys
path=next(arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--output='))
open(path,'wb').write(b'not a PNG')
''')
with patch.object(renderer,'_run',side_effect=raster_worker(bad_raster)):
    expect_error(lambda:render(SOURCE),'output','PNG')
assert not list(private_tmp.iterdir())
print('PASS contract: corrupt dependency output rejected; complete public results only')

# R6.3: concrete source failures vs dependency/internal faults, through API and CLI.
subprocess.run([sys.executable, '/app/tests/verify_error_taxonomy.py'], check=True, timeout=120)


# Output validation checks actual M/L/Q geometry, not merely data-* copies.
result=render(SOURCE)
for mutation in ['coordinate','command','ordinal','metadata']:
    svg=ET.fromstring(result.svg)
    line=svg.find("s:path[@data-ordinal='0']",NS)
    if mutation=='coordinate':
        tokens=line.attrib['d'].split();tokens[1]=str(float(tokens[1])+1);line.set('d',' '.join(tokens))
    elif mutation=='command':line.set('d',line.attrib['d']+' Z')
    elif mutation=='ordinal':line.set('data-ordinal','99')
    else:line.set('data-points','[]')
    expect_error(lambda: renderer._svg(ET.tostring(svg),result.layout),'output')
print('PASS contract: strict edge path/layout coordinates, commands, ordinal and metadata')
