"""Check verify.sh argv handling with Bash 3.2 and Linux Bash, without Docker.

A fixed exported shell function records the exact docker argv. No eval, command
string assembly, external stub executable, or executable scratch mount is used.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--bash', default='/bin/bash')
args = parser.parse_args()
source = Path(__file__).resolve().parent.parent / 'scripts' / 'verify.sh'
driver = r'''
set -euo pipefail
docker() {
  printf '%s\0' "$@" > "$ARGV_CAPTURE"
  for last in "$@"; do :; done
  if [[ -n "${ARGV_CALLS:-}" ]]; then printf '%s\n' "$last" >> "$ARGV_CALLS"; fi
  if [[ "$last" == "${DOCKER_FAIL_SUFFIX:-__never__}" ]]; then return 7; fi
  return "${DOCKER_TEST_EXIT:-0}"
}
export -f docker
exec "$BASH" "$1" "${2:-runtime}"
'''
with tempfile.TemporaryDirectory(prefix='aiz shell argv ') as temporary:
    root = Path(temporary) / 'checkout with spaces [*]'
    (root / 'scripts').mkdir(parents=True)
    script = root / 'scripts' / 'verify.sh'
    shutil.copyfile(source, script)
    driver_path = Path(temporary) / 'argv driver.sh'
    driver_path.write_text(driver)
    capture = Path(temporary) / 'captured argv'
    base = os.environ.copy()
    for key in ['RENDERER_PLATFORM', 'RENDERER_IMAGE', 'DOCKER_TEST_EXIT']:
        base.pop(key, None)
    base['ARGV_CAPTURE'] = str(capture)
    # Include an invalid-for-Docker value only to verify shell word boundaries;
    # this test does not claim that Docker accepts such a platform/image name.
    cases = [(None, None), ('', None), ('linux/arm64', None),
             ('linux/amd64', None), ('platform with spaces *', 'image with spaces *')]
    for platform, image in cases:
        env = base.copy()
        if platform is not None:
            env['RENDERER_PLATFORM'] = platform
        if image is not None:
            env['RENDERER_IMAGE'] = image
        expected = ['run', '--rm']
        if platform:
            expected += ['--platform', platform]
        expected += ['--network', 'none', '--read-only', '--memory', '2g', '--memory-swap', '2g',
                     '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--ulimit', 'cpu=300:300',
                     '--ulimit', 'nofile=256:256', '--ulimit', 'fsize=268435456:268435456',
                     '--entrypoint', 'python3']
        for filename in ['draw-probe.mjs', 'text_geometry.py', 'subgraph-layout.mjs','elk-layout.mjs',
                         'theme-source.mjs', 'mermaid-model.mjs', '__init__.py', 'renderer.py', 'runtime_version.py']:
            subdir = 'backend/' if filename.endswith('.mjs') or filename == 'text_geometry.py' else ''
            expected += ['-v', f'{root}/renderer/{subdir}{filename}:/app/{filename}:ro']
        expected += ['-v', f'{root}/tests:/app/tests:ro', '--tmpfs', '/tmp:rw,mode=1777',
                     '--tmpfs', '/output:rw,mode=1777', image or 'aiz-render-runtime:local',
                     '/app/tests/verify_runtime.py']
        completed = subprocess.run([args.bash, str(driver_path), str(script)], env=env,
                                   capture_output=True, text=True, timeout=10)
        assert completed.returncode == 0, (platform, completed.stderr)
        actual = [word.decode() for word in capture.read_bytes().split(b'\0')[:-1]]
        assert actual == expected, (platform, actual, expected)
    # Strict-mode failure propagation must remain intact.
    env = base.copy()
    env['DOCKER_TEST_EXIT'] = '7'
    completed = subprocess.run([args.bash, str(driver_path), str(script)], env=env,
                               capture_output=True, text=True, timeout=10)
    assert completed.returncode == 7, completed
    # all must visit every group even after a failure, and never mask an
    # unverified (3) or failed status as success. These are shell-only stubs.
    groups = ['edges', 'subgraphs', 'theme_labels', 'contract', 'runtime', 'regression']
    expected_calls = [f'/app/tests/verify_{group}.py' for group in groups]
    calls = Path(temporary) / 'group calls'
    for failure, exit_code, expected_status in [(None, '0', 0), ('/app/tests/verify_theme_labels.py', '0', 1), (None, '3', 3)]:
        calls.write_text('')
        env = base.copy()
        env['ARGV_CALLS'] = str(calls)
        env['DOCKER_TEST_EXIT'] = exit_code
        if failure: env['DOCKER_FAIL_SUFFIX'] = failure
        completed = subprocess.run([args.bash, str(driver_path), str(script), 'all'], env=env,
                                   capture_output=True, text=True, timeout=10)
        assert completed.returncode == expected_status, completed
        assert calls.read_text().splitlines() == expected_calls
        if expected_status == 1: assert 'GROUP_RESULT theme-labels failed 7' in completed.stdout
        if expected_status == 3: assert 'passed 0' not in completed.stdout
version = subprocess.check_output([args.bash, '--version'], text=True).splitlines()[0]
print(f'PASS shell argv: unset/empty/platform, spaces/globs, unchanged Docker limits, all dispatch/failure/unverified propagation; {version}')
