"""Content identity for source plus externally supplied runtime fingerprints."""
import hashlib
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
# Deployment configuration, not input from Mermaid or per-diagram state.
RUNTIME_ROOT=Path(os.environ.get('AIZ_RENDERER_RUNTIME_DIR',str(ROOT))).resolve()
BACKEND_FILES=('draw-probe.mjs','text_geometry.py','subgraph-layout.mjs','elk-layout.mjs','theme-source.mjs','mermaid-model.mjs')
ENVIRONMENT_FILES=('runtime-manifest.json','build-identity.json')
POLICY_FILES=('__init__.py','renderer.py','runtime_version.py','package.json','package-lock.json',*ENVIRONMENT_FILES)


def renderer_version(backend_directory=None):
    backend_directory=Path(backend_directory) if backend_directory is not None else (ROOT/'backend' if (ROOT/'backend').is_dir() else ROOT)
    digest=hashlib.sha256(b'aiz-renderer-v1\0')
    files=[(n,backend_directory) for n in BACKEND_FILES]
    files += [(n,RUNTIME_ROOT if n in ENVIRONMENT_FILES else ROOT) for n in POLICY_FILES]
    for name,base in files:
        digest.update(name.encode()+b'\0')
        with (base/name).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        digest.update(b'\0')
    return 'aiz-mermaid-v1-sha256:'+digest.hexdigest()


# Missing deployment fingerprints remain an explicit dependency error on render.
try:RENDERER_VERSION=renderer_version()
except OSError:RENDERER_VERSION=None
