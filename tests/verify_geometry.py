"""Shared checks of emitted SVG primitives and Cairo glyph paths. No tests run on import."""
from verify_common import *

LEGACY = {
    'rect':'square', 'rounded':'round', 'stadium':'stadium',
    'subroutine':'subroutine', 'cylinder':'cylinder', 'circle':'circle',
    'diamond':'diamond', 'hexagon':'hexagon', 'parallelogram':'lean_right',
    'parallelogram_alt':'lean_left', 'trapezoid':'trapezoid',
    'trapezoid_alt':'inv_trapezoid', 'flag':'odd', 'double_circle':'doublecircle',
}

def metadata(source):
    Path('/output/metadata.mmd').write_text(source)
    return json.loads(subprocess.check_output(['node','/app/tests/inspect-edges.mjs','/output/metadata.mmd']))

def contained(a,b,margin=0):
    return a[0] >= b[0]+margin-1e-7 and a[1] >= b[1]+margin-1e-7 and a[0]+a[2] <= b[0]+b[2]-margin+1e-7 and a[1]+a[3] <= b[1]+b[3]-margin+1e-7

def overlaps(a,b):
    return a[0] < b[0]+b[2]-1e-6 and a[0]+a[2] > b[0]+1e-6 and a[1] < b[1]+b[3]-1e-6 and a[1]+a[3] > b[1]+1e-6

def label_geometry(group):
    path = next(p for p in group.findall('s:path',NS) if 'transform' in p.attrib)
    ctx = path_context(path.attrib['d'])
    x1,y1,x2,y2 = ctx.path_extents()
    tx,ty = map(float,re.fullmatch(r'translate\(([^ ]+) ([^ ]+)\)',path.attrib['transform']).groups())
    return [x1+tx,y1+ty,x2-x1,y2-y1]

def inside_polygon(p, polygon):
    x,y=p
    count=0
    for a,b in zip(polygon,polygon[1:]):
        if (a[1]>y)!=(b[1]>y) and x < a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]): count+=1
    return count%2 == 1

def check_geometry(root, layout):
    outlines={}
    for node in layout['nodes']:
        group=next(g for g in root.findall('s:g[@data-node-box]',NS) if g.attrib['id']==node['id'])
        shape=list(group)[0]
        kind=LEGACY.get(node['id'])
        tag=shape.tag.split('}')[-1]
        if kind in ['square','round','stadium','subroutine']:
            assert tag=='rect'
            rx=float(shape.attrib.get('rx',0))
            assert rx == (float(shape.attrib['height'])/2 if kind=='stadium' else 8 if kind=='round' else 0)
        elif kind in ['circle','doublecircle']:
            assert tag=='circle'
            assert len(group.findall('s:circle',NS))==(2 if kind=='doublecircle' else 1)
        elif kind=='cylinder':
            assert tag=='path' and shape.attrib['d'].count('A')==2
            assert group.find('s:ellipse',NS) is not None
        elif kind:
            assert tag=='polygon'
            pts=[tuple(map(float,p.split(','))) for p in shape.attrib['points'].split()]
            assert len(pts)==(6 if kind=='hexagon' else 5 if kind=='odd' else 4)
            top=[p[0] for p in pts if p[1]==min(q[1] for q in pts)]
            bottom=[p[0] for p in pts if p[1]==max(q[1] for q in pts)]
            if kind=='lean_right': assert min(top)>min(bottom) and max(top)>max(bottom)
            if kind=='lean_left': assert min(top)<min(bottom) and max(top)<max(bottom)
            if kind=='trapezoid': assert max(top)-min(top)<max(bottom)-min(bottom)
            if kind=='inv_trapezoid': assert max(top)-min(top)>max(bottom)-min(bottom)
            if kind=='odd': assert pts[-1][0]>min(p[0] for p in pts)
        boundary=outline(group)
        outlines[node['id']]=boundary
        xs=[p[0] for p in boundary]; ys=[p[1] for p in boundary]
        assert_close(node['box'],[min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)],0.01)
        actual=label_geometry(group)
        assert_close(actual,node['label_box'])
        # All four label-box edges must lie inside the real shape, not just bbox.
        x,y,w,h=actual
        for t in range(21):
            t/=20
            for p in [(x+t*w,y),(x+t*w,y+h),(x,y+t*h),(x+w,y+t*h)]:
                assert inside_polygon(p,boundary), (node['id'], 'label outside shape',p)
        if node['id']=='double_circle':
            inner=group.findall('s:circle',NS)[1]
            cx,cy,r=[float(inner.attrib[key]) for key in ['cx','cy','r']]
            assert all(math.hypot(px-cx,py-cy)<r-1 for px in [x,x+w] for py in [y,y+h])
        if node['id']=='subroutine':
            lines=group.findall('s:line',NS)
            assert x>float(lines[0].attrib['x1']) and x+w<float(lines[1].attrib['x1'])
        if node['id']=='cylinder':
            ellipse=group.find('s:ellipse',NS)
            cap_bottom=float(ellipse.attrib['cy'])+float(ellipse.attrib['ry'])
            assert y>cap_bottom and y+h<node['box'][1]+node['box'][3]-24
    for sg in layout['subgraphs']:
        group=next(g for g in root.findall('s:g[@data-subgraph-box]',NS) if g.attrib['id']==sg['id'])
        rect=group.find('s:rect',NS)
        actual=[float(rect.attrib[k]) for k in ['x','y','width','height']]
        assert_close(sg['box'],actual)
        assert_close(sg['label_box'],label_geometry(group))
        assert contained(sg['label_box'],actual,10)
        x,y,w,h=actual
        outlines[sg['id']]=[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
    for edge in layout['edges']:
        line=root.find(f"s:path[@data-ordinal='{edge['ordinal']}']",NS)
        pts=edge['points']
        for side,node,index,neighbor in [('start',edge['source'],0,1),('end',edge['target'],-1,-2)]:
            p,q=pts[index],pts[neighbor]
            tip=p
            if f'marker-{side}' in line.attrib:
                marker_id=re.fullmatch(r'url\(#(.*)\)',line.attrib[f'marker-{side}']).group(1)
                marker=next(m for m in root.findall('s:defs/s:marker',NS) if m.attrib['id']==marker_id)
                extent=float(marker.attrib['markerWidth'])
                dx,dy=p[0]-q[0],p[1]-q[1];length=math.hypot(dx,dy)
                tip=[p[0]+extent*dx/length,p[1]+extent*dy/length]
            distance=distance_to_outline(tip,outlines[node])
            assert distance<0.025,(node,side,tip,distance)
    return outlines

