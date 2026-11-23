"""Measure one real CLI process tree in Linux; no estimated memory figures.

RSS is a 10 ms sampled sum over descendant process leaders. Shared pages may
be counted more than once, and short peaks may be missed. This is not PSS or a
proof of the 2 GiB limit. The measurement excludes the measuring process itself.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from verify_common import layout_args, TEST_LAYOUT


def process_tree_rss(root_pid):
    rows = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            status = {}
            for line in (entry / 'status').read_text().splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    status[key] = value.strip()
            rows[int(entry.name)] = (int(status['PPid']), int(status.get('VmRSS', '0 kB').split()[0]) * 1024)
        except (OSError, ValueError, KeyError):
            continue  # Process exited between directory listing and status read.
    descendants = {root_pid}
    while True:
        found = {pid for pid, (parent, _) in rows.items() if parent in descendants}
        if found <= descendants:
            break
        descendants.update(found)
    return sum(rows[pid][1] for pid in descendants if pid in rows), len(descendants & rows.keys())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/proc/self/status').is_file():
        print('UNVERIFIED: Linux /proc memory measurement unavailable', file=sys.stderr)
        return 3
    command = [sys.executable, '/app/renderer.py',*layout_args(), str(args.input), '--scale', '2', '--timeout', '30', '--output', str(args.output)]
    peak = 0
    max_processes = 0
    samples = 0
    started = time.monotonic()
    # Files avoid deadlocking on diagnostic pipes while sampling memory.
    with args.report.with_suffix('.stdout').open('wb') as stdout, args.report.with_suffix('.stderr').open('wb') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL)
        while True:
            rss, count = process_tree_rss(process.pid)
            peak = max(peak, rss)
            max_processes = max(max_processes, count)
            samples += 1
            if process.poll() is not None:
                break
            time.sleep(0.01)
        code = process.wait()
    report = {'layout_engine': TEST_LAYOUT, 'status': 'passed' if code == 0 else 'failed', 'exit_code': code,
              'wall_seconds': time.monotonic() - started, 'sampled_process_tree_peak_rss_bytes': peak,
              'max_observed_processes': max_processes, 'memory_samples': samples, 'sample_interval_seconds': 0.01,
              'memory_method': 'sum of VmRSS for CLI and descendant process leaders via Linux /proc; excludes measuring process; shared pages counted per process; short peaks may be missed',
              'threshold_status': 'mentor threshold not decided; observations only, not a few-seconds SLA pass'}
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print('MEASUREMENT ' + json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
