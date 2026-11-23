# Hướng dẫn kỹ thuật và kiểm chứng

Các đường dẫn đã chuyển theo [README gốc](../README.md). Image mặc định hiện tại
là `aiz-render-runtime:local`; các phần nhắc image/revision cũ dưới đây là lịch sử.
Trạng thái kiểm chứng hiện tại nằm trong [audit](renderer-requirements-audit.md).

Run from the repository root:

```sh
scripts/verify.sh edges
```

The suite uses the existing `aiz-render-runtime:local` image (override with
`RENDERER_IMAGE`). It invokes `/app/renderer.py` in a disposable container
with `--network none`, the image's default user and sandbox, read-only source
mounts, and temporary output. It neither builds nor downloads dependencies.
Failures exit nonzero. No dependencies were added for these checks.

The metadata mapping was checked against Mermaid 12.3.0 installed in that image:
`FlowDB.destructStartLink`, `destructEndLink`, `destructLink` in
`dist/chunks/mermaid.core/chunk-QB3YPZ4I.mjs`, plus live `getEdges()` results.
The fixture's edge 18 has Mermaid ID suffix `_2`, explicitly exercising the
separation between linkStyle ordinal and generated ID. `inspect-edges.mjs`
rechecks live metadata during verification.

Coverage: four strokes; open/point/circle/cross and the three same-kind double
heads supported by Mermaid's parser; all visible single-head combinations;
invisible label suppression and layout participation; parallel labels; chains;
Cartesian expansion of `&`; cycles and self-loops; marker ID collisions;
independent label path extents via Cairo; node boundary sampling on the actual
SVG primitives for all 14 existing shapes in TB/BT/LR/RL; deterministic output;
PNG decoding, scale, and byte comparison with a second raster of the returned
SVG; invalid-source failure and removal of stale output.

Geometry conventions: edge `points` are the clipped and marker-shortened routing
vertices before corner rounding (including protected label waypoints and endpoint
leads), in global SVG coordinates. SVG edges are paths containing only M/L/Q.
`corner_radii` contains the trim distance on each side of each routing vertex
(zero at endpoints/unrounded vertices). Each trim is at most 40% of either
adjacent segment. The SVG `data-points` and `data-corner-radii` mirror these
arrays; the Python output validator reconstructs every M/L/Q coordinate and
checks it against the actual SVG path, edge identity and ordinal. Consumers
needing the painted curve must use these trims, rather than joining `points`.
Quadratic intersections are tested using rectangle-boundary roots, and unsafe
rounding is reduced or disabled. Shortcut lookahead is six vertices, two passes;
self-loop routing vertices are preserved. Inflated obstacles allow boundary
contact with 10 px clearance from their geometric boxes (including stroke
allowance). Ancestor border bands allow transverse crossings but block parallel
travel; full title bands remain solid obstacles.
Visible bodies stop before markers; the markers extend to the node's geometric
outline. Marker size decreases on short terminal segments. Invisible edges
retain their hidden route and ordinal, with an empty label_box. The node outline
means the geometric shape boundary, excluding half the node stroke width.

Edges use straight segments and collision-checked quadratic corners; this does not add
other diagram types; theme support is specified below. Edge linkStyle support is limited to
literal stroke colors, numeric stroke-width and simple stroke-dasharray;
unsupported declarations fail explicitly. No browser is invoked by rendering or
the suite; removing the pre-existing Chromium packages from the image remains
outside the renderer changes described here.

## Node and subgraph verification

```sh
scripts/verify.sh subgraphs
```

This group checks both `flowchart` and `graph` with TB, TD, BT, RL, LR; real
label-path containment and edge-boundary contacts for all 14 shapes; modern
aliases; multiline/entity/empty labels; two nesting levels; real cluster bounds
and membership; title clearance; private directions; external connections;
cluster endpoints; ancestor/descendant links; empty/auto-ID clusters; cluster
self-loops; parallel crossing edges; deterministic SVG/PNG/layout and rerastering.
The shared geometry checks are in `verify_common.py`; `edges` remains a separate
regression group.

