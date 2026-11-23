# Chỉnh sửa flowchart không giữ trạng thái

Mỗi lượt nhận file SVG/PNG gốc, đọc model hiện tại từ metadata, áp dụng lệnh trên
bản sao, chạy renderer và trả file mới. **Không dùng SQLite/database, registry,
cache model, history hoặc undo/redo.** `DiagramEditor` chỉ giữ cấu hình scale và
timeout. Có thể tạo instance mới cho từng request mà vẫn sửa tiếp được từ file.

Mã chỉnh sửa nằm trong `editing/`, độc lập với folder `renderer/` thuần render.
Build image renderer trước, rồi build `aiz-diagram-editor:local` qua
`deployment/editing/Dockerfile`. Các recipe/build files đều nằm ngoài source.
`EDITOR_IMAGE` chọn image chỉnh sửa; `RENDERER_IMAGE` vẫn chọn image render.

Renderer cũ vẫn là `render(source, scale, timeout) -> Rendered(svg,png,layout)`.
Không thay Dagre, Dijkstra, khoảng hở, nối tắt, bo góc, input Mermaid, CLI render
hay schema layout JSON. Lớp ngoài renderer nhúng JSON text vào SVG `<metadata>`
và PNG iTXt sau khi render thành công, đúng vai trò embedding của engine trong
requirements.md. Không thêm dependency; dùng thư viện chuẩn Python và parser/
validator màu/style hiện có.

## Vòng đời dữ liệu

1. Caller đưa file hiện tại vào request; lần đầu có thể khởi tạo từ `.mmd`.
2. Đọc metadata, kiểm tra schema/checksum, diagram_id, revision và model/source.
3. Chỉnh trên bản sao trong bộ nhớ. Batch thành công toàn bộ hoặc trả lỗi.
4. Render source mới qua pipeline hiện tại; chỉ sau khi thành công mới trả ảnh.
5. Chỉ file output mà caller yêu cầu được xuất. Scratch render và staging được
   dọn bằng TemporaryDirectory trên đường thành công lẫn đường lỗi.

File input không bị ghi đè. API không tự tạo thư mục hay file lưu lâu dài.
CLI xuất thư mục mới bằng rename nguyên bộ, giống cách công bố output renderer.
Sau khi giao file cho người dùng, hệ thống gọi có thể dọn thư mục output theo
vòng đời file đính kèm của nó. Không cần một database sơ đồ riêng. Giữ lại file
SVG/PNG gốc để sửa lần sau; screenshot hoặc công cụ xóa metadata sẽ mất model.

Các demo/evidence trong repo là artifact kiểm thử được tạo có chủ đích, không
phải trạng thái mà chương trình đọc lại ngầm ở request tiếp theo.

## Metadata hiện tại trong file

SVG có `<metadata id="mmdToDiagram-edit">`; PNG có iTXt keyword
`mmdToDiagram.edit`, UTF-8 không nén. Hai định dạng mang cùng payload:

- format/schema v1;
- diagram_id và revision của **file**;
- source Mermaid và model hiện tại (node/cạnh/nhóm, style, theme/config);
- ID cạnh ổn định và mặc định style cần cho đối tượng mới;
- preview flag và SHA256 checksum để phát hiện dữ liệu hỏng/thay đổi.

Không nhúng ảnh nhị phân, layout, lịch sử, phiên bản cũ, request cũ hoặc stack
undo/redo. Kích thước phụ thuộc sơ đồ hiện tại, giới hạn metadata 2 MiB; không
tích lũy theo số lượt chỉnh sửa. Metadata đọc được, không phải mã hóa hay chữ ký
xác thực. Checksum không thay thế phân quyền của hệ thống gọi.

Metadata được coi là input không tin cậy: schema chặt, key trùng/JSON không
hữu hạn, DTD/entity, checksum lỗi, PNG CRC lỗi và kích thước vượt giới hạn bị
từ chối. Model/style/source được kiểm tra bằng grammar và validator hiện tại.
Khi tạo output, luôn render lại source đã kiểm tra; không phát lại primitive SVG,
pixel PNG hay layout do người gửi cung cấp. SVG allowlist của renderer không
được nới lỏng để nhận metadata; embedding diễn ra ngoài hộp đen renderer.

## ID và revision theo file

Theo lựa chọn của người dùng, giữ `diagram_id` và `expected_revision` cho từng
file. Revision bắt đầu từ 1, apply thành công tăng 1. Sai ID/revision trả lỗi rõ.
Hai request cùng nhận file revision 1 có thể trả hai nhánh revision 2 độc lập.
**Không có server head, global lock hay kiểm tra bản mới nhất trên toàn hệ
thống.** Caller chọn đúng file kết quả của lượt trước để sửa tiếp.

