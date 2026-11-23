"""Repeat one real source through independent Python/Node/Pango/raster processes.

Run in the installed renderer image. Outputs are kept for visual inspection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('input',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--repeats',type=int,default=3)
args=parser.parse_args()
if not 2<=args.repeats<=20:parser.error('--repeats must be between 2 and 20')
args.output.mkdir(parents=True,exist_ok=False)
source=args.input.read_bytes()
snapshot=args.output/'source.mmd'
snapshot.write_bytes(source)
report={'input':str(args.input),'source_sha256':hashlib.sha256(source).hexdigest(),
        'layout':'elk','elk_spacing':1,'scale':1,'fresh_cli_process_each_run':True,
        'status':'running','modes':{}}
for mode in ['raw','default']:
    runs=[]
    for index in range(args.repeats):
        target=args.output/f'{mode}-{index+1}'
        command=[sys.executable,'/app/renderer.py',str(snapshot),'--layout','elk',
                 '--elk-spacing','1','--scale','1','--timeout','60','--output',str(target)]
        if mode=='raw':command.append('--raw-edges')
        subprocess.run(command,check=True,capture_output=True,text=True,timeout=65)
        root=ET.parse(target/'diagram.svg').getroot()
        assert root.attrib['data-layout-engine']=='elk'
        assert root.get('data-edge-postprocessing')=='none'
        runs.append({'directory':target.name,'renderer_version':root.attrib['data-renderer-version'],
                     'viewBox':root.attrib['viewBox'],
                     'sha256':{name:hashlib.sha256((target/name).read_bytes()).hexdigest()
                               for name in ['diagram.svg','diagram.png','layout.json']}})
    identical=all(r['sha256']==runs[0]['sha256'] and r['renderer_version']==runs[0]['renderer_version'] for r in runs)
    report['modes'][mode]={'byte_identical':identical,'runs':runs}
report['status']='passed' if all(m['byte_identical'] for m in report['modes'].values()) else 'failed'
report['default_equals_raw']=report['modes']['raw']['runs'][0]['sha256']==report['modes']['default']['runs'][0]['sha256']
if not report['default_equals_raw']:report['status']='failed'
(args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
if report['status']!='passed':raise SystemExit(1)
