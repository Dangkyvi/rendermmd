# Mermaid diagram renderer

Renderer flowchart chạy offline trong Docker, xuất SVG, PNG và layout JSON.
Không dùng jsdom hoặc tạo `window`/`document`: adapter lấy model từ grammar Mermaid,
đo chữ bằng Pango và tạo SVG trực tiếp.

## Cấu trúc thư mục

```text
renderer/             Mã nguồn thuần render, không kèm Docker/runtime build
  backend/            Parser/layout/SVG/shaping nội bộ
editing/              Mã chỉnh sửa theo ID và metadata stateless
deployment/           Dockerfile, build policy, inventory và runtime manifests
scripts/              Lệnh render, kiểm thử và tổng hợp evidence
tests/               Các nhóm kiểm thử và helper
  fixtures/           Source Mermaid mẫu (.mmd)
docs/                 Yêu cầu, audit, điều tra dependency và hướng dẫn kỹ thuật
evidence/             Log/report/hash của các lần kiểm chứng, gồm lịch sử
artifacts/            Hình và layout đã xuất
  showcase/           Hình tổng hợp 14 shape và các kiểu cạnh
  legacy-probe/       Output thử nghiệm cũ được giữ lại
  renders/            Output mới từ scripts/render.sh
```

## Build image

Chạy từ thư mục gốc project; mở Docker Desktop trước:

```bash
docker info
docker build --platform linux/arm64 \
  -f deployment/renderer/Dockerfile \
  -t aiz-render-runtime:arm64 -t aiz-render-runtime:local .
```

Máy AMD64 dùng `--platform linux/amd64` và tag tương ứng. Kết quả kiểm chứng
ARM64 không xác nhận AMD64; xem audit để biết phạm vi đã chạy.

Để tích hợp chỉ chức năng render vào repo khác, xem
[renderer/README.md](renderer/README.md). Copy source vẫn cần chuẩn bị runtime
và đăng ký tool/sandbox của công ty; folder không tự cung cấp các dependency hệ
thống hay tự đăng ký agent. Các file build nằm trong
[deployment/](deployment/README.md), tách khỏi source.

Nếu cần thêm chỉnh sửa theo ID, build component ngoài renderer:

```bash
docker build -f deployment/editing/Dockerfile -t aiz-diagram-editor:local .
```

Xem [editing/README.md](editing/README.md) và
[hướng dẫn chỉnh sửa](docs/diagram-editing.md). Image renderer thuần không có CLI
chỉnh sửa; scripts/edit.sh vẫn giữ cú pháp cũ và mặc định gọi image editor.

## Xuất hình để xem

```bash
bash scripts/render.sh tests/fixtures/showcase-all-shapes-edges.mmd
```

Lệnh in đường dẫn output mới trong `artifacts/renders/`, gồm `diagram.svg`,
`diagram.png` và `layout.json`. Muốn chọn nơi lưu:

```bash
bash scripts/render.sh tests/fixtures/showcase-all-shapes-edges.mmd artifacts/renders/my-diagram
open artifacts/renders/my-diagram/diagram.png
```

Nếu sơ đồ lớn vượt giới hạn PNG ở scale mặc định 2x, giảm scale (không nới giới hạn):

```bash
bash scripts/render.sh test.mmd --scale 1
```

Thư mục output phải chưa tồn tại. Muốn chạy lại, chọn tên mới. SVG phù hợp để
zoom hình dài. Có thể sửa file `.mmd` rồi render lại; khi sửa code renderer,
build lại image trước. `RENDERER_IMAGE` và `RENDERER_PLATFORM` dùng để chọn image/arch.
Các giới hạn Docker và entry point renderer được giữ trong script.

## Kiểm thử

```bash
python3 tests/verify_shell_args.py --bash /bin/bash
bash scripts/verify.sh all
# Hoặc một nhóm: edges, subgraphs, theme-labels, contract, runtime, regression
bash scripts/verify.sh edges
```

Xem [hướng dẫn kỹ thuật](docs/development.md) để ghi log và tổng hợp evidence.

## Tài liệu và bằng chứng

- [Sơ đồ luồng chạy từ input đến output](docs/execution-flow.md)
- [Phân loại lỗi source/engine và cách bắt exception](docs/error-handling.md)
- [Yêu cầu R1–R8](docs/requirements.md)
- [Audit hiện tại và phạm vi còn thiếu](docs/renderer-requirements-audit.md)
- [Điều tra R1.1](docs/renderer-r1.1-investigation.md)
- [Cách đọc evidence và lịch sử đường dẫn](evidence/README.md)
- [Báo cáo verification mới nhất](evidence/verification/latest.json)

Các tên cũ `sandbox-probe/`, `scripts/fixtures/`, `scripts/*-evidence/` đã được
chuyển vào các thư mục trên. Log/hash snapshot cũ giữ nguyên nội dung để bảo toàn lịch sử.