Node/subgraph giữ ID từ Mermaid. ID cạnh tường minh duy nhất được giữ; cạnh
ẩn danh được cấp UUID một lần khi init và mang theo metadata. Không dùng nhãn
hoặc ordinal làm ID lâu dài. Bảng manifest ánh xạ edge_id sang ordinal trong
revision hiện tại; layout.json vẫn giữ hợp đồng cũ.

## API Python

Chạy trong runtime đã đóng gói, hoặc môi trường đầy đủ dependency với cả hai thư mục
renderer và editing trên PYTHONPATH:

```python
from pathlib import Path
from diagram_edit import DiagramEditor

editor = DiagramEditor(scale=1)  # không có store_path
first = editor.create_diagram(Path('/work/source.mmd').read_text(), 'orders')

current_png = first['rendered']['png']
edge_id = first['state']['edges'][0]['id']

# Instance mới vẫn hoạt động: toàn bộ đầu vào cần thiết nằm trong current_png.
second = DiagramEditor(scale=1).insert_node_on_edge(
    current_png, 'orders', 1, edge_id,
    'Kiểm tra bổ sung', shape='diamond', fill_color='rgba(255,220,128,0.8)'
)
next_png = second['rendered']['png']
next_svg = second['rendered']['svg']
assert second['revision'] == 2

# Dùng file PNG hoặc SVG từ kết quả cho request tiếp theo.
third = DiagramEditor(scale=1).update_node_label(
    next_svg, 'orders', 2, second['results'][0]['node_id'], 'Duyệt yêu cầu'
)
```

Mỗi lệnh chỉnh sửa nhận các tham số đầu:
`(artifact, diagram_id, expected_revision, …)`.
`artifact` là PNG bytes, SVG bytes hoặc SVG string; không phải đường dẫn DB.

| Hàm | Tham số còn lại |
| --- | --- |
| `add_node` | `label, shape='rect', fill_color=None, subgraph_id=None` |
| `delete_node` | `node_id` |
| `update_node_label` | `node_id, label` |
| `update_node_shape` | `node_id, shape` |
| `update_node_color` | `node_id, fill_color` |
| `add_edge` | `source_id, target_id, label='', line_style=None` |
| `delete_edge` | `edge_id` |
| `update_edge_label` | `edge_id, label` |
| `update_edge_line_style` | `edge_id, line_style` |
| `add_subgraph` | `label, node_ids, parent_subgraph_id=None` |
| `rename_subgraph` | `subgraph_id, label` |
| `move_node_to_subgraph` | `node_id, target_subgraph_id` (`None` = cấp ngoài) |
| `delete_subgraph` | `subgraph_id, mode` (bắt buộc ungroup/delete_contents) |
| `insert_node_on_edge` | `edge_id, label, shape='rect', fill_color=None, subgraph_id=None` |
| `delete_node_and_reconnect` | `node_id, connections=None` |
| `apply_diagram_edit` / `preview_diagram_edit` | `operations` |
| `get_diagram` | không có; đọc model/manifest, không trả lại graphics upload |
| `export_diagram` | `destination` mới; render lại source trước khi xuất |

`create_diagram(source, diagram_id=None)` là bước khởi tạo riêng, trả revision 1.
Không có `undo_diagram_edit`, `redo_diagram_edit`, `update_edge_endpoints`.

Response tạo/sửa/preview có diagram_id, revision, source, state, results,
manifest, changes và `rendered={svg:str,png:bytes,layout:dict}`. `changes` liệt kê
added/updated/deleted, gồm các thay đổi gián tiếp; `layout_changed` liệt kê những
ID còn tồn tại bị đổi hình học. Response không được lưu ngầm vào đâu.

## Batch và preview

```python
preview = editor.preview_diagram_edit(current_png, 'orders', 1, [
    {'op':'add_node', 'label':'Bước mới', 'as':'step'},
    {'op':'delete_edge', 'edge_id':edge_id},
    {'op':'add_edge', 'source_id':'A', 'target_id':'$step', 'label':'Có'},
    {'op':'add_edge', 'source_id':'$step', 'target_id':'B'},
])
```

Alias `as` tùy chọn cho lệnh tạo; `$alias` chỉ phân giải trong trường ID, không
đổi nhãn. ID mới trong preview là tạm, apply lại operations lên file gốc sẽ
cấp ID mới. Preview giữ revision/base_revision, không thay file gốc. File preview
được đánh dấu trong metadata và bị từ chối làm đầu vào chỉnh sửa/export tiếp;
chỉ file từ init/apply là phiên bản để sửa tiếp. Không lưu lịch sử.

## Các quy tắc được giữ

