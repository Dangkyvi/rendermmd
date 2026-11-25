# Lớp chỉnh sửa riêng

Folder này chỉ có source; Dockerfile/build nằm ngoài trong deployment/.
Component này nằm ngoài hộp đen renderer. Nó sửa model theo ID, tạo Mermaid,
gọi renderer và nhúng trạng thái hiện tại vào metadata SVG/PNG. Không database,
không undo/redo, không giữ model giữa các request.

Build renderer trước, rồi build editor từ project root:

```bash
docker build -f deployment/renderer/Dockerfile -t aiz-render-runtime:local .
docker build -f deployment/editing/Dockerfile -t aiz-diagram-editor:local .
```

Có thể chọn core image khác:

```bash
docker build -f deployment/editing/Dockerfile \
  --build-arg RENDERER_IMAGE=aiz-render-runtime:custom -t aiz-diagram-editor:local .
```

`deployment/editing/Dockerfile` chỉ thêm editor lên renderer image; không cài lại dependency.
Image editor vẫn có renderer để xuất ảnh, còn image renderer không chứa editor.
Script `scripts/edit.sh` và `scripts/verify-editing.sh` mặc định dùng image editor;
`EDITOR_IMAGE` chọn image riêng. Biến RENDERER_IMAGE cũ vẫn được nhận nếu không
có EDITOR_IMAGE, để giữ tương thích các lệnh chọn image đã dùng trước đây.

Khi chạy source repo, hai folder renderer/ và editing/ là các component cùng
cấp; bridge dùng grammar/validator/dependency Node của renderer, không có một
bộ npm riêng cho editor. Có thể import `editing.diagram_edit.DiagramEditor` từ
source root hoặc chạy `python3 editing/diagram_edit.py --help`.

Xem docs/diagram-editing.md của repo phát triển để biết API, ID/revision theo file,
preview, các lệnh JSON và test thủ công. Tài liệu đó không cần cho renderer chạy.

Native deployment dùng cùng AIZ_RENDERER_RUNTIME_DIR của renderer, trỏ tới hai
fingerprint JSON read-only ngoài source. Xem deployment/README.md.

## Sửa đường đi một cạnh

API giữ nguyên node, nhóm, cạnh khác và cổng nối. Tìm đường mới trước,
sau đó đặt nhãn trên đoạn trống của đường đó; nhãn cạnh được chọn có thể di chuyển.
Thay polyline và vị trí nhãn tương ứng; không chạy layout toàn hình để thay tọa độ.
Editor dựng lại bản gốc từ source để kiểm chứng, sau đó áp dụng đường đã sửa
lên SVG mới và raster lại PNG. Không phát lại SVG người dùng tải lên.

```python
editor = DiagramEditor(scale=1, timeout=60)
result = editor.reroute_edge(
    artifact, diagram_id, expected_revision,
    edge_id="e_12", avoid_overlap_with=["e_15"],
)
```

Cũng dùng được qua `preview_diagram_edit` / `apply_diagram_edit` hoặc CLI
`preview` / `apply` với operations:

```json
[{"op":"reroute_edge","edge_id":"e_12","avoid_overlap_with":["e_15"]}]
```

Lấy ID từ `manifest.edges`, không lấy ordinal làm ID. `prefer_side` tạm được
nhận để tương thích (left/right/top/bottom) nhưng không còn ảnh hưởng đường
đi; không tạo guide hay waypoint ép ghé mép khung. Dijkstra tự tìm khoảng
trống, tránh node/tiêu đề/nhãn khác. Lưới có các làn cách dây ngang/dọc hiện
có 12/24 đơn vị để khuyến khích các dây chạy song song gọn thành bó, không
phạt việc song song đủ xa. Quá sát/trùng vẫn bị phạt; khoảng cách là ưu tiên
mềm khi không gian bị hạn chế. `avoid_overlap_with` cấm chạy dọc làn của các
cạnh được chỉ định, vẫn cho phép cắt ngang. Đoạn dẫn chung ngay tại cùng đầu
nối có thể còn trùng vì cổng hiện tại được giữ nguyên.

Không tìm được đường với cổng hiện tại, hoặc đường mới không đủ chỗ đặt nhãn
→ lỗi `routing_failed`, không
âm thầm di chuyển node hoặc mở rộng khung. Không hỗ trợ cạnh invisible.
Tối đa 50 lệnh reroute/batch; không trộn lệnh sửa model và reroute trong batch.

