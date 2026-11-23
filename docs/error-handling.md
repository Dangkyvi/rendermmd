# Phân loại lỗi renderer — R6.3

API và CLI phân biệt trách nhiệm sửa lỗi bằng **category**, không suy từ nội dung
thông báo hoặc chỉ từ code. Không đổi Rendered hoặc schema layout JSON.

| category | kind | Python exception | Hướng xử lý |
| --- | --- | --- | --- |
| source | syntax | DiagramSyntaxError | Sửa cú pháp source theo line_number 1-based |
| source | source | DiagramSourceError | Sửa nội dung, cấu hình hoặc yêu cầu của diagram |
| engine | engine | RendererError | Xử lý môi trường/caller/backend; không tự yêu cầu model sửa MMD |

`DiagramSyntaxError` vẫn là ValueError, không phải RendererError.
`DiagramSourceError` là subclass của RendererError để các handler cũ vẫn bắt được;
consumer mới cần bắt subclass này **trước** RendererError hoặc đọc `category`.
Cả ba class đều có `kind`, `category`, `code`; syntax có `line_number`, source
policy có `line_number=None` khi không có vị trí chính xác, không đoán số dòng.

```python
from renderer import render, DiagramSyntaxError, DiagramSourceError, RendererError

try:
    result = render(source)
except (DiagramSyntaxError, DiagramSourceError) as error:
    # Trả thông tin cho engine/model sửa source.
    source_problem = (error.code, getattr(error, 'line_number', None), str(error))
except RendererError as error:
    # Xử lý lỗi hệ thống/caller; không tự sửa source để che lỗi backend.
    engine_problem = (error.code, str(error))
```

## CLI

CLI vẫn trả exit 1 khi renderer thất bại, không công bố bộ file dở dang. JSON
stderr giữ các field `kind`, `line`, `code`, `message`, thêm `category` và giá trị
`kind="source"`. Consumer CLI cần chấp nhận giá trị mới này.

```json
{
  "kind": "source",
  "category": "source",
  "line": null,
  "code": "font",
  "message": "Font chưa được đóng gói: AIZ Missing Font. Không tải font ngoài."
}
```

Argparse dùng exit 2 cho cú pháp gọi CLI không hợp lệ, không phải một lỗi MMD.
Shell wrapper còn có thể lỗi input/Docker trước khi Python CLI chạy.

## Các ranh giới

| Nguồn lỗi | Phân loại |
| --- | --- |
| Grammar Mermaid hoặc YAML sai cú pháp | source / syntax |
| Style/config/theme/markup bị policy từ chối | source / source_policy |
| Sequence/ER hoặc header chưa hỗ trợ | source / unsupported |
| Yêu cầu font chưa đóng gói, glyph không có | source / font hoặc glyph |
| Mâu thuẫn parent/cycle trong cây subgraph | source / source_structure |
| Flowchart không có node/subgraph | source / input |
| Source vượt ký tự/byte, quá số cạnh, diagram vượt kích thước raster hữu hạn | source / limit |
| Source chứa NUL/Unicode không encode được; file không phải UTF-8 | source / invalid_argument hoặc invalid_source |
| Sai type tham số API, scale/timeout không hợp lệ | engine / invalid_argument |
| Không đọc được file input, thư mục output đã có | engine / input hoặc output_exists |
| Thiếu Node/rsvg/Pango hoặc font Noto bắt buộc của image | engine / dependency |
| Timeout, log/output vượt budget, nội bộ layout lỗi hoặc không tìm được route | engine / timeout, limit hoặc engine |
| Backend trả JSON/geometry/SVG/PNG hỏng; protocol lỗi không hợp lệ | engine / engine hoặc output |
| Màu palette do theme engine sinh sai sau khi input đã validate | engine / output |
| Lỗi khác không có nguồn rõ ràng | engine |

Một style chứa URL có thể bị grammar từ chối ngay và trở thành **syntax**;
style đúng grammar nhưng ngoài allowlist trở thành **source**. Cả hai có category
source. Code `input`, `limit`, `invalid_argument` có thể xuất hiện ở hai category:
consumer phải dùng category/kind, không dùng code đơn lẻ để quyết định ai sửa.

Font yêu cầu không có khác với font Noto bắt buộc trong image bị thiếu: trường
hợp đầu thay source được; trường hợp sau là lỗi đóng gói/môi trường. Lỗi layout
cho source hợp lệ và timeout không bị đổi thành lỗi source chỉ vì có thể thử
viết lại diagram đơn giản hơn. Lỗi không rõ nguyên nhân giữ ở engine.

## Implementation và kiểm tra

- [Public exceptions, đọc diagnostic và CLI](../renderer/renderer.py)
- [Source policy errors](../renderer/backend/theme-source.mjs)
- [Grammar boundary và giới hạn cạnh](../renderer/backend/mermaid-model.mjs)
- [Truyền lỗi shaping và lỗi backend](../renderer/backend/draw-probe.mjs)
- [Font/glyph vs native dependency](../renderer/backend/text_geometry.py)
- [Test API/CLI và fault injection](../tests/verify_error_taxonomy.py)

Chạy thông qua nhóm contract, dưới các giới hạn Docker hiện có:

```bash
bash scripts/verify.sh contract
```

Chưa kiểm chứng consumer private công ty đã xử lý class/field mới. Không có thay
đổi engine private, dependency, runtime permissions hoặc resource limits.
