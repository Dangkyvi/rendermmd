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
