"""Packaged runtime verification; never treat unexecuted coverage as passed."""
from verify_common import *
import hashlib
import sys
import resource
sys.path.insert(0,'/app')
from runtime_version import RENDERER_VERSION,renderer_version
from renderer import _svg,RendererError

ROOT=Path('/output/runtime');ROOT.mkdir()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest=json.loads(Path('/app/runtime-manifest.json').read_text())
build_identity=json.loads(Path('/app/build-identity.json').read_text())
assert build_identity=={'schema':1,'dockerfile_sha256':sha(Path('/app/Dockerfile')),
    'build_policy_sha256':sha(Path('/app/runtime/build-policy.json')),
    'inventory_builder_sha256':sha(Path('/app/runtime/build_inventory.py'))}

assert RENDERER_VERSION==renderer_version() and RENDERER_VERSION.startswith('aiz-mermaid-v1-sha256:')
lock=json.loads(Path('/app/package-lock.json').read_text())
for key,value in lock['packages'].items():
    if key:
        assert value['integrity'].startswith('sha512-')
        assert value['resolved'].startswith('https://registry.npmjs.org/')
assert not any(key == 'node_modules/jsdom' or key.endswith('/node_modules/jsdom') for key in lock['packages'])
subprocess.run(['node', '/app/tests/verify_no_dom.mjs'], check=True, timeout=15)
# Recheck contents rather than trusting build inventory as a self-assertion.
for root,key in [(Path('/app/node_modules'),'npm_files'),(Path('/usr/share/fonts'),'fonts'),(Path('/etc/fonts'),'fontconfig')]:
    actual={str(p.relative_to(root)):({'symlink':os.readlink(p),'sha256':sha(p)} if p.is_symlink() else sha(p)) for p in sorted(root.rglob('*')) if p.is_file()}
    assert actual==manifest[key],key+' checksum drift'
assert manifest['fonts'] and all('chromium' not in p['name'] and 'firefox' not in p['name'] for p in manifest['dpkg'])
for program in ['chromium','chromium-browser','google-chrome','firefox','puppeteer','playwright']:
    assert shutil.which(program) is None,program
assert not any(any(n in key.lower() for n in ['puppeteer','playwright','chromium']) for key in lock['packages'])
print('PASS runtime: pinned npm integrity, actual npm/font/fontconfig checksums; no browser dependency')

# Probe the additional policy itself, independently of successful rendering.
probe=subprocess.run([sys.executable,'/app/tests/runtime_guard.py','--probe'],capture_output=True,text=True,timeout=10)
assert resource.getrlimit(resource.RLIMIT_CPU)==(300,300)
assert resource.getrlimit(resource.RLIMIT_NOFILE)==(256,256)
assert resource.getrlimit(resource.RLIMIT_FSIZE)==(268435456,268435456)
assert Path('/sys/fs/cgroup/memory.max').read_text().strip()==str(2*1024**3)
restricted=probe.returncode==0
if probe.returncode==3:
    policy={'status':'unverified','reason':json.loads(probe.stderr)['message']}
    print('UNVERIFIED additional syscall policy: '+policy['reason'],file=sys.stderr)
else:
    assert probe.returncode==0,probe.stderr
    policy=json.loads(probe.stdout)
    assert policy['status']=='passed'
    print('PASS runtime: enforced seccomp AF_UNIX/ptrace/mount/namespace restrictions and resource probes')
def renderer_command(input_path,out):
    prefix=[sys.executable,'/app/tests/runtime_guard.py'] if restricted else [sys.executable]
    return [*prefix,'/app/renderer.py',*layout_args(),str(input_path),'--output',str(out)]

sources=[
    (APP/'tests/fixtures/theme-labels.mmd').read_text(),
    (APP/'tests/fixtures/subgraphs.mmd').read_text(),
    'flowchart LR\narrow --> aiz-marker-point --> aiz-marker-point-1 --> aiz-marker-point-2\naiz-marker-point-2 o--o arrow\n',
]
digests=[]
for fixture,source in enumerate(sources):
    input_path=ROOT/f'input-{fixture}.mmd';input_path.write_text(source)
    repeats=[];id_lists=[]
    for attempt in range(3):
        out=ROOT/f'render-{fixture}-{attempt}'
        command=renderer_command(input_path,out)
        completed=subprocess.run(command,capture_output=True,text=True,timeout=35)
        if completed.returncode==3:
            print('UNVERIFIED restricted renderer: '+completed.stderr,file=sys.stderr);raise SystemExit(3)
        assert completed.returncode==0,completed.stderr
        svg=(out/'diagram.svg').read_text();layout=json.loads((out/'layout.json').read_text())
        parsed=ET.fromstring(svg)
        assert parsed.attrib['data-renderer-version']==RENDERER_VERSION
        _svg(svg.encode(),layout)
        ids=[e.attrib['id'] for e in parsed.iter() if 'id' in e.attrib]
        assert len(ids)==len(set(ids))
        id_lists.append(ids)
        for text in [svg,(out/'layout.json').read_text()]:
            assert '/tmp/aiz-render-' not in text and '.aiz-publish-' not in text
        subprocess.run(['rsvg-convert','--zoom=2',f'--output={ROOT}/reraster.png',str(out/'diagram.svg')],check=True)
        assert (ROOT/'reraster.png').read_bytes()==(out/'diagram.png').read_bytes()
        repeats.append({name:sha(out/name) for name in ['diagram.svg','diagram.png','layout.json']})
    assert repeats[0]==repeats[1]==repeats[2] and id_lists[0]==id_lists[1]==id_lists[2]
    digests.append(repeats[0])