Artifact chưa sửa đường vẫn là metadata v1. Khi sửa đường, metadata v2 thêm
`geometry = {renderer_version, base_layout, routes}`; khi nhãn di chuyển, thêm
`positions` (rỗng nếu node không đổi) và `labels` để giữ vị trí nhãn qua export. Không lưu constraints,
lịch sử hay ảnh gốc. Mỗi lần đọc/xuất lại kiểm tra bố cục gốc và đường số học;
checksum không phải chữ ký tin cậy. Renderer/bố cục gốc thay đổi →
`layout_incompatible`. Preview không tăng revision; apply tăng một revision.

Trong phiên bản đầu, các thao tác sửa model trên artifact v2 bị từ chối với
`geometry_edit_conflict`, để không tự làm mất đường đã chỉnh. Có thể tiếp tục
reroute các cạnh khác hoặc export SVG/PNG; muốn đổi model thì tạo bản mới từ
source. Có thể tiếp tục bố trí lại vùng như phần dưới.

Kiểm tra: `bash scripts/verify-editing.sh` (gồm kiểm tra cũ và
`tests/verify_edge_edit.py` cho sửa đường). Image mới đã build cục bộ:
`aiz-diagram-editor:edge-routing`; chọn bằng biến `EDITOR_IMAGE` khi dùng script.

## Bố trí lại một vùng

```python
result = editor.relayout_region(
    artifact, diagram_id, expected_revision,
    node_ids=["A", "B", "C"], goal="compact", direction="TB",
)
```

Operations JSON dùng với `preview` / `apply`:

```json
[{"op":"relayout_region","node_ids":["A","B","C"],"goal":"compact","direction":"TB","preserve_boundary":true}]
```

- Nhận 2..150 node lá có cùng nhóm cha trực tiếp. Khung nhóm, node ngoài
  vùng, kích thước chữ/node và viewport giữ nguyên. Không nhận ID subgraph.
- `direction`: LR/RL/TB/TD/BT. `goal`: compact (khoảng cách nhỏ hơn) hoặc
  reduce_crossings (khoảng cách rộng hơn dành cho dây). Dagre tính một bố cục
  cục bộ; node độc lập được đóng gói thành hàng. Không bảo đảm mọi chỉ số
  thẩm mỹ đều giảm. Không đổi thuật toán layout mặc định của renderer.
- `bounds` tùy chọn là `[x,y,width,height]` trong hệ tọa độ layout. Bỏ trống
  thì dùng vùng nội dung khung cha/viewport làm giới hạn. `preserve_boundary`
  hiện chỉ hỗ trợ true. Engine tìm chỗ trống khả thi cho **cùng một bố cục**,
  có xét node, cạnh bị khóa và khả năng đi dây; không render nhiều phương án
  để xếp hạng. Tối đa 128 vị trí đặt được kiểm tra trong một lần gọi.
- Mọi cạnh nối node được chọn (kể cả cạnh ra ngoài) được đi dây lại; đầu nối
  thuộc node ngoài giữ nguyên. Nhãn cạnh liên quan có thể đổi vị trí, nhãn và
  đường của cạnh không liên quan giữ nguyên. Cổng trên node được di chuyển
  được tịnh tiến theo node, không đổi hình dạng/marker.
- Thiếu diện tích: `region_too_small` kèm required_size/available_size.
  Không tìm được chỗ đặt và đi dây an toàn: `region_blocked`. Không thay đổi
  artifact đầu vào khi lỗi; muốn thêm chỗ phải chọn bounds/phạm vi khác.
- Metadata v2 bổ sung `positions` (tọa độ node tuyệt đối) và `labels` (tọa độ
  nhãn cạnh) bên cạnh routes/base_layout. Không lưu ràng buộc khóa lâu dài.
  Mọi lần get/export đều dựng lại từ source, kiểm tra vị trí và các đường.
  Các node/nhãn trong SVG được tịnh tiến bằng transform của nhóm g; các box
  trong layout JSON và data-* vẫn là tọa độ tuyệt đối sau chỉnh sửa.
- Có thể ghép reroute_edge và relayout_region trong batch hình học, tiếp tục
  chỉnh vùng hoặc cạnh trên artifact đã chỉnh. Chưa hỗ trợ trộn với sửa model,
  thay khung nhóm hoặc chọn node thuộc nhiều nhóm cha trực tiếp.

`bash scripts/verify-editing.sh` gồm `tests/verify_region_edit.py`.

Image cục bộ chứa cả hai API: `aiz-diagram-editor:region-edit`.
Dùng `EDITOR_IMAGE=aiz-diagram-editor:region-edit bash scripts/verify-editing.sh`
để kiểm tra image này.

Bản đi dây gom bó dùng runtime `aiz-render-runtime:parallel-lanes`. Editor cần
build trên runtime này để có cùng router/đặt nhãn; image đã đóng gói là
`aiz-diagram-editor:region-edit` và `aiz-diagram-editor:edge-routing`.
