from verify_common import *


def group(root,id):
    return next(g for g in root.findall('s:g',NS) if g.attrib.get('id')==id)

def glyph(group):
    return next(p for p in group.findall('s:path',NS) if 'transform' in p.attrib)

def geometry(path):
    x1,y1,x2,y2=path_context(path.attrib['d']).path_extents()
    tx,ty=map(float,re.fullmatch(r'translate\(([^ ]+) ([^ ]+)\)',path.attrib['transform']).groups())
    return [x1+tx,y1+ty,x2-x1,y2-y1]

def measure(text,family='Noto Sans',size=15,weight='normal',style='normal'):
    item={'text':text,'font_family':family,'font_px':size,'font_weight':weight,'font_style':style}
    return json.loads(subprocess.check_output(['python3','/app/text_geometry.py'],input=json.dumps([item]).encode()))[0]

def check_glyph(path,text,**font):
    expected=measure(text,**font)
    assert path.attrib['d']==expected['path']
    assert float(path.attrib['font-size'])==expected['font_px']
    assert path.attrib['font-family']==', '.join(expected['fonts_used'])
    return expected

def check_layout_labels(root,layout):
    for entity in layout['nodes']+layout['subgraphs']:
        path=glyph(group(root,entity['id']))
        assert_close(entity['label_box'],geometry(path))
        x,y,w,h=entity['box'];lx,ly,lw,lh=entity['label_box']
        assert lx>=x and ly>=y and lx+lw<=x+w and ly+lh<=y+h
    all_boxes=[n['box'] for n in layout['nodes']+layout['subgraphs']]
    for x,y,w,h in all_boxes:
        assert x>=0 and y>=0 and x+w<=layout['width']+1e-6 and y+h<=layout['height']+1e-6
    for element in root.iter():
        assert element.tag.split('}')[-1] not in ['script','foreignObject','image','a','style','text']
        for key,value in element.attrib.items():
            assert not key.lower().startswith('on') and 'href' not in key.lower()
            assert 'file:' not in value.lower() and 'http:' not in value.lower() and 'https:' not in value.lower()
            if 'url(' in value:
                assert key in ['marker-start','marker-end'] and re.fullmatch(r'url\(#[^()]+\)',value)