The product names map to Mermaid's installed parser types as follows:

| Product shape | Legacy parser type | Supported modern short name |
| --- | --- | --- |
| rect | square | rect |
| rounded | round | rounded |
| stadium | stadium | stadium |
| subroutine | subroutine | fr-rect |
| cylinder | cylinder | cyl |
| circle | circle | circle |
| diamond | diamond | diam |
| hexagon | hexagon | hex |
| parallelogram | lean_right | lean-r |
| parallelogram_alt | lean_left | lean-l |
| trapezoid | trapezoid | trap-b |
| trapezoid_alt | inv_trapezoid | trap-t |
| flag | odd (`A>label]`) | odd |
| double_circle | doublecircle | dbl-circ |

Registry aliases were read from Mermaid 12.3.0's installed
`dist/chunks/mermaid.core/chunk-AXFCVDMN.mjs` (`shapes.ts` source section).
Modern `@{shape: flag}` means **paper tape** (`waveRectangle`), not the legacy
asymmetric `odd` shape in this product's 14 shapes. It fails explicitly rather
than rendering the wrong shape. Collapsed groups and other group metadata are
also rejected; ordinary expanded subgraphs are supported.

### Cluster layout and direction

Dagre 3.1.3 has one graph-wide `rankdir`; direct edges on compound nodes can fail
with `Cannot set properties of undefined (setting 'rank')`. The implementation
therefore composes one ordinary Dagre graph per nesting level, with child
clusters sized from their actual content, real Pango title geometry, padding,
and reserved title bands. It uses the existing dependency, not a replacement.
Cross-level constraints are projected to the immediate children of their least
common enclosing graph; their actual edge bodies are then routed on a visibility
grid around leaf-node boxes, unrelated clusters, other edge labels and titles.