print('PASS runtime: 3 fixtures × 3 independent Python/Node/Pango/raster processes, byte-identical SVG/PNG/layout and IDs')

# Source attacks: all go through the public CLI under the extra policy. Negative
# tests need rejection, not network failure. There must be no published outputs.
attacks=[
 'flowchart TB\nA\nclick A "https://example.invalid/"\n',
 'flowchart TB\nA\nclick A call malicious()\n',
 'flowchart TB\nA["<script>require(\'fs\').writeFileSync(\'/output/SOURCE-EXECUTED\',1)</script>"]\n',
 'flowchart TB\nA["x<br onerror=\'alert(1)\'>y"]\n',
 '---\nconfig: !!js/function \'function () { return 1; }\'\n---\nflowchart TB\nA\n',
 'flowchart TB\nA@{img: "file:///etc/passwd"}\n',
 '---\nconfig:\n  fontFamily: "file:///etc/passwd"\n---\nflowchart TB\nA\n',
 '---\nconfig:\n  themeCSS: "@import url(https://example.invalid/a.css)"\n---\nflowchart TB\nA\n',
 'flowchart TB\nA\nstyle A fill:url(file:///etc/passwd)\n',
 'flowchart TB\nA["<img src=\'https://example.invalid/x\'>"]\n',
]
for index,source in enumerate(attacks):
    path=ROOT/'attack.mmd';path.write_text(source)
    destination=ROOT/f'attack-output-{index}'
    failed=subprocess.run(renderer_command(path,destination),capture_output=True,text=True,timeout=35)
    assert failed.returncode!=0 and not destination.exists(),(index,failed.stdout,failed.stderr)
    detail=json.loads(failed.stderr)
    assert detail['kind'] in ['syntax','source'] and detail['category']=='source'
# Verify output validator rejects active/unexpected SVG even if a dependency
# returns it with success. This is additional to the source-side allowlists.
layout={'width':10,'height':10}
for content in ['<script/>','<foreignObject/>','<image href="file:///etc/passwd"/>','<rect onclick="x()"/>','<path fill="url(https://example.invalid/x)"/>','<path stroke-linecap="url(file:///etc/passwd)"/>','<path stroke-linecap="invalid"/>','<g id="dup"/><g id="dup"/>']:
    bad=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">{content}</svg>'
    try:_svg(bad.encode(),layout)
    except RendererError:pass
    else:raise AssertionError('unsafe SVG accepted: '+content)
assert not Path('/output/SOURCE-EXECUTED').exists()
print('PASS runtime: unsafe source rejected; active SVG, external references and duplicate IDs rejected')

# Environment injection cannot change child behavior or escape via preloads.
trap=ROOT/'trap.cjs';trap.write_text('require("fs").writeFileSync("/output/PRELOAD-EXECUTED","bad")')
input_path=ROOT/'env.mmd';input_path.write_text(sources[0]);out=ROOT/'env-output'
env=os.environ.copy();env.update({'NODE_OPTIONS':f'--require={trap}','FONTCONFIG_FILE':'/output/does-not-exist','PYTHONPATH':'/output/does-not-exist','TZ':'Asia/Ho_Chi_Minh','LC_ALL':'C'})
completed=subprocess.run([sys.executable,'/app/renderer.py',*layout_args(),str(input_path),'--output',str(out)],env=env,capture_output=True,text=True,timeout=35)
assert completed.returncode==0,completed.stderr
assert not Path('/output/PRELOAD-EXECUTED').exists()
assert {name:sha(out/name) for name in ['diagram.svg','diagram.png','layout.json']}==digests[0]
# A changed backend cannot keep the same identity.
copy=ROOT/'changed-backend';copy.mkdir()
for name in ['draw-probe.mjs','text_geometry.py','subgraph-layout.mjs','elk-layout.mjs','theme-source.mjs','mermaid-model.mjs']:shutil.copyfile(Path('/app')/name,copy/name)
(copy/'draw-probe.mjs').write_text((copy/'draw-probe.mjs').read_text()+'\n// identity probe\n')
assert renderer_version(copy)!=RENDERER_VERSION
print('PASS runtime: ambient environment/preload sanitized; backend changes alter RENDERER_VERSION')
report={'platform':manifest['platform'],'layout_engine':TEST_LAYOUT,'renderer_version':RENDERER_VERSION,'digests':digests,'tested_policy':policy,
        'status':'passed' if restricted else 'unverified','resource_configuration':{'ram_bytes':2*1024**3,'cpu_rlimit_seconds':300,'nofile':256,'fsize_bytes':268435456},'unverified':[*(['additional AF_UNIX/ptrace/mount/namespace seccomp filter'] if not restricted else []),'private office_sandbox.py/Landlock path policy','300 CPU-second exhaustion','2 GiB exhaustion','native execution when platform uses emulation']}
(ROOT/'runtime-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
print('RUNTIME_REPORT '+json.dumps(report,sort_keys=True))

if not restricted:raise SystemExit(3)
