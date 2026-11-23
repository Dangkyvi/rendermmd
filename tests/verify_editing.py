"""Stateless editing acceptance: actual files, parser, renderer and no database."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import json
from pathlib import Path
import struct
import subprocess
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib
import cairo
sys.path.insert(0,'/app')
from diagram_edit import DiagramEditor, DiagramEditError, _publish
from edit_artifact import ArtifactError, extract, pack, embed_svg, embed_png, MAX_METADATA_BYTES
from renderer import render, RendererError

ROOT=Path('/output/stateless');ROOT.mkdir()
editor=DiagramEditor(scale=1)

def expect(code,fn):
    try:fn()
    except DiagramEditError as e:
        assert e.code==code,(e.code,str(e),e.details)
        return e
    raise AssertionError('Expected '+code)

def new(source='flowchart LR\nA["same"] --> B["same"]\nB --> C["End"]\nD["Other"]\n'):
    return editor.create_diagram(source)

def png(r):return r['rendered']['png']
def svg(r):return r['rendered']['svg']
def edge(r,a,b,index=0):return [e['id'] for e in r['state']['edges'] if e['source']==a and e['target']==b][index]
def call(r,op,*args,**kwargs):
    # A fresh service instance every time. The file is the only continuity.
    return getattr(DiagramEditor(scale=1),op)(png(r),r['diagram_id'],r['revision'],*args,**kwargs)

def unchanged_failure(code,r,op,*args,**kwargs):
    before=deepcopy(r);scratch=set(Path('/tmp').iterdir())
    e=expect(code,lambda:call(r,op,*args,**kwargs))
    assert r==before,'input was modified on failure'
    assert set(Path('/tmp').iterdir())==scratch,'scratch leaked on failure'
    return e

def pixels(data,name):
    path=ROOT/name;path.write_bytes(data)
    image=cairo.ImageSurface.create_from_png(str(path))
    return (image.get_width(),image.get_height(),bytes(image.get_data()))

assert set(vars(editor))=={'scale','timeout'}
assert not hasattr(editor,'undo_diagram_edit') and not hasattr(editor,'redo_diagram_edit')
assert not hasattr(editor,'store_path')
assert 'artifact' in inspect.signature(editor.add_node).parameters
assert not hasattr(editor,'update_edge_endpoints')
# Same semantic/paint/layout coverage as before, plus metadata pixel invariance.
fixtures=[Path('/input/test1.mmd'),Path('/input/test.mmd'),Path('/input/chat_flow.mmd')]
fixtures += [Path('/app/tests/fixtures')/name for name in ['edges.mmd','node-shapes.mmd','modern-shapes.mmd','theme-labels.mmd','subgraphs.mmd','renderer-execution-flow.mmd','node-labels.mmd','showcase-all-shapes-edges.mmd']]
for path in fixtures:
    scratch=set(Path('/tmp').iterdir());r=editor.create_diagram(path.read_text())
    assert set(Path('/tmp').iterdir())==scratch
    payload=extract(png(r));assert payload==extract(svg(r))
    assert set(payload)=={'format','schema','diagram_id','revision','source','state','preview','checksum'}
    assert not any(k in payload for k in ('history','undo_stack','redo_stack','layout','png','svg'))
    canonical=editor._source(r['state']);fresh=render(canonical,scale=1)
    assert fresh.layout==r['rendered']['layout'],path
    assert pixels(fresh.png,'fresh.png')==pixels(png(r),'embedded.png'),path
    file=ROOT/'embedded.svg';file.write_text(svg(r))
    subprocess.run(['rsvg-convert','--zoom=1',f'--output={ROOT}/reraster.png',str(file)],check=True)
    assert pixels((ROOT/'reraster.png').read_bytes(),'reraster-check.png')==pixels(png(r),'embedded-check.png')
    assert len({e['id'] for e in r['state']['edges']})==len(r['state']['edges'])
    print('PASS import/round-trip/metadata pixels:',path.name,flush=True)

r=new();original=deepcopy(r);ab=edge(r,'A','B')
r=call(r,'update_node_label','A','Dấu & "quote" | #123; \\ <script>\r\nNext')
assert r['revision']==2 and 'A' in r['changes']['layout_changed']['nodes'] and r['changes']['layout_changed']['edges']
r=call(r,'update_node_shape','A','diamond')
layout=r['rendered']['layout']
r=call(r,'update_node_color','A','rgba(12, 34, 56, 0.5)')
assert r['state']['nodes'][0]['style']['fill']=='#0c223880' and r['rendered']['layout']==layout
r=call(r,'add_node','new',shape='rounded',fill_color='hsl(120,50%,50%)');node=r['results'][0]['node_id']
assert r['results'][0]['node']['style']['fill']=='#40bf40'
r=call(r,'add_edge','A',node,label='Có',line_style='dotted');e1=r['results'][0]['edge_id']
r=call(r,'add_edge','A',node,label='Có',line_style='thick');e2=r['results'][0]['edge_id'];assert e1!=e2
r=call(r,'update_edge_label',e2,'Other')
assert next(e for e in r['state']['edges'] if e['id']==e1)['label']=='Có'
r=call(r,'update_edge_line_style',e2,'invisible')
r=call(r,'update_edge_line_style',e2,'normal')
assert next(e for e in r['state']['edges'] if e['id']==e2)['arrow_type']=='arrow_point'
r=call(r,'delete_edge',e1);assert e2 in {e['id'] for e in r['state']['edges']}
r=call(r,'delete_node',node)
assert e2 in r['results'][0]['deleted_edge_ids'] and e2 in {e['id'] for e in r['changes']['deleted']['edges']}
for code,op,args in [('id_not_found','update_node_label',('missing','x')),('invalid_diagram','update_node_shape',('A','wave-rect')),('invalid_diagram','update_node_color',('A','url(file:///etc/passwd)')),('invalid_argument','update_edge_line_style',(ab,'bad'))]:
    unchanged_failure(code,r,op,*args)
expect('stale_revision',lambda:editor.get_diagram(png(r),r['diagram_id'],1))
expect('diagram_not_found',lambda:editor.get_diagram(png(r),'wrong',r['revision']))
assert original['state']['nodes'][0]['label']=='same'
print('PASS node/edge operations, stable parallel IDs, cascades, colors, marker restore and file-local revisions',flush=True)

ops=[{'op':'add_node','label':'Step','as':'step'},{'op':'add_edge','source_id':'A','target_id':'$step','label':'condition'}]
before=deepcopy(r);scratch=set(Path('/tmp').iterdir())
preview=call(r,'preview_diagram_edit',ops)
assert preview['preview'] and preview['revision']==r['revision'] and extract(png(preview))['preview']
assert r==before and set(Path('/tmp').iterdir())==scratch
expect('preview_artifact',lambda:editor.get_diagram(png(preview),r['diagram_id'],r['revision']))
saved=call(r,'apply_diagram_edit',ops)
assert saved['revision']==r['revision']+1
assert saved['results'][0]['node_id']!=preview['results'][0]['node_id']
unchanged_failure('id_not_found',r,'apply_diagram_edit',[{'op':'delete_edge','edge_id':ab},{'op':'add_edge','source_id':'A','target_id':'missing'}])
unchanged_failure('unsupported_operation',r,'apply_diagram_edit',[{'op':'undo_diagram_edit'}])
unchanged_failure('unsupported_operation',r,'apply_diagram_edit',[{'op':'update_edge_endpoints','edge_id':ab}])
with patch('diagram_edit.render',side_effect=RendererError('injected failure','engine')):
    unchanged_failure('render_failed',r,'update_node_label','A','not returned')
print('PASS preview/batch atomicity, aliases, unsupported history and render failure cleanup',flush=True)

r=new('flowchart TB\nA chosen@-->|Có| B\nB --> C\nD\n')
r=call(r,'insert_node_on_edge','chosen','Inserted',shape='diamond')
step=r['results'][0]['node_id'];new_ids=r['results'][0]['new_edge_ids']
assert [e['label'] for e in r['results'][0]['new_edges']]==['Có','']
# PNG -> SVG -> PNG across separate instances, preserving actual IDs.
r=editor.update_node_color(svg(r),r['diagram_id'],r['revision'],step,'#aabbcc')
assert set(new_ids)<={e['id'] for e in r['state']['edges']}
r=call(r,'delete_node_and_reconnect',step)
assert r['results'][0]['new_edges'][0]['label']=='Có'
b=new('flowchart TB\nA --> B\nX --> B\nB --> C\nB --> D\n')
unchanged_failure('ambiguous_reconnect',b,'delete_node_and_reconnect','B')
b=call(b,'delete_node_and_reconnect','B',[{'source_id':'A','target_id':'C'},{'source_id':'X','target_id':'D','line_style':'dotted'}])
assert {(e['source'],e['target']) for e in b['state']['edges']}=={('A','C'),('X','D')}
loop=new('flowchart TB\nA --> A\nB\n')
unchanged_failure('ambiguous_reconnect',loop,'delete_node_and_reconnect','A')
loop=call(loop,'insert_node_on_edge',loop['state']['edges'][0]['id'],'Loop step')
print('PASS split/reconnect, conditions, self-loops and SVG/PNG continuity without a server store',flush=True)

source='''flowchart TB
subgraph P ["Parent"]
 A --> B
 subgraph S ["Child"]
  C --> D
 end
end
X --> P
P --> S
D --> X
'''
r=new(source);original=deepcopy(r)
u=call(r,'delete_subgraph','P','ungroup')
assert set(u['results'][0]['promoted_ids'])=={'A','B','S'} and len(u['results'][0]['direct_group_edge_ids'])==2
assert next(g for g in u['state']['subgraphs'] if g['id']=='S')['parent_id'] is None
r=call(original,'delete_subgraph','P','delete_contents')
assert {n['id'] for n in r['state']['nodes']}=={'X'} and not r['state']['edges']
r=call(original,'add_subgraph','Selected',['A','C'],parent_subgraph_id='P');g=r['results'][0]['subgraph_id']
assert {'P','S'}<={g['id'] for g in r['changes']['updated']['subgraphs']}
r=call(r,'rename_subgraph',g,'Longer title')
r=call(r,'move_node_to_subgraph','A',None)
assert r['results'][0]['old_subgraph_id']==g
r=call(r,'add_node','',subgraph_id=g)
unchanged_failure('invalid_argument',r,'delete_subgraph',g,'unknown')
last=new('flowchart TB\nA\n');unchanged_failure('render_failed',last,'delete_node','A')
last=new('flowchart TB\nsubgraph S\n A\nend\n');unchanged_failure('render_failed',last,'delete_subgraph','S','delete_contents')
print('PASS groups, indirect membership changes, deletion modes/frame edges and empty-diagram policy',flush=True)

# Metadata is untrusted; corruption/oversize/schema/source mismatches never publish.
r=new();payload=extract(png(r));raw=pack(payload['diagram_id'],1,payload['source'],payload['state'])
plain=render(payload['source'],scale=1)
corrupt=svg(r).replace('"revision":1','"revision":9')
expect('invalid_artifact',lambda:editor.get_diagram(corrupt,r['diagram_id'],1))
expect('invalid_artifact',lambda:editor.get_diagram(plain.svg,r['diagram_id'],1))
expect('invalid_artifact',lambda:editor.get_diagram(png(r)[:-1],r['diagram_id'],1))
expect('invalid_artifact',lambda:editor.get_diagram(png(r)[:40]+bytes([png(r)[40]^1])+png(r)[41:],r['diagram_id'],1))
for state in [{**payload['state'],'history':[]},{**payload['state'],'nodes':None},{**payload['state'],'node_defaults':{'fill':'url(file:///etc/passwd)'}}]:
    bad=embed_svg(plain.svg,pack(r['diagram_id'],1,payload['source'],state))
    expect('invalid_artifact' if 'history' in state or state['nodes'] is None else 'invalid_diagram',lambda:editor.get_diagram(bad,r['diagram_id'],1))
state=deepcopy(payload['state']);state['nodes'][0]['label']='mismatch'
bad=embed_svg(plain.svg,pack(r['diagram_id'],1,payload['source'],state))
expect('serialization',lambda:editor.get_diagram(bad,r['diagram_id'],1))
# Uploaded SVG primitives are ignored and regenerated from validated source.
injected=svg(r).replace('</svg>','<script>untrusted()</script></svg>')
editor.export_diagram(injected,r['diagram_id'],1,ROOT/'regenerated')
assert '<script>' not in (ROOT/'regenerated/diagram.svg').read_text()
# Duplicate metadata, XML entity declarations and deeply nested JSON are rejected.
duplicate=svg(r).replace('</svg>','<metadata id="mmdToDiagram-edit">{}</metadata></svg>')
expect('invalid_artifact',lambda:editor.get_diagram(duplicate,r['diagram_id'],1))
expect('invalid_artifact',lambda:editor.get_diagram('<!DOCTYPE svg [<!ENTITY x "x">]>'+svg(r),r['diagram_id'],1))
# Enforce the size ceiling and reject duplicate/deep JSON before using a model.
try:pack(r['diagram_id'],1,'x'*MAX_METADATA_BYTES,r['state'])
except ArtifactError:pass
else:raise AssertionError('metadata size bound not enforced')
for invalid in [raw.replace(b'"schema":1',b'"schema":1,"schema":1',1),b'['*2000+b'0'+b']'*2000]:
    bad=embed_svg(plain.svg,invalid)
    expect('invalid_artifact',lambda:editor.get_diagram(bad,r['diagram_id'],1))
body=b'mmdToDiagram.edit\0\1\0\0\0'+b'not-expanded'
chunk=struct.pack('>I',len(body))+b'iTXt'+body+struct.pack('>I',zlib.crc32(body,zlib.crc32(b'iTXt')) & 0xffffffff)
bad=plain.png[:33]+chunk+plain.png[33:]
expect('invalid_artifact',lambda:editor.get_diagram(bad,r['diagram_id'],1))
print('PASS metadata integrity/schema/limits, missing/corrupt files, compressed/deep/duplicate JSON rejection and uploaded graphics discarded',flush=True)

# No server head: two copies intentionally create independent revisions.
with ThreadPoolExecutor(max_workers=2) as pool:
    branches=list(pool.map(lambda label:call(r,'update_node_label','A',label),['left','right']))
assert all(b['revision']==2 for b in branches)
assert branches[0]['state']!=branches[1]['state']
assert set(vars(editor))=={'scale','timeout'}
assert not list(ROOT.rglob('*.sqlite')) and not list(ROOT.rglob('*.db'))
print('PASS stateless independent branches, no registry/database and no retained editor state',flush=True)

# Real packaged CLI, explicit immutable outputs and scratch cleanup.
source=ROOT/'input.mmd';source.write_text('flowchart TB\nA -->|Có| B\n')
def cli(*args,input=None):
    return subprocess.run([sys.executable,'/app/diagram_edit.py','--scale','1',*args],input=input,text=True,capture_output=True,timeout=60)
p=cli('init','--source',str(source),'--diagram-id','cli','--output',str(ROOT/'cli-1'));assert p.returncode==0,p.stderr
created=json.loads(p.stdout);eid=created['state']['edges'][0]['id']
ops=json.dumps([{'op':'insert_node_on_edge','edge_id':eid,'label':'Step'}])
base=ROOT/'cli-1/diagram.png';original=base.read_bytes()
p=cli('preview','--input',str(base),'--diagram-id','cli','--expected-revision','1','--output',str(ROOT/'cli-preview'),input=ops);assert p.returncode==0,p.stderr
p=cli('apply','--input',str(base),'--diagram-id','cli','--expected-revision','1','--output',str(ROOT/'cli-2'),input=ops);assert p.returncode==0,p.stderr
assert json.loads(p.stdout)['revision']==2 and base.read_bytes()==original
p=cli('get','--input',str(ROOT/'cli-2/diagram.svg'),'--diagram-id','cli','--expected-revision','2');assert p.returncode==0,p.stderr
p=cli('apply','--input',str(base),'--diagram-id','cli','--expected-revision','2','--output',str(ROOT/'bad-output'),input=ops)
assert p.returncode==1 and json.loads(p.stderr)['code']=='stale_revision' and not (ROOT/'bad-output').exists()
p=cli('undo');assert p.returncode==2
before=set(ROOT.iterdir())
expect('output_exists',lambda:editor.export_diagram(png(r),r['diagram_id'],1,ROOT/'cli-1'))
with patch('diagram_edit.Path.write_bytes',side_effect=OSError('injected output failure')):
    try:_publish(r,ROOT/'failed-export')
    except OSError:pass
    else:raise AssertionError('expected write failure')
assert set(ROOT.iterdir())==before and not list(ROOT.glob('.edit-export-*'))
assert not list(ROOT.rglob('*.sqlite')) and not list(ROOT.rglob('*.db'))
print('PASS CLI input files, init/apply/preview/get, atomic publication and scratch cleanup on output failure',flush=True)
print('ALL STATELESS EDITING TESTS PASSED',flush=True)