As documented by [Mermaid's official subgraph direction rules](https://mermaid.js.org/syntax/flowchart.html#direction-in-subgraphs),
a link from an interior member to the outside disables that cluster's private
direction and it inherits its parent's effective direction. A link to the cluster
itself preserves its private direction. The suite verifies the official examples,
including independent RL and BT children under a TB parent in an LR graph.

`subgraphs[].members` are **direct member IDs** from Mermaid's parsed source
membership, including immediate nested subgraph IDs. They are not a flattened
list of descendant leaves. A group referenced by an edge is not duplicated in
`nodes`. Group rectangles and title paths are emitted at final SVG coordinates,
with the exact same boxes in layout JSON.

Remaining scope limits: no collapsed clusters, paper-tape flag or arbitrary
additional Mermaid shapes; no curved routing. Theme/style support is specified in the section below. The hierarchical layout is not pixel-identical to
Mermaid's browser layout and does not optimize edge crossings globally. A route
which cannot avoid obstacles, or an ancestor/descendant edge label with no free
segment, produces an explicit engine error rather than a fabricated route or
box. The tests run offline in the existing local image; cross-architecture and
the separate production office sandbox have not been tested here.

## Theme and label verification

```sh
scripts/verify.sh theme-labels
```

`theme-source.mjs` reuses Mermaid 12.3.0's bundled `matchFrontMatter`, YAML
`load` with `JSON_SCHEMA`, and entity encoder/decoder. It checks that exact
Mermaid version because the bundle chunk paths are internal APIs. A version
update must review the adapter and rerun all three verification groups.
`mermaid.parse()` applies configuration before `getDiagramFromText()` obtains
flowchart metadata. No Mermaid browser renderer is called. No dependencies were
added: the YAML implementation and theme engine are already bundled in Mermaid.

Supported source configuration:

- Front matter `title`, `config.theme` (`default`, `base`, `dark`, `forest`,
  `neutral`), `config.themeVariables`, `config.fontFamily`, `config.fontSize`.
- Flowchart `htmlLabels` and `inheritDir` boolean flags. Text is always shaped
  into paths; htmlLabels never enables HTML or foreignObject output.
- Color theme variables: background; primary/secondary/tertiary Color,
  TextColor and BorderColor; textColor; lineColor; edgeLabelBackground;
  clusterBkg, clusterBorder, clusterTextColor; titleColor; nodeBkg, nodeBorder,
  nodeTextColor, mainBkg, defaultLinkColor, arrowheadColor; plus fontFamily,
  fontSize and darkMode. Derived palettes come from Mermaid's theme engine.
- With no explicit config, the earlier prototype's colors and 15 px Noto Sans
  default are preserved. Explicit theme config uses Mermaid's palette.

Style allowlist: `fill`, `stroke`, `stroke-width` (0..16 px),
`stroke-dasharray` (simple numeric lists or `none`), `color`, `font-family`,
`font-size` (1..256 px), `font-weight` (normal/bold or 100..1000 in hundreds),
`font-style` (normal/italic/oblique). Edge fill must be `none`. Colors must be
absolute literal named/hex/rgb(a)/hsl(a) values. Styles are emitted as validated
SVG attributes, never copied into a stylesheet. Geometry-changing styles such
as transforms, width, height, rx/ry, filters, and arbitrary CSS are rejected.
Unused class definitions are also validated.

Precedence follows the installed Mermaid style compiler: theme, default/node
classes, assigned classes in metadata order, then direct node `style`.
Subgraphs use their assigned classes and direct styles. Edges use assigned
classes, `linkStyle default`, then the ordinal-specific `linkStyle`. Marker
colors follow the styled edge stroke; an explicit theme arrowheadColor supplies
the default marker color. Stroke width does not scale markers or alter their
boundary offsets. Node/layout boxes describe geometric outlines, excluding
half of the painted stroke width, as in the earlier groups.

Font policy: every requested family must be installed in the image; missing
families fail explicitly and are never fetched. Generic `sans-serif`, `serif`,
`monospace` map explicitly to packaged Noto Sans, Noto Serif, Noto Sans Mono.
Pango may fall back for individual glyphs using local packaged fonts; actual
shaped run families are aggregated into `font_family_used`. Missing glyphs fail.
Empty/invisible labels do not add unused families to the report; an entirely
blank diagram reports the font Pango resolves for its blank labels.
`layout.font_px` is the diagram's global font size; class/style overrides are
measured individually before layout and their effective size/family are on each
SVG glyph path. Paths preserve the shaped font appearance without raster-time
font lookup. `label_box` measures those exact paths after translation.

Labels support all three `<br>` spellings, Mermaid named/decimal entities,
precomposed and combining Vietnamese characters. Literal HTML/Markdown formatting beyond the supported line breaks is
rejected; escaped markup entities remain inert label text. Titles use the same Pango path pipeline, get a
reserved top band, expand viewBox width when needed, and are rasterized in the
returned PNG. There is no extra title field in the fixed layout schema.

Configuration directives, themeCSS, external resources, links/callbacks,
image/icon nodes and unknown config/style properties fail explicitly. YAML uses
the bundled JSON schema, without executable tags. A pinned `mermaid-model.mjs`
adapter uses Mermaid's grammar and FlowDB with per-instance plain-text/br hooks,
keeping securityLevel=strict without calling DOMPurify or a DOM renderer. No
window/document is created. SVG uses explicit XML-escaped records; labels only
become Pango glyph paths, never markup. Output contains no active markup or
external references. The theme-labels suite verifies unsafe-source failures,
style priority, parallel ordinals, five official palettes, exact Pango paths,
font changes, title pixels, all 14 shapes under larger/styled fonts, and existing
invisible-edge behavior. The `edges` and `subgraphs` suites are also rerun.

## Python contract and CLI

The public entry point is `renderer/renderer.py` (installed as
`/app/renderer.py` in the container):

```python
from renderer import render, Rendered, DiagramSyntaxError, RendererError

result = render(source, scale=2, timeout=30)
assert isinstance(result.svg, str)
assert isinstance(result.png, bytes)
assert isinstance(result.layout, dict)
```

`DiagramSyntaxError.line_number` is 1-based in the original source, including
front matter, removed comments, blank lines, multiline labels and CRLF. It keeps
its ValueError base and adds category=source, kind=syntax, code=syntax.
`DiagramSourceError(RendererError)` represents other explicit source validation
failures (policy/style/config, unsupported diagram, requested font/glyph, known
source budgets). Catch it before RendererError, or inspect category. RendererError
has category=engine/kind=engine for dependency, timeout, caller/I/O, invalid output
and internal failures. Unknown failures stay engine errors.

CLI errors preserve exit 1 and JSON kind/line/code/message, add category, and use
kind=source for non-syntax source failures; source-policy line may be null. Codes
are details, not responsibility classifiers: limit/input/invalid_argument can
occur in different categories. Missing mandatory image fonts are engine dependency
failures; asking for an arbitrary uninstalled font is a source font error.
Argparse's invalid CLI usage still exits 2. See the complete
[error contract and migration notes](error-handling.md).

Examples inside the packaged image:

```sh
python3 /app/renderer.py /input.mmd --scale 2 --timeout 30 --output /output/run-001
python3 /app/renderer.py /input.mmd 2 30 --output /output/run-002
node /app/draw-probe.mjs /input.mmd 2 30 --output /output/run-003
```

The legacy Node CLI delegates to Python. Its `--internal` mode is a private
backend protocol, not an independently supervised public entry point. All
verification groups now render through the public Python CLI; metadata probes
still call the installed Mermaid parser directly.

Dockerfile now copies all five renderer files and sets
`ENTRYPOINT ["python3", "/app/renderer.py"]`. To exercise the packaged CLI:

```sh
bash scripts/render.sh tests/fixtures/legacy-input.mmd
```

`aiz-render-contract:local` was built offline by copying the current renderer
into the existing `aiz-render-probe:local` dependency image; no packages were
installed or downloaded. The full dependency build in the main Dockerfile was
not rerun. No new Python/npm dependencies were introduced for the contract.

### Isolation, deadlines and publication

Each `render()` creates its own private TemporaryDirectory, input snapshot,
logs, Node backend staging directory, font cache and raster file. Node calls
Pango for shaping and produces SVG/layout in that scratch. Python validates
those artifacts and rasterizes the **same SVG file** using rsvg-convert. It
returns the complete Rendered object only after the PNG dimensions and chunk
CRCs, SVG viewBox and layout schema all pass validation. No background worker or
renderer state is reused between calls.

A single monotonic deadline covers argument/input checks, Node startup,
parse/layout/Pango, rasterization, artifact reads and validation. Every child
stage receives the remaining time, not a fresh timeout. Node and rsvg run in
separate per-call process groups; all their descendants inherit the group.
Timeouts, failure, cancellation and normal leader exit trigger group cleanup.
The caller reaps the direct child plus any descendants adopted by it when it is
PID 1/subreaper, without changing application-wide signal/subreaper settings or
waiting on children from another concurrent call. This lifecycle uses POSIX
process groups and is tested in Linux containers; Windows is not supported.

The API writes no public files. CLI output directories are immutable: an
existing destination is an error and is never removed or overwritten. CLI
publication stages all three files on the destination filesystem, then atomically
renames the complete directory. Two renderer publishers racing to the same
name cannot replace or mix each other's completed sets. Without `--output`, the
CLI creates `<input-stem>-render-<uuid>` under the current directory and prints
its absolute path as JSON. The output parent must already exist. Retry after
failure may reuse the failed destination because no destination was published;
after success, choose another name. There is no special `/output/result` path.

### Fixed resource limits

| Item | Limit |
| --- | --- |
| Source | 50,000 characters and 256 KiB UTF-8 |
| Scale | finite number, 0 < scale <= 16; booleans rejected |
| Timeout | finite number, 0 < timeout <= 300 seconds; default 30 |
| SVG | 32 MiB |
| Layout JSON | 8 MiB |
| PNG | 64 MiB |
| Combined public output | 96 MiB |
| Raster | at most 16,384 per dimension and 100,000,000 pixels |
| Each stage's stdout/stderr | 1 MiB |

Mermaid's existing 500-edge parser limit also remains enforced. CLI input must
be a regular UTF-8 file; FIFO/device input is rejected. Output size/raster
limits fail before publishing anything. Scale/timeout have the same validation
in API and CLI. These bounds supplement the container/office sandbox limits;
the renderer does not relax them. As with any synchronous local API, OS
scheduling and final process/file cleanup can add a small amount of time beyond
the configured deadline; no successful result is returned after the API's
final deadline check.

### Contract verification

```sh
scripts/verify.sh contract
RENDERER_IMAGE=aiz-render-contract:local scripts/verify.sh contract
```

The suite checks API types and data correspondence, exact rerastering, CLI
options/positionals/default output, legacy Node CLI, exact syntax source lines,
unsupported diagrams, input/argument/output/raster limits, missing
Node/rsvg/npm/helper/Pango dependencies, concurrent API and CLI calls, racing
publishers, immutable earlier output, retry, shared deadlines across stages,
process-tree termination/reaping, scratch cleanup and corrupt raster output.
Fault injection uses only private test copies and Python-interpreted workers;
the container's noexec mount and default user/security settings are preserved.
Neither `--privileged`, sandbox disablement nor network access is used.

Still unverified: the separate production office sandbox integration and
cross-architecture execution. The packaged-entry-point smoke check and all
four verification groups run with `--network none` in the available local
Linux runtime.

## Runtime, version and supply-chain verification

The current default image for verification is `aiz-render-runtime:local`.

```sh
docker build --platform linux/arm64 -f deployment/renderer/Dockerfile -t aiz-render-runtime:arm64 -t aiz-render-runtime:local .
docker build --platform linux/amd64 -f deployment/renderer/Dockerfile -t aiz-render-runtime:amd64 .
scripts/verify.sh runtime
scripts/verify-runtime-matrix.sh
```

`verify-runtime-matrix.sh` builds both platforms, then runs each suite in two
fresh containers and compares SVG, PNG and layout hashes between them. Runtime
exit **3 means UNVERIFIED**, not PASS; failures return nonzero. The test runner
adds a read-only root, dropped capabilities, no-new-privileges, a 2 GiB memory
cgroup, and CPU/FD/file-size limits. It never disables Docker seccomp, enables
privileged mode or makes scratch executable to get a test to pass.

### Renderer identity

`from renderer import RENDERER_VERSION` and `python3 /app/renderer.py --version`
expose `aiz-mermaid-v1-sha256:<digest>`. SVG includes that exact identity as
`data-renderer-version`; the fixed layout schema remains unchanged. The identity
hash covers backend/controller source, package.json/lockfile and the two runtime
fingerprints: runtime-manifest.json plus build-identity.json (recipe, policy and
inventory-builder checksums generated at build time). Native source reads these
from AIZ_RENDERER_RUNTIME_DIR; it does not need Dockerfile/build tools inside src.
The manifest covers native
versions/architectures, Node components, tool hashes, all npm contents, all font
files and fontconfig contents **including active symlink targets**. Rendering
without either required environment fingerprint fails explicitly. Code changes change identity.

A cache key must include version, source and scale; source-specific theme/style
and render parameters are inputs, not separate fixed renderer versions. No
current timestamp, process ID, scratch path or random ID is added to SVG/PNG/
layout. CLI output directory names can be unique without entering artifacts.
Output environment is normalized to C.UTF-8/UTC and a fixed fontconfig path.
Node/Pango/rsvg children do not inherit NODE_OPTIONS, PYTHONPATH, LD_PRELOAD,
user fontconfig overrides, locale or timezone settings. Caller/interpreter
startup itself is still a trusted deployment boundary.

### Pinned build inputs and drift checks

- Base is the official multi-platform Node index digest in Dockerfile; both
  platform-specific manifest digests are recorded in runtime/build-policy.json.
- The Debian snapshot is fixed to `20261112T000000Z`, with exact root package
  versions. Only snapshot expiry is disabled; signatures, TLS verification and
  package SHA256 verification stay enabled. Since slim has no OS CA bundle,
  HTTPS roots are bootstrapped from the pinned Node binary's bundled CA roots.
- `npm ci --omit=dev --ignore-scripts` uses the committed lockfile: all 119 app
  resolutions have registry.npmjs.org tarballs and SHA512 integrity. No install
  hook or branch checkout is used. Chromium/chromium-sandbox were removed, not
  merely disabled during tests; browser npm packages are absent too.
- Full expected manifests for arm64 and amd64 are committed under
  `deployment/renderer/runtime/manifests/`. They record 164 Debian archive SHA256s,
  274 font files, 9,483 npm file entries and 265 npm package records including
  the base image's npm/Yarn distribution. Build inventory compares against the
  matching expected manifest and fails on drift.
- Installed code/dependencies remain root-owned; only the /app directory is
  owned by the runtime user. This avoids recursive ownership copy-up of the
  full dependency tree on each source-only rebuild.
- Original Debian copyright files and package license/notice files remain in
  the image. Read [the origin/license review](../deployment/renderer/runtime/THIRD_PARTY_REVIEW.md).
  An inventory is not a blanket permissive-license or distribution approval.

For an intentional dependency/font/base update, build an isolated candidate
context with the old expected manifests omitted, inspect the signed archive,
lockfile, font and license changes, then deliberately replace both expected
manifests after review. Never refresh expected hashes to conceal unexplained
build drift. A changed identity invalidates previous cached results.

This pins the installed environment and checks its tracked content. The
2026-11-16 [two-clean-build experiment](../evidence/verification/2026-11-16-r13-rebuild/report.json)
used the same frozen context and native ARM64 builder with --no-cache. Both
builds passed the manifest gate; the tracked runtime manifest and SVG/PNG/layout
for three fixtures were byte-identical. Full Docker image identities/layers
were different: image creation timestamps, installed package mtimes and apt/dpkg
log content varied. This is an observed packaging reproducibility gap, not a
renderer failure. No OCI archive serialization comparison or AMD64 clean-build
comparison was performed. Passing render hashes does not prove a byte-identical
image artifact. The release artifact scope must be explicit; no mentor approval
is required merely to run and record this experiment.

### Independent R2-related policy and exact coverage

`runtime_guard.py` installs an extra libseccomp filter in an unprivileged worker
before executing the real Python CLI. It permits only AF_UNIX for socket and
socketpair; rejects ptrace, legacy/new mount APIs, setns/unshare and namespace
flags on clone. clone3 returns ENOSYS so normal libc threads can fall back to
clone, whose flags are inspectable. The worker also lowers inherited rlimits.
Native probe tests check allowed UNIX vs denied IPv4/IPv6 socket creation, denied
ptrace/mount/unshare calls, actual FD exhaustion and a too-large sparse file.
Successful rendering runs under the same filter in fresh processes.

The cgroup memory.max value is checked at 2 GiB. RLIMIT_CPU is checked at 300
seconds **per process**, RLIMIT_NOFILE at 256, RLIMIT_FSIZE at 256 MiB. CPU/RAM
exhaustion is not deliberately induced; aggregate CPU accounting for the whole
process tree is not proven by RLIMIT_CPU. Resource configuration and tested
FD/file-size enforcement must not be described as an exhaustive resource-limit
stress proof.

The application rejects active HTML/resource tags, callbacks/links, image/icon
nodes, resource styles/config and executable YAML tags. Output validation only
accepts the SVG elements/attributes actually emitted, local resolved marker
references and unique IDs. Tests cover malicious inputs, a preload sentinel,
unsafe/corrupt SVG, deterministic independent outputs and changed-backend
identity. These are evidence for the tested cases, not a proof against all
possible parser/dependency vulnerabilities.

**Not reproduced:** office_sandbox.py's exact program registration/read/write
allowlists, Landlock path rules and full private seccomp allowlist. The
read-only container root is not Landlock, and `--network none` or Docker's
default seccomp is not R2.1 compliance. Source-side refusal to load a file is
also not a syscall-level read-path confinement proof. No private company code
was accessed or requested.

### Evidence and current infrastructure limitation

See [evidence/runtime/STATUS.json](../evidence/runtime/STATUS.json) and captured
logs. Earlier in this turn both clean platform builds succeeded; an earlier
arm64 revision passed the extra-filter/resource/source/determinism tests.
Under amd64 emulation the extra seccomp load returned EINVAL, so that restriction
was marked UNVERIFIED rather than passed. Native amd64 execution was not tested.

The subsequent **final-revision** matrix rebuild encountered Docker BuildKit
metadata I/O errors, then the engine became unavailable while host free space
was about 2.2 GiB. Final source changes (including non-recursive image ownership), committed-manifest build gates, the
completed amd64 rendering fallback checks and the full regression suite after
these operational changes must therefore remain **UNVERIFIED** until rerun on
an available Docker engine. Static Python/Node/shell/JSON checks passed; these
are not substitutes for runtime verification. Status evidence is deliberately
not overwritten with a PASS for an unexecuted final test.

## Full R1–R8 audit and regression entry point

```sh
bash scripts/verify.sh all > evidence/verification/all.log 2>&1
python3 scripts/summarize_verification.py evidence/verification/all.log \
  --output evidence/verification/latest.json
```

`all` runs edges, subgraphs, theme-labels, contract, runtime and regression in
separate containers, without stopping after the first failed group. A failure
returns nonzero; an unverified exit 3 never becomes a successful overall result.
The Bash 3.2 argv test also checks all-group dispatch and failure propagation.

`regression` starts with the committed 25-node/35-edge fixture and measures
three independent public CLI processes. It records wall time, a 10 ms sampled
sum of process-tree VmRSS (shared pages can be counted more than once and short
peaks missed), and SVG/PNG/layout hashes. It checks the measured artifacts'
geometry and exact rerastering, plus metadata insertion, large sources, nested
groups, long labels, cycles, configured limits, unsupported-type rejection and
R6.4 syntax examples. A parser accepting one of those prohibited examples is a
test failure to investigate, not a reason to silently change the expectation.
No mentor performance SLA is invented. Missing measurements remain null.

Read the complete [requirements audit](renderer-requirements-audit.md)
for the three-state table and its exact evidence/limitations. Historical
revision passes do not certify final source, private tests, actual office
sandbox integration, manual Office roundtrip or undecided v1 scope.

## Removing jsdom (2026-11-16)

`jsdom` and 26 exclusive transitive resolutions have been removed. `entities`
9.0.0, already present before this change, is retained directly for text reference
decoding. khroma validates supported absolute colors. There is no replacement
DOM shim. The parser adapter is tied to Mermaid 12.3.0 internal exports; an
upgrade must re-review those exports, preprocessing, text hooks and tests.

The metadata probes use the same pinned grammar adapter; independent geometry,
Pango and exact reraster checks remain. `verify_no_dom.mjs` checks that jsdom is
absent and window/document stay undefined through parse, plus text/color policy.
Contract fault injection now expects the actual missing Mermaid dependency
instead of the removed jsdom import. Assertions and runtime limits stay enabled.
