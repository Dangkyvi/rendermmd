"""Offline integration checks against actual SVG geometry, not data-* copies."""
import json
import shutil
import math
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import cairo

APP = Path('/app')
OUT = Path('/output/result')
NS = {'s': 'http://www.w3.org/2000/svg'}

def run(source):
    Path('/output/input.mmd').write_text(source)
    # Only this disposable test container owns this output; renderer never deletes it.
    shutil.rmtree(OUT, ignore_errors=True)
    subprocess.run(['python3', '/app/renderer.py', '/output/input.mmd', '--output', str(OUT)], check=True, timeout=35)
    root = ET.parse(OUT / 'diagram.svg').getroot()
    layout = json.loads((OUT / 'layout.json').read_text())
    # Raster must be the very SVG returned, at default 2x; decode pixel data too.
    subprocess.run(['rsvg-convert', '--zoom=2', '--output=/output/check.png', str(OUT / 'diagram.svg')], check=True)
    assert (OUT / 'diagram.png').read_bytes() == Path('/output/check.png').read_bytes()
    png = cairo.ImageSurface.create_from_png(str(OUT / 'diagram.png'))
    assert png.get_width() == math.ceil(layout['width'] * 2)
    assert png.get_height() == math.ceil(layout['height'] * 2)
    assert any(png.get_data()), 'empty raster'
    assert list(map(float, root.attrib['viewBox'].split())) == [0, 0, layout['width'], layout['height']]
    ids = [e.attrib['id'] for e in root.iter() if 'id' in e.attrib]
    assert len(ids) == len(set(ids)), 'duplicate SVG IDs'
    for edge in layout['edges']:
        line = root.find(f"s:path[@data-ordinal='{edge['ordinal']}']", NS)
        assert line is not None
        points = json.loads(line.attrib['data-points'])
        assert edge['points'] == points
        assert len(points) >= 2 and all(math.isfinite(n) for p in points for n in p)
        assert [edge['source'], edge['target']] == [line.attrib['data-source'], line.attrib['data-target']]
        label = root.find(f"s:g[@data-edge-label='{edge['ordinal']}']", NS)
        if label is None:
            assert edge['label_box'] == [0, 0, 0, 0]
        else:
            path = label.find('s:path', NS)
            ctx = path_context(path.attrib['d'])
            x1, y1, x2, y2 = ctx.path_extents()
            tx, ty = map(float, re.fullmatch(r'translate\(([^ ]+) ([^ ]+)\)', path.attrib['transform']).groups())
            assert_close(edge['label_box'], [x1 + tx, y1 + ty, x2 - x1, y2 - y1])
    return root, layout

def assert_close(a, b, tolerance=1e-7):
    assert len(a) == len(b) and all(abs(x-y) <= tolerance for x,y in zip(a,b)), (a,b)

def path_context(d):
    ctx = cairo.Context(cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None))
    tokens = re.findall(r'[MLCQZ]|[-+]?(?:\d*\.\d+|\d+)(?:e[-+]?\d+)?', d, re.I)
    i = 0
    while i < len(tokens):
        op = tokens[i]; i += 1
        count = {'M':2, 'L':2, 'C':6, 'Q':4, 'Z':0}[op]
        args = list(map(float, tokens[i:i+count])); i += count
        if op=='Q':
            x,y=ctx.get_current_point();cx,cy,ex,ey=args
            ctx.curve_to(x+2*(cx-x)/3,y+2*(cy-y)/3,ex+2*(cx-ex)/3,ey+2*(cy-ey)/3,ex,ey)
            continue
        {'M':ctx.move_to, 'L':ctx.line_to, 'C':ctx.curve_to, 'Z':ctx.close_path}[op](*args)
    return ctx

def outline(group):
    shape = list(group)[0]
    tag = shape.tag.split('}')[-1]
    a = {k: float(v) for k,v in shape.attrib.items() if k in ('x','y','width','height','cx','cy','r','rx','ry')}
    if tag == 'polygon':
        points = [tuple(map(float, p.split(','))) for p in shape.attrib['points'].split()]
        return points + points[:1]
    if tag == 'circle':
        return [(a['cx'] + a['r']*math.cos(t*math.tau/4096),
                 a['cy'] + a['r']*math.sin(t*math.tau/4096)) for t in range(4097)]
    if tag == 'rect':
        x, y, w, h = a['x'], a['y'], a['width'], a['height']
        r = a.get('rx', 0)
        if not r:
            return [(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
        points = []
        for cx,cy,start in [(x+w-r,y+r,-math.pi/2), (x+w-r,y+h-r,0),
                            (x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)]:
            points += [(cx + r*math.cos(start + t*math.pi/2048),
                        cy + r*math.sin(start + t*math.pi/2048)) for t in range(1025)]
        return points + points[:1]
    assert tag == 'path' and 'A' in shape.attrib['d']
    # M x top A halfwidth radius 0 0 1 right top L right bottom A ...
    vals = list(map(float, re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:e[-+]?\d+)?',shape.attrib['d'],re.I)))
    x, top, rx, ry = vals[:4]
    right, bottom = vals[9:11]
    cx = x+rx
    points = [(cx + rx*math.cos(math.pi + t*math.pi/2048),
               top + ry*math.sin(math.pi + t*math.pi/2048)) for t in range(2049)]
    points += [(cx + rx*math.cos(t*math.pi/2048),
                bottom + ry*math.sin(t*math.pi/2048)) for t in range(2049)]
    return points + points[:1]

def distance_to_outline(p, points):
    nearest = float('inf')
    for a,b in zip(points, points[1:]):
        dx,dy = b[0]-a[0], b[1]-a[1]
        length = dx*dx+dy*dy
        t = max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
        nearest = min(nearest, math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy))
    return nearest



def edge_segments(root, edge):
    """Independently flatten the actual painted M/L/Q body through Cairo."""
    line=root.find(f"s:path[@data-ordinal='{edge['ordinal']}']",NS)
    ctx=path_context(line.attrib['d'])
    ctx.set_tolerance(.001)
    previous=None
    for kind,coords in ctx.copy_path_flat():
        if kind==cairo.PATH_MOVE_TO: previous=coords
        elif kind==cairo.PATH_LINE_TO:
            yield previous,coords
            previous=coords
