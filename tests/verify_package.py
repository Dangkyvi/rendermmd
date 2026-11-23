"""Pure renderer and detached source-bundle tests. No editor/repo runtime input."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,'/app')
from renderer import render, RENDERER_VERSION

DELIVERY=Path('/delivery/renderer')
required={'__init__.py','renderer.py','runtime_version.py','package.json','package-lock.json','README.md','backend'}
assert required <= {p.name for p in DELIVERY.iterdir()}
assert not any((DELIVERY/name).exists() for name in ['Dockerfile','runtime','.dockerignore'])
for name in ['diagram_edit.py','edit-model.mjs','edit_artifact.py']:
    assert not (DELIVERY/name).exists() and not (Path('/app')/name).exists(),name
assert importlib.util.find_spec('diagram_edit') is None
assert {p.name for p in (DELIVERY/'backend').iterdir() if p.is_file()}=={'draw-probe.mjs','subgraph-layout.mjs','elk-layout.mjs','theme-source.mjs','mermaid-model.mjs','text_geometry.py'}
print('PASS pure renderer: no editing component in delivery folder or renderer image',flush=True)

# Only the copied folder exists in this simulated company source root.
root=Path('/tmp/company-src');root.mkdir()
package=root/'renderer'
shutil.copytree(DELIVERY,package,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store','node_modules'))
# Runtime preparation is explicit. Dependencies are supplied by the pinned image,
# exactly as documented, rather than copied from the development checkout.
(root/'node_modules').symlink_to('/app/node_modules',target_is_directory=True)
runtime=Path('/tmp/company-runtime');runtime.mkdir()
for name in ['runtime-manifest.json','build-identity.json']:
    shutil.copyfile(Path('/app')/name,runtime/name)
assert not (package/'runtime-manifest.json').exists() and not (package/'Dockerfile').exists()
source='flowchart TB\nA["Tiếng Việt"] -->|Có| B["Hoàn tất"]\n'
expected=render(source,scale=1)
source_file=root/'input.mmd';source_file.write_text(source)
expected_hashes={k:hashlib.sha256(v).hexdigest() for k,v in [('svg',expected.svg.encode()),('png',expected.png)]}
env={k:v for k,v in os.environ.items() if k in ['PATH','LANG','LC_ALL','TZ']}
env['PYTHONDONTWRITEBYTECODE']='1'
env['AIZ_RENDERER_RUNTIME_DIR']=str(runtime)
code='''import hashlib,json
from renderer import render, RENDERER_VERSION
source=open('input.mmd').read()
r=render(source,scale=1)
print(json.dumps({'version':RENDERER_VERSION,'svg':hashlib.sha256(r.svg.encode()).hexdigest(),'png':hashlib.sha256(r.png).hexdigest(),'layout':r.layout}))
'''
p=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,timeout=40)
assert p.returncode==0,p.stderr
result=json.loads(p.stdout)
assert result['version']==RENDERER_VERSION
assert {k:result[k] for k in ['svg','png']}==expected_hashes
assert result['layout']==expected.layout
print('PASS detached Python package API: only renderer folder plus prepared runtime, byte-identical output',flush=True)
missing=Path('/tmp/missing-runtime');missing.mkdir()
probe='from renderer import render; render("flowchart TB\\nA --> B\\n",scale=1)'
bad_env=dict(env,AIZ_RENDERER_RUNTIME_DIR=str(missing))
p=subprocess.run([sys.executable,'-c',probe],cwd=root,env=bad_env,capture_output=True,text=True,timeout=15)
assert p.returncode!=0 and ('manifest' in p.stderr or 'fingerprint' in p.stderr),p.stderr
print('PASS external runtime fingerprints required; no unchecked fallback',flush=True)


for kind,cmd in [
    ('python',[sys.executable,str(package/'renderer.py')]),
    ('node',['node',str(package/'backend/draw-probe.mjs')]),
]:
    dest=Path('/output')/('package-'+kind)
    p=subprocess.run([*cmd,str(source_file),'--scale','1','--output',str(dest)],cwd=root,env=env,capture_output=True,text=True,timeout=40)
    assert p.returncode==0,p.stderr
    assert (dest/'diagram.svg').read_text()==expected.svg
    assert (dest/'diagram.png').read_bytes()==expected.png
    assert json.loads((dest/'layout.json').read_text())==expected.layout
    print('PASS detached '+kind+' CLI: no scripts/tests/editing folder required',flush=True)
assert not list(package.rglob('*.sqlite')) and not list(package.rglob('*.db'))

# Also exercise the optional sibling editor source layout, which is not included
# in the renderer image/bundle and has no independent npm dependency install.
if Path('/delivery/editing').is_dir():
    shutil.copytree('/delivery/editing',root/'editing',ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
    code='''from editing.diagram_edit import DiagramEditor
r=DiagramEditor(scale=1).create_diagram('flowchart TB\\nA --> B\\n','native-editor')
r=DiagramEditor(scale=1).update_node_color(r['rendered']['png'],'native-editor',1,'A','hsl(120,50%,50%)')
assert r['revision']==2 and r['state']['nodes'][0]['style']['fill']=='#40bf40'
print('PASS optional sibling editor source: native Python import, renderer bridge and shared npm dependencies')
'''
    p=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,timeout=60)
    assert p.returncode==0,p.stderr
    print(p.stdout.strip(),flush=True)

print('ALL PACKAGE TESTS PASSED',flush=True)
