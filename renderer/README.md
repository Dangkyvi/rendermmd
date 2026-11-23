# Hộp đen render Mermaid — source

Folder này chỉ chứa mã chạy và khai báo dependency Node:

```text
renderer/
  __init__.py             API khi import như Python package
  renderer.py             Python API/CLI chính
  runtime_version.py      Định danh code và môi trường thực tế
  backend/                Parser/theme/layout/SVG/shaping
  package.json
  package-lock.json
  README.md
```

Không chứa Dockerfile, runtime build tools/manifests, chỉnh sửa theo ID,
metadata chỉnh sửa, database, lịch sử hay cache diagram. Dockerfile/policy/
inventory được tách ra deployment/. Editing là component ngoài source này.

## Dùng trong src công ty

Copy renderer/ vào source root, chuẩn bị runtime, rồi gọi:

```python
from renderer import render, RendererError, DiagramSyntaxError
result = render('flowchart TB\nA --> B\n', scale=1, timeout=30)
# result.svg: str; result.png: bytes; result.layout: dict
```

Công ty vẫn cần Python, Node và các package đã ghim, PyGObject/PyCairo/Pango,
fonts Noto và rsvg-convert. node_modules do môi trường cung cấp phải ở vị trí
Node resolve được qua cây thư mục, ví dụ node_modules ở cha của src/renderer/.
Không cài package hay tải font lúc xử lý source.

Hai fingerprint môi trường được tạo ở bước build và đặt ngoài source:

```text
/opt/diagram-runtime/
  runtime-manifest.json   Phiên bản/checksum dependency, fonts, tools
  build-identity.json     Fingerprint recipe, policy và inventory builder
```

Cấu hình trước khi import/chạy code:

```bash
export AIZ_RENDERER_RUNTIME_DIR=/opt/diagram-runtime
python3 /company/src/renderer/renderer.py input.mmd --output new-output --scale 1
```

runtime_version.py cần hai JSON này để giữ định danh R8; nó không đọc Dockerfile
hay toàn bộ folder runtime từ src. Thiếu fingerprint/dependency thì báo lỗi,
không bỏ kiểm tra và không giả lập renderer version. Các JSON chỉ mô tả môi
trường cài đặt, không chứa diagram/model/trạng thái người dùng.

API: Mermaid + scale + timeout → Rendered(svg,png,layout) hoặc lỗi cú pháp/source/
engine. CLI không ghi đè output đã tồn tại, dọn scratch mỗi lượt. Không có
background worker/state giữ giữa các request. Legacy Node CLI trong source là
`node backend/draw-probe.mjs ...` khi môi trường đã chuẩn bị đầy đủ.

## ELK thử nghiệm

Dagre vẫn là mặc định. Chọn engine bằng keyword mới hoặc CLI; các positional
argument scale/timeout và schema Rendered/layout cũ giữ nguyên:

```python
result = render(source, scale=1, timeout=60, layout="elk")
```

```bash
python3 renderer/renderer.py input.mmd --output new-output --layout elk --scale 1
RENDERER_IMAGE=aiz-render-runtime:elk-experimental bash scripts/render.sh \
  tests/fixtures/subgraphs.mmd artifacts/elk-new --layout elk --scale 1
```

`elkjs` được ghim trong package-lock. Sau khi cài/build, cả hai engine chạy
offline, không cần browser/Chrome. Backend chỉ import ELK khi được chọn.
SVG có `data-layout-engine` và `data-edge-routing` để xác minh engine thực tế.

Thêm `--raw-edges` cho Python/Node CLI, `scripts/render.sh` hoặc
`scripts/compare_layouts.py` để bỏ qua cả `shortcutRoute` và `roundedRoute`.
API tương ứng là `render(source, layout="elk", raw_edges=True)`. Hai hàm vẫn
được giữ và chạy như cũ khi không bật flag. Chế độ này nối các routing point
bằng đoạn thẳng M/L, không rút gọn, không bo góc; vẫn căn endpoint vào biên
shape và chừa chỗ cho mũi tên. Với Dagre, các cạnh xuyên nhóm vẫn qua router
`orthogonalRoute` hiện có; với ELK, routing point do ELK cung cấp.