- 14 shape renderer hỗ trợ; `flag` API là legacy odd, không phải paper tape.
- Kiểu nét normal/dotted/thick/invisible; đổi nét giữ nhãn, marker, màu/font và
  minlen, thay width/dash override theo nét mới. Marker của cạnh bị ẩn vẫn nằm
  trong model hiện tại để khôi phục khi chuyển sang nét nhìn thấy.
- Màu dạng hàm RGB/RGBA/HSL được chuẩn hóa sang hex 8-bit theo lựa chọn đã chốt;
  URL/giá trị không hợp lệ bị từ chối.
- Xóa node xóa mọi cạnh incident. Ungroup đưa node/nhóm con trực tiếp lên cha;
  delete_contents xóa toàn bộ cây con. Cả hai liệt kê cạnh nối chính khung nhóm.
- Chèn bước là một batch xóa cạnh cũ, tạo node và hai cạnh; nhãn cũ sang cạnh
  thứ nhất, cạnh thứ hai không nhãn; giữ kiểu/paint/marker/minlen.
- Xóa-nối lại chỉ tự suy ra với đúng một cạnh vào, một cạnh ra và không mâu
  thuẫn nhãn/style. Nhiều nhánh/self-loop cần connections rõ từng cặp đầu
  vào–đầu ra. Cạnh tạo tường minh dùng label/line_style được chỉ rõ và marker point.
- Renderer vẫn từ chối sơ đồ rỗng: thao tác xóa cuối cùng trả lỗi, không có
  artifact mới. Nhóm rỗng vẫn được hỗ trợ như trước.
- Không có cache layout. Apply/preview render cả source gốc lẫn source mới để
  báo cáo thay đổi hình học; export render lại source. Mỗi lần render có timeout
  riêng theo pipeline cũ; timeout không phải deadline chung cho cả batch.

## CLI không database

Build hai phần từ project root (runtime phải sẵn sàng trước):

```bash
docker build -f deployment/renderer/Dockerfile -t aiz-render-runtime:local .
docker build -f deployment/editing/Dockerfile -t aiz-diagram-editor:local .
```

Các script và ví dụ nằm ngoài folder renderer, không cần mang theo khi chỉ tích
hợp hộp đen render. CLI đã cài vẫn giữ `/app/renderer.py` và `/app/diagram_edit.py`
trong hai image tương ứng. Các lệnh chỉnh sửa dưới đây giữ nguyên cú pháp:

```bash
mkdir -p artifacts/stateless-demo
cp test1.mmd artifacts/stateless-demo/source.mmd

bash scripts/edit.sh artifacts/stateless-demo init \
  --source /work/source.mmd --diagram-id demo --output /work/r1 --scale 1

bash scripts/edit.sh artifacts/stateless-demo get \
  --input /work/r1/diagram.png --diagram-id demo --expected-revision 1

# operations.json là JSON array chứa ID từ kết quả init/get.
bash scripts/edit.sh artifacts/stateless-demo apply \
  --input /work/r1/diagram.png --diagram-id demo --expected-revision 1 \
  --operations /work/operations.json --output /work/r2 --scale 1
```

`preview` có cùng tham số như apply, dùng output mới. `export` đọc một file gốc
có metadata và render lại ra thư mục mới. `apply/preview` đọc stdin nếu không
có --operations. CLI trả JSON thông tin/model/changes và đường dẫn output; ảnh
nằm trong các file output, không in PNG base64 ra stdout.

Bỏ hoàn toàn `--store`, undo và redo. Các lỗi này không còn được hỗ trợ. API
cũng bỏ đối số store_path; caller phải đưa artifact ở mỗi request.

Output chỉ gồm các file được yêu cầu: diagram.svg, diagram.png, layout.json,
source.mmd và edit-manifest.json. Không tạo database/journal/lock/history. Wrapper
vẫn chạy offline, read-only root, tmpfs /tmp và cùng giới hạn Docker; chỉ mount
thư mục input/output của request. Thư mục output đã tồn tại sẽ bị từ chối.

File chỉ có hình từ CLI renderer cũ chưa có metadata chỉnh sửa: cần init từ
source .mmd một lần. Metadata bị mất/hỏng hoặc file không đúng phiên bản thì báo
invalid_artifact; không dùng OCR hoặc đoán cấu trúc từ đường vẽ.

## Kiểm chứng

```bash
bash scripts/verify-editing.sh
bash scripts/verify.sh all
```

Suite mới kiểm tra SVG↔PNG qua instance mới, pixels không đổi sau nhúng metadata,
ID cạnh, mọi thao tác còn lại, atomic batch, preview, bỏ history, revision theo
file, metadata hỏng/giả, input bị giữ nguyên và dọn scratch cả khi lỗi. Các bộ
renderer cũ vẫn giữ nguyên assertion và entry point.
