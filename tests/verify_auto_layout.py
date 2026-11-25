"""Model-based dispatch boundaries and proof that only the selected engine runs."""
from verify_common import *
import sys, tempfile
from unittest.mock import patch
sys.path.insert(0,'/app')
import renderer
from runtime_version import BACKEND_FILES

def nodes(n):return 'flowchart TB\n'+'\n'.join(f'N{i}' for i in range(n))+'\n'
def edges(n):return 'flowchart LR\n'+'A --> B\n'*n
def groups(n):return 'flowchart TB\n'+''.join(f'subgraph S{i}\nN{i}\nend\n' for i in range(n))
cases=[('small','flowchart TB\nA --> B\n','dagre',2,1,0,0),
       ('nodes-below',nodes(24),'dagre',24,0,0,0),('nodes-at',nodes(25),'elk',25,0,0,0),
       ('edges-below',edges(34),'dagre',2,34,0,0),('edges-at',edges(35),'elk',2,35,0,0),
       ('groups-below',groups(2),'dagre',2,0,2,1),('groups-at',groups(3),'elk',3,0,3,1),
       ('depth-at','flowchart TB\nsubgraph S\nsubgraph T\nA\nend\nend\n','elk',1,0,2,2),
       ('implicit','flowchart TB\nA --> B --> C\n%% subgraph fake\n','dagre',3,2,0,0)]
for name,source,engine,n,e,g,d in cases:
    auto=renderer.render(source,layout='auto',scale=1,timeout=60)
    root=ET.fromstring(auto.svg)
    assert root.get('data-layout-engine')==engine,name
    assert json.loads(root.get('data-layout-stats'))==dict(nodes=n,edges=e,subgraphs=g,depth=d),name
    explicit=renderer.render(source,layout=engine,scale=1,timeout=60)
    assert auto.png==explicit.png and auto.layout==explicit.layout,name
    assert root.get('data-layout-policy')=='size-groups-v1'
    print('PASS auto:',name,engine)

for engine,source in [('dagre',cases[0][1]),('elk',groups(3))]:
    with tempfile.TemporaryDirectory() as folder:
        backend=Path(folder)
        for name in BACKEND_FILES:shutil.copyfile(APP/name,backend/name)
        (backend/'node_modules').symlink_to(APP/'node_modules',target_is_directory=True)
        if engine=='dagre':
            (backend/'elk-layout.mjs').write_text("throw new Error('FORBIDDEN_ELK');")
        else:
            p=backend/'subgraph-layout.mjs'
            p.write_text(p.read_text().replace('export function layoutSubgraphs(dagre, graph, groups, rankdir) {',
                "export function layoutSubgraphs(dagre, graph, groups, rankdir) { throw new Error('FORBIDDEN_DAGRE');"))
        with patch.object(renderer,'_BACKEND',backend/'draw-probe.mjs'):
            result=renderer.render(source,layout='auto',scale=1)
            assert ET.fromstring(result.svg).get('data-layout-engine')==engine
    print('PASS auto: unselected engine disabled, chose',engine)