Luồng dùng chung: `mermaid-model.mjs` parse source → `text_geometry.py` đo
Pango và tạo outline chữ → `draw-probe.mjs` tính kích thước shape/node/nhãn →
engine layout → clipping theo shape, shortcut/bo góc, marker, style, SVG →
Python kiểm tra output rồi dùng librsvg xuất PNG.
Dagre gọi `dagre.layout` hoặc `layoutSubgraphs` cho cây nhóm; ELK gọi
`elk-layout.mjs` với thuật toán `layered`, cây children thật và
[`INCLUDE_CHILDREN`](https://eclipse.dev/elk/reference/options/org-eclipse-elk-hierarchyHandling.html)
cho các cạnh xuyên cấp. Nhóm không có cạnh xuyên ranh giới dùng
`SEPARATE_CHILDREN` để giữ hướng riêng. Tọa độ node được cộng qua các parent,
còn tọa độ cạnh/nhãn được cộng theo container mà ELK trả về. ID gốc và đối
tượng geometry/style được giữ trong graph hiện tại.

ELK dùng **routing trực giao của ELK** và vị trí nhãn của ELK, rồi dùng chung
phần vẽ cạnh hiện tại. Ảnh khác nhau ở cả bố cục lẫn routing. Đây là chế độ
thử nghiệm; không bảo đảm tối ưu khoảng trắng hoặc tránh mọi giao cắt. Mermaid
edge length/minlen hiện chỉ ảnh hưởng luồng Dagre; ELK dùng spacing cố định.

Build và tạo lại ba ảnh so sánh, với Dagre bên trái, ELK bên phải, cùng tỉ lệ
1 đơn vị SVG = 1 pixel (output phải là thư mục mới):

```bash
docker build -f deployment/renderer/Dockerfile -t aiz-render-runtime:elk-experimental .
docker run --rm --network none --read-only --memory 2g \
  --cap-drop ALL --security-opt no-new-privileges \
  -v "$PWD:/workspace:ro" -v "$PWD/artifacts:/output:rw" \
  --tmpfs /tmp:rw,mode=1777 --entrypoint python3 \
  aiz-render-runtime:elk-experimental /workspace/scripts/compare_layouts.py \
  /workspace/tests/fixtures/subgraphs.mmd --output /output/layout-comparison-new
```

Script xuất `dagre.svg`, `elk.svg`, `compare.png`, layout JSON và báo cáo kiểm
tra. Nó render thêm lượt mặc định và so sánh bằng tuyệt đối với Dagre explicit;
đối chiếu kích thước node, font, outline/style chữ, ID/cạnh và cây nhóm trước
khi ghép PNG bằng Cairo, không co giãn riêng từng sơ đồ.

Kiểm tra bộ chuyển đổi ELK: `node tests/verify_elk.mjs` sau `cd renderer && npm ci`.

## Build Docker là một lựa chọn triển khai

Các recipe được giữ ngoài code, chạy từ project root:

```bash
docker build -f deployment/renderer/Dockerfile -t aiz-render-runtime:local .
```

Trong image, metadata và dependency đã được chuẩn bị ở /app, không cần thêm
AIZ_RENDERER_RUNTIME_DIR. Entry point vẫn là /app/renderer.py, legacy Node CLI
là /app/draw-probe.mjs. Runtime chạy offline; build có thể cần tải dependency.

Nếu công ty đã có python-vm/runtime phù hợp, không cần đưa Dockerfile vào src;
CI/provisioning của công ty cấp dependency và hai fingerprint JSON. Chi tiết ở
deployment/README.md của repo phát triển. Source renderer không cần file tài
liệu đó để chạy.

Việc đăng ký PROGRAMS/PROGRAM_READ/scratch, Landlock/seccomp và resource limits
cho office_sandbox.py thuộc hệ thống công ty; package không tự đăng ký agent.
Tích hợp private đó chưa được kiểm chứng trong repo này. Copy folder là mang
mã nguồn, không tự cài binary/runtime hoặc tự cấu hình sandbox.
