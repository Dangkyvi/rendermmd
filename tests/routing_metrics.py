"""Metrics on emitted polylines; crossings and shared segments are distinct."""
def routing_metrics(layout, minimum_overlap=8):
    edges=layout['edges']; pairs=[];total=0;bends=0
    for edge in edges:
        ps=edge['points']
        bends+=sum(abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>1e-7
                   for a,b,c in zip(ps,ps[1:],ps[2:]))
    for i,e in enumerate(edges):
        for f in edges[i+1:]:
            extent=0
            for a,b in zip(e['points'],e['points'][1:]):
                for c,d in zip(f['points'],f['points'][1:]):
                    if abs(a[1]-b[1])<1e-6 and abs(c[1]-d[1])<1e-6 and abs(a[1]-c[1])<1e-6:
                        extent+=max(0,min(max(a[0],b[0]),max(c[0],d[0]))-max(min(a[0],b[0]),min(c[0],d[0])))
                    elif abs(a[0]-b[0])<1e-6 and abs(c[0]-d[0])<1e-6 and abs(a[0]-c[0])<1e-6:
                        extent+=max(0,min(max(a[1],b[1]),max(c[1],d[1]))-max(min(a[1],b[1]),min(c[1],d[1])))
            if extent>=minimum_overlap:
                pairs.append([e['ordinal'],f['ordinal']]);total+=extent
    return {'shared_pairs':len(pairs),'shared_pair_ordinals':pairs,'shared_length':total,
            'overlap_threshold':minimum_overlap,'bends':bends,
            'width':layout['width'],'height':layout['height']}