source=(APP/'tests/fixtures/theme-labels.mmd').read_text()
root,layout=run(source)
themed_snapshot=[(OUT/name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
check_layout_labels(root,layout)
assert layout['font_px']==20
assert layout['font_family_used']=='Noto Sans, Noto Serif'
assert root.attrib['font-size']=='20' and root.attrib['font-family']==layout['font_family_used']
a,b,c,s=[group(root,id) for id in ['A','B','C','S']]
assert list(a)[0].attrib['fill']=='#fce7f3'         # inline > second > first > default > theme
assert list(a)[0].attrib['stroke']=='#4338ca'       # first still supplies border
assert list(a)[0].attrib['stroke-width']=='4'
assert glyph(a).attrib['fill']=='#831843'
check_glyph(glyph(a),'Dựng sẵn\nTiếng Việt "A" &',family='Noto Serif',size=26,weight='bold',style='italic')
assert list(b)[0].attrib['fill']=='#e0e7ff' and glyph(b).attrib['fill']=='#312e81'
check_glyph(glyph(b),'Dấu kết hợp\nTiếng Việt',size=22)
assert list(c)[0].attrib['fill']=='#fefce8' and list(c)[0].attrib['stroke']=='#854d0e'
check_glyph(glyph(c),'Mặc định',size=20)
assert list(s)[0].attrib['fill']=='#ecfeff' and list(s)[0].attrib['stroke']=='#155e75'
assert glyph(s).attrib['fill']=='#164e63'
check_glyph(glyph(s),'Nhóm\nTiếng Việt',size=20)
for ordinal,color_,width,labelsize,weight in [(0,'#334155',1.5,20,'normal'),(1,'#be123c',5,24,'bold')]:
    line=root.find(f"s:path[@data-ordinal='{ordinal}']",NS)
    assert line.attrib['stroke']==color_ and float(line.attrib['stroke-width'])==width
    marker_id=re.fullmatch(r'url\(#(.*)\)',line.attrib['marker-end']).group(1)
    marker=next(m for m in root.findall('s:defs/s:marker',NS) if m.attrib['id']==marker_id)
    assert marker.find('s:path',NS).attrib['fill']==color_
    label=root.find(f"s:g[@data-edge-label='{ordinal}']",NS)
    path=glyph(label)
    check_glyph(path,['nhánh một','nhánh hai'][ordinal],size=labelsize,weight=weight)
    assert path.attrib['fill']==['#0f172a','#9f1239'][ordinal]
assert [e['ordinal'] for e in layout['edges']]==[0,1]
assert layout['edges'][0]['points']!=layout['edges'][1]['points']
assert layout['edges'][0]['label_box']!=layout['edges'][1]['label_box']
# Title is a Pango path inside viewBox, above all graph content.
title=root.find('s:path[@data-title-box]',NS)
assert title is not None
check_glyph(title,'Sơ đồ Tiếng Việt & AIZ',size=20)
title_box=geometry(title)
assert_close(json.loads(title.attrib['data-title-box']),title_box)
x,y,w,h=title_box
assert x>=0 and y>=0 and x+w<=layout['width'] and y+h<=layout['height']
assert y+h < min(e['box'][1] for e in layout['nodes']+layout['subgraphs'])
# Verify the returned PNG includes visible title pixels, not merely SVG markup.
original=cairo.ImageSurface.create_from_png(str(OUT/'diagram.png'))
root.remove(title)
ET.ElementTree(root).write('/output/without-title.svg',encoding='utf-8')
subprocess.run(['rsvg-convert','--zoom=2','--output=/output/without-title.png','/output/without-title.svg'],check=True)
without=cairo.ImageSurface.create_from_png('/output/without-title.png')
old=bytes(original.get_data());new=bytes(without.get_data());stride=original.get_stride()
assert any(old[row*stride+int(x*2)*4:row*stride+math.ceil((x+w)*2)*4]!=new[row*stride+int(x*2)*4:row*stride+math.ceil((x+w)*2)*4] for row in range(int(y*2),math.ceil((y+h)*2)))
print('PASS theme-labels: class/default/inline priority, node/subgraph styles, parallel linkStyle ordinals, actual font paths and title pixels')

# Palette comes from the installed official theme computation, not hard-coded
# approximations of Mermaid's default/base/dark/forest/neutral colors.
for theme in ['default','base','dark','forest','neutral']:
    source=f'---\nconfig:\n  theme: {theme}\n---\nflowchart LR\nsubgraph S\n A --> B\nend\n'
    root,layout=run(source)
    Path('/output/theme.mmd').write_text(source)
    actual=json.loads(subprocess.check_output(['node','/app/tests/inspect-theme.mjs','/output/theme.mmd']))
    variables=actual['config']['themeVariables']
    assert list(group(root,'A'))[0].attrib['fill']==variables['mainBkg']
    assert list(group(root,'A'))[0].attrib['stroke']==variables['nodeBorder']
    assert list(group(root,'S'))[0].attrib['fill']==variables['clusterBkg']
    assert root.find('s:path',NS).attrib['stroke']==variables['defaultLinkColor']
    assert root.find('s:rect[@data-background]',NS).attrib['fill']==variables['background']
    check_layout_labels(root,layout)
print('PASS theme-labels: five official theme palettes')

# Changing the global font changes Pango geometry before layout, across all labels.
base='flowchart LR\nsubgraph S ["Nhóm"]\n A["Tiếng Việt"] -->|Nhãn cạnh| B\nend\n'
root,small=run('---\nconfig:\n  fontFamily: Noto Serif\n  fontSize: 12\n---\n'+base)
small_boxes={n['id']:n['box'] for n in small['nodes']}
root,large=run('---\nconfig:\n  themeVariables:\n    fontFamily: Noto Serif\n    fontSize: 32px\n---\n'+base)
check_layout_labels(root,large)
assert large['font_px']==32 and large['font_family_used']=='Noto Serif'
assert next(n for n in large['nodes'] if n['id']=='A')['box'][2]>small_boxes['A'][2]
check_glyph(glyph(group(root,'A')),'Tiếng Việt',family='Noto Serif',size=32)
for path in root.findall('.//s:path[@transform]',NS): assert path.attrib['font-size']=='32'
print('PASS theme-labels: root and themeVariables font settings measured before layout')

# All br spellings, Mermaid named/decimal entities, NFC vs NFD Vietnamese.
source='''flowchart TB
A["Một<br>Hai<br/>Ba<br />Bốn #quot; #amp; #9829;"]
B["Tiếng Việt"]
C["Tiếng Việt"]
'''
root,layout=run(source)
check_layout_labels(root,layout)
check_glyph(glyph(group(root,'A')),'Một\nHai\nBa\nBốn " & ♥')
assert glyph(group(root,'B')).attrib['d']==glyph(group(root,'C')).attrib['d']
print('PASS theme-labels: br variants, named/decimal entities and canonically equivalent Vietnamese glyph paths')

# Title wider than the graph expands viewBox and consistently moves graph geometry.
long_title='Tiêu đề tiếng Việt dài hơn nội dung sơ đồ '*8
root,layout=run('---\ntitle: "'+long_title+'"\n---\nflowchart TB\nA --> B\n')
check_layout_labels(root,layout)
title=root.find('s:path[@data-title-box]',NS)
x,y,w,h=geometry(title)
assert x>=19 and x+w<=layout['width']-19 and y+h<min(n['box'][1] for n in layout['nodes'])
print('PASS theme-labels: long title expands viewBox without cropping or coordinate drift')

# Fail closed on configuration/code/resource/style injection and unknown fonts.
def rejects(source,part,allow_syntax=False):
    Path('/output/input.mmd').write_text(source)
    result=subprocess.run(['python3','/app/renderer.py',*layout_args(),'/output/input.mmd','--output','/output/rejected'],capture_output=True,text=True,timeout=30)
    assert result.returncode!=0,source
    error=json.loads(result.stderr)
    assert error['category']=='source' and error['kind'] in ['syntax','source'],error
    assert (allow_syntax and error['kind']=='syntax') or part.lower() in error['message'].lower(),error
    assert not Path('/output/rejected').exists(),'stale success output'

for style in ['fill:url(file:///etc/passwd)','stroke:url(https://example.invalid/a.svg)',
              'filter:url(#outside)','transform:translate(100px)','rx:99px',
              'font-family:url(https://example.invalid/font)','color:var(--external)',
              'onclick:alert(1)','fill:expression(alert(1))']:
    rejects('flowchart TB\nA\nclassDef unsafe '+style+'\n','an toàn',allow_syntax=True)
for config in ['securityLevel: loose','themeCSS: "@import url(file:///etc/passwd)"',
               'fontFamily: "file:///etc/passwd"','unknown: true',
               'themeVariables:\n    primaryColor: "url(https://example.invalid/a)"',
               'themeVariables:\n    fontFamily: "url(file:///font.ttf)"']:
    rejects('---\nconfig:\n  '+config+'\n---\nflowchart TB\nA\n','an toàn')
rejects('%%{init: {"securityLevel":"loose"}}%%\nflowchart TB\nA\n','directive')
rejects('---\nconfig:\n  fontFamily: AIZ Font Not Installed\n---\nflowchart TB\nA\n','chưa được đóng gói')
rejects('flowchart TB\nA:::missing\nclassDef missing font-family:AIZ Missing Font\n','chưa được đóng gói')
rejects('flowchart TB\nA["\U0010ffff"]\n','glyph')
rejects('flowchart TB\nA\nclick A "file:///etc/passwd"\n','không được phép')
rejects('flowchart TB\nA\nclick A call alert()\n','không được phép')
print('PASS theme-labels: rejected unsafe config/style/links, missing fonts and missing glyphs')

# Generic fallback is explicit and reports the packaged resolved family.
root,layout=run('---\nconfig:\n  fontFamily: sans-serif\n---\nflowchart TB\nA\n')
assert layout['font_family_used']=='Noto Sans'
check_glyph(glyph(group(root,'A')),'A')
# Dotted/invisible semantics survive source styles; invisible labels stay hidden.
root,layout=run('flowchart LR\nA -.->|hiện| B\nB ~~~|ẩn| C\nlinkStyle 1 stroke:red,color:blue,font-size:32px\n')
assert root.find("s:path[@data-ordinal='0']",NS).attrib['stroke-dasharray']=='3 3'
line=root.find("s:path[@data-ordinal='1']",NS)
assert line.attrib['stroke']=='none' and 'marker-end' not in line.attrib
assert layout['edges'][1]['label_box']==[0,0,0,0]
print('PASS theme-labels: documented generic font resolution; dotted/invisible behavior preserved')

# Invisible/empty measurements must not add a phantom global font to the report.
root,layout=run('flowchart LR\nA:::serif --> B:::serif\nclassDef serif font-family:Noto Serif,font-size:24px\n')
assert layout['font_family_used']=='Noto Serif'
print('PASS theme-labels: font report contains visible shaped fonts, not unused empty-label defaults')

# Paint-only styles and thick outlines cannot change geometric outlines, ports
# or marker offsets. Exercise every existing shape under a larger styled font.
shape_source=(APP/'tests/fixtures/node-shapes.mmd').read_text()
shape_source+='\nclassDef default fill:#ecfeff,stroke:#164e63,stroke-width:8px,stroke-dasharray:5 2,color:#134e4a,font-family:Noto Serif,font-size:28px,font-weight:700\n'
shape_source+='linkStyle default stroke:#b91c1c,stroke-width:7px,color:#7f1d1d,font-size:18px\n'
root,layout=run(shape_source)
check_layout_labels(root,layout)
outlines={g.attrib['id']:outline(g) for g in root.findall('s:g[@data-node-box]',NS)}
for node in layout['nodes']:
    pts=outlines[node['id']];xs=[p[0] for p in pts];ys=[p[1] for p in pts]
    assert_close(node['box'],[min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)],0.01)
    path=glyph(group(root,node['id']))
    check_glyph(path,'Nhãn rộng tiếng Việt',family='Noto Serif',size=28,weight='700')
for edge in layout['edges']:
    line=root.find(f"s:path[@data-ordinal='{edge['ordinal']}']",NS)
    points=edge['points']
    for side,id,index,neighbor in [('start',edge['source'],0,1),('end',edge['target'],-1,-2)]:
        p,q=points[index],points[neighbor];tip=p
        ref=line.attrib.get(f'marker-{side}')
        if ref:
            marker_id=re.fullmatch(r'url\(#(.*)\)',ref).group(1)
            marker=next(m for m in root.findall('s:defs/s:marker',NS) if m.attrib['id']==marker_id)
            extent=float(marker.attrib['markerWidth'])
            dx,dy=p[0]-q[0],p[1]-q[1];length=math.hypot(dx,dy)
            tip=[p[0]+extent*dx/length,p[1]+extent*dy/length]
        assert distance_to_outline(tip,outlines[id])<0.025,(id,side,tip)
print('PASS theme-labels: styled larger fonts, thick/dashed outlines and marker contacts on all 14 shapes')

# Explicit subgraph class and its font participate in real header reservation.
root,layout=run('''flowchart TB
subgraph S ["Nhãn nhóm nhiều dòng<br>Tiếng Việt"]
 A --> B
end
classDef cluster fill:#ffedd5,stroke:#9a3412,color:#7c2d12,font-family:Noto Serif,font-size:36px,font-weight:bold
class S cluster
''')
check_layout_labels(root,layout)
sg=layout['subgraphs'][0]
check_glyph(glyph(group(root,'S')),'Nhãn nhóm nhiều dòng\nTiếng Việt',family='Noto Serif',size=36,weight='bold')
assert list(group(root,'S'))[0].attrib['fill']=='#ffedd5'
assert sg['label_box'][1]+sg['label_box'][3]<min(n['box'][1] for n in layout['nodes'])
print('PASS theme-labels: subgraph class font sizes reserve actual title space')

rejects('flowchart TB\nA["<b>bold</b>"]\n','HTML chưa hỗ trợ')
rejects('flowchart TB\nA["`**bold**`"]\n','Markdown chưa')
Path('/output/input.mmd').write_text('---\nconfig:\n  theme: [base\n---\nflowchart TB\nA\n')
error_run=subprocess.run(['python3','/app/renderer.py',*layout_args(),'/output/input.mmd','--output','/output/rejected'],capture_output=True,text=True)
assert error_run.returncode!=0
error=json.loads(error_run.stderr)
assert error['kind']=='syntax' and isinstance(error['line'],int) and error['line']>=3
print('PASS theme-labels: unsupported formatted labels fail explicitly; YAML syntax errors report source lines')

root,layout=run('flowchart TB\nA["Tiếng Việt العربية"]\n')
expected=check_glyph(glyph(group(root,'A')),'Tiếng Việt العربية')
assert len(expected['fonts_used'])>=2 and 'Noto Sans' in expected['fonts_used']
assert layout['font_family_used']==', '.join(expected['fonts_used'])
print('PASS theme-labels: local per-glyph font fallback reported from actual Pango runs')

run((APP/'tests/fixtures/theme-labels.mmd').read_text())
assert themed_snapshot==[(OUT/name).read_bytes() for name in ['diagram.svg','diagram.png','layout.json']]
print('PASS theme-labels: themed SVG/PNG/layout deterministic across separate renders')
