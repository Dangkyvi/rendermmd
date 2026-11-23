# Luồng chạy renderer

[SVG để zoom](../artifacts/flows/renderer-execution/diagram.svg) ·
[PNG](../artifacts/flows/renderer-execution/diagram.png) ·
[Source Mermaid](../tests/fixtures/renderer-execution-flow.mmd)

Sơ đồ mô tả code đang có trong workspace: người dùng/engine cung cấp **source
Mermaid**, không phải gửi văn bản tự nhiên đến một dịch vụ sinh source.

1. **CLI:** `scripts/render.sh` kiểm tra đường dẫn và Docker, mount input read-only,
   chạy image offline có giới hạn. `renderer.py main()` đọc file UTF-8, chuẩn hóa
   scale/timeout và gọi API render nội bộ. Mặc định scale=2, timeout=30 giây.
2. **Python API:** caller gọi `render(source, scale, timeout)` trong môi trường
   đã đóng gói. Nhánh này đi trực tiếp vào controller, không gọi shell script.
   Đây là API Python, không phải một HTTP endpoint được triển khai trong repo.
3. **Controller:** kiểm tra đầu vào/dependencies/identity, tạo scratch riêng;
   gọi Node backend dưới deadline chung và theo dõi subprocess/output limits.
4. **Backend:** `theme-source.mjs` xử lý YAML/theme/style và policy;
   `mermaid-model.mjs` dùng grammar/FlowDB của Mermaid để tạo model flowchart,
   với text hooks riêng, không tạo DOM/window/document. `text_geometry.py` dùng Pango/Cairo shape/đo nhãn trước
   layout. Dagre và `subgraph-layout.mjs` bố trí node/nhóm, rồi router tạo các
   đường cạnh/marker và backend xuất SVG/layout.
5. **Kiểm tra và raster:** Python kiểm tra layout/SVG rồi `rsvg-convert` raster
   chính SVG đó thành PNG. Python kiểm tra PNG và tổng dung lượng, dọn scratch,
   kiểm tra deadline rồi trả `Rendered(svg, png, layout)`.
6. **Trả kết quả:** API trả object cho caller; CLI ghi ba file qua staging và
   atomic rename, in đường dẫn output ra stdout. Output có sẵn không bị ghi đè.

Các mũi tên nét đứt minh họa những nhóm lỗi, không liệt kê mọi điểm có thể lỗi.
Syntax errors có line number; lỗi policy/source dùng DiagramSourceError và
category=source, lỗi môi trường/nội bộ có category=engine. CLI trả JSON stderr/exit 1
(với kind syntax/source/engine và code); lỗi dùng sai cú pháp argparse có thể exit 2, và wrapper
có thể trả lỗi input/Docker trước khi renderer chạy. Timeout dừng cây subprocess;
scratch đã tạo được dọn khi thoát. Deadline của CLI còn bao gồm đọc input và
công bố kết quả, còn API không có bước công bố file.

Luồng cache, nhúng source vào Office và tích hợp `office_sandbox.py`/python-vm
không nằm trong sơ đồ vì các consumer private không có trong workspace.

## Tự chạy lại

```bash
bash scripts/render.sh tests/fixtures/renderer-execution-flow.mmd
```

Script tạo output mới trong `artifacts/renders/` và in đường dẫn ra terminal.

## Code đối chiếu

- [Wrapper Docker](../scripts/render.sh)
- [Python controller/API/CLI và công bố file](../renderer/renderer.py)
- [Node backend](../renderer/backend/draw-probe.mjs)
- [Theme/source policy](../renderer/backend/theme-source.mjs)
- [Shaping và đo chữ](../renderer/backend/text_geometry.py)
- [Bố trí subgraph](../renderer/backend/subgraph-layout.mjs)
