"""Bash 3.2 wrapper argument forwarding; real render validation stays in Python."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--bash',default='/bin/bash')
args=parser.parse_args()
script=Path(__file__).resolve().parent.parent/'scripts/render.sh'
with tempfile.TemporaryDirectory(prefix='render args [spaces] ') as temporary:
    root=Path(temporary);source=root/'input [*].mmd';source.write_text('flowchart TB\nA\n')
    capture=root/'argv';driver=root/'driver.sh'
    driver.write_text('''set -euo pipefail
docker() {
  if [[ "$1" == info ]]; then return 0; fi
  printf '%s\\0' "$@" > "$ARGV_CAPTURE"
  return "${DOCKER_TEST_EXIT:-0}"
}
export -f docker
exec "$BASH" "$@"
''')
    env=os.environ.copy();env['ARGV_CAPTURE']=str(capture)
    env.pop('RENDERER_PLATFORM',None);env.pop('RENDERER_IMAGE',None);env.pop('DOCKER_TEST_EXIT',None)
    for index,options in enumerate([[],['--scale','1'],['--scale=0.5']]):
        destination=root/f'output [{index}]'
        result=subprocess.run([args.bash,str(driver),str(script),str(source),str(destination),*options],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        argv=[v.decode() for v in capture.read_bytes().split(b'\0')[:-1]]
        assert argv[:3]==['run','--rm','--network']
        for option,value in [('--network','none'),('--memory','2g'),('--memory-swap','2g'),('--cap-drop','ALL'),('--security-opt','no-new-privileges')]:
            assert argv[argv.index(option)+1]==value,(option,argv)
        assert '--read-only' in argv
        assert [argv[i+1] for i,v in enumerate(argv) if v=='--ulimit']==['cpu=300:300','nofile=256:256','fsize=268435456:268435456']
        assert f'{source}:/input/source.mmd:ro' in argv
        assert argv[-5:]==['/input/source.mmd','--output',f'/output/{destination.name}','--scale',['2','1','0.5'][index]],argv
    for options in [['--layout', 'elk'], ['--layout=dagre'], ['--layout=auto']]:
        result=subprocess.run([args.bash,str(driver),str(script),str(source),str(root/'layout-output'),*options],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        argv=[v.decode() for v in capture.read_bytes().split(b'\0')[:-1]]
        assert argv[-2:]==['--layout', options[1] if options[0]=='--layout' else options[0].split('=',1)[1]],argv
    for options in [['--elk-spacing','1.5'],['--elk-spacing=1.3']]:
        result=subprocess.run([args.bash,str(driver),str(script),str(source),str(root/'spaced-output'),'--layout','elk',*options],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        argv=[v.decode() for v in capture.read_bytes().split(b'\0')[:-1]]
        assert argv[-4:]==['--layout','elk','--elk-spacing','1.5' if options[0]=='--elk-spacing' else '1.3'],argv
    for options in [['--elk-spacing'],['--elk-spacing','1.5','--elk-spacing=2'],['--layout'],['--layout=unknown'],['--layout','elk','--layout=dagre'],['--scale'],['--scale','1','--scale','2'],['--unknown'],['out-a','out-b']]:
        capture.unlink(missing_ok=True)
        result=subprocess.run([args.bash,str(driver),str(script),str(source),*options],env=env,capture_output=True,text=True)
        assert result.returncode==2 and not capture.exists(),(options,result.stdout,result.stderr)
    env['DOCKER_TEST_EXIT']='7'
    result=subprocess.run([args.bash,str(driver),str(script),str(source),str(root/'failed'),'--scale','1'],env=env,capture_output=True,text=True)
    assert result.returncode==7 and 'Output:' not in result.stdout,result
print('PASS render argv: default/explicit/fractional scale, spaced paths, invalid/duplicate flags, failure propagation; runtime limits unchanged')
