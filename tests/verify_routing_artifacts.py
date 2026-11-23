"""Independent QA of requested renders, run in the pinned runtime with /artifacts mounted."""
from verify_geometry import *
import sys

def hits(a,b,box):
    x,y,w,h=box
    if w<=0 or h<=0:return False
    lo,hi=0,1
    for v,d,mn,mx in [(a[0],b[0]-a[0],x+.02,x+w-.02),(a[1],b[1]-a[1],y+.02,y+h-.02)]:
        if abs(d)<1e-12:
            if v<=mn or v>=mx:return False
        else:
            t1,t2=(mn-v)/d,(mx-v)/d
            lo=max(lo,min(t1,t2));hi=min(hi,max(t1,t2))
    return lo<hi

def inflate(box,c):
    x,y,w,h=box;return [x-c,y-c,w+2*c,h+2*c]

for directory in sys.argv[1:]:
    path=Path(directory)
    root=ET.parse(path/'diagram.svg').getroot()
    layout=json.loads((path/'layout.json').read_text())
    check_geometry(root,layout)
    groups={g['id']:g for g in layout['subgraphs']}
    def contains(group,id):
        return id==group or any(m==id or (m in groups and contains(m,id)) for m in groups[group]['members'])
    segments=0
    for e in layout['edges']:
        for a,b in edge_segments(root,e):
            segments+=1
            for node in layout['nodes']:
                if node['id'] in [e['source'],e['target']]:continue
                assert not hits(a,b,inflate(node['box'],10)),(path.name,e['ordinal'],node['id'],'node clearance')
            for other in layout['edges']:
                if other['ordinal']==e['ordinal'] or not other['label_box'][2]:continue
                assert not hits(a,b,inflate(other['label_box'],10)),(path.name,e['ordinal'],other['ordinal'],'label clearance')
            for id,g in groups.items():
                related=contains(id,e['source']) or contains(id,e['target'])
                if related:
                    x,y,w,h=g['box'];title_bottom=g['label_box'][1]+g['label_box'][3]+9
                    assert not hits(a,b,[x-10,y-10,w+20,title_bottom-y+20]),(path.name,e['ordinal'],id,'title band')
                    # A segment within a side's 10 px band must cross it transversely.
                    for band,axis in [([x-10,y,20,h+10],0),([x+w-10,y,20,h+10],0),([x-10,y+h-10,w+20,20],1)]:
                        if hits(a,b,band):
                            assert abs(b[axis]-a[axis])+0.025>=abs(b[1-axis]-a[1-axis]),(path.name,e['ordinal'],id,'parallel border')
                elif id not in [e['source'],e['target']]:
                    assert not hits(a,b,inflate(g['box'],10)),(path.name,e['ordinal'],id,'unrelated group')
    print(f'PASS {path.name}: {len(layout["edges"])} paths, {segments} Cairo-flattened segments, node/label/title/group clearance and marker boundary contacts')
