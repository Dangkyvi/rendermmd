# Yêu cầu cho renderer diagram thay thế mmdr

Trạng thái: bản nháp, chưa chốt. Tài liệu này chỉ nói renderer **phải làm được gì**, không chọn công nghệ hay cách làm.

## 1. Bối cảnh

- Engine diagram cũ nằm ở `filezkit/diagrams/` và đã bị gỡ ở commit `f9c5fa6`, ngày 29/10/2026. Lý do ghi trong commit: `mmdr`
  được build từ repo cá nhân của bên thứ ba (mermaid-rs-renderer) và parse Mermaid do model viết ngay trong sandbox.
- Trước `mmdr`, engine từng dùng Mermaid.js 11.17.2 (xem `PAST_VERSIONS` trong `renderer.py` cũ). README của `mmdr` ghi rõ
  "never fall back to a browser or invent an empty layout".
- Phần lớn engine cũ không phụ thuộc renderer và vẫn chạy được: model, edit, theme, embed, format. Chạy test cũ trên máy
  không có `mmdr`: 288 passed, 53 skipped, 1 failed. Các test skipped là do thiếu `mmdr` hoặc LibreOffice; test failed là do
  thiếu `fc-match`. **Renderer là mảnh duy nhất phải thay.**

## 2. Vai trò của renderer trong engine

Renderer là một hộp đen, có đúng một việc:

- **Vào:** một source Mermaid (đã được `theme.py` thêm front matter và classDef), tỉ lệ raster, thời hạn.
- **Ra:** `Rendered(svg, png, layout)`, hoặc một lỗi cú pháp có số dòng, hoặc một lỗi engine.

Mọi thứ khác do các phần khác của engine lo: parse, sửa, theme, kiểm tra nhãn, nhúng source vào SVG/PNG/DOCX/PPTX, cache.
Vì vậy renderer mới phải giữ đúng định dạng dữ liệu này để `checks.py`, `office.py` và `embed.py` dùng lại được mà không phải sửa.

## 3. Yêu cầu bắt buộc

### R1. Nguồn gốc và chuỗi cung ứng

- R1.1 Có nguồn đáng tin: do một tổ chức hoặc cộng đồng duy trì, có lịch sử phát hành và xử lý lỗ hổng. Nếu không có lựa chọn
  như vậy thì team tự viết và tự duy trì. Không dùng repo cá nhân của bên thứ ba.
- R1.2 License cho phép dùng thương mại và phân phối on-prem (MIT, Apache-2.0, BSD hoặc tương đương).
- R1.3 Ghim chính xác phiên bản và checksum. Build tái lập được. Không kéo nhánh động lúc build.
- R1.4 Đóng gói được vào image của python-vm cho cả linux/amd64 và linux/arm64.
- R1.5 Có quy trình cập nhật: đổi phiên bản thì đổi định danh renderer (xem R8).

### R2. An toàn khi nhận input do model viết

- R2.1 Chạy được dưới chế độ `exec` của `app/office_sandbox.py`, như `pandoc` và `tesseract`:
  - là một chương trình cố định trong `PROGRAMS`;
  - chỉ đọc `PROGRAM_READ` cộng các đường dẫn riêng của nó; chỉ ghi vào scratch riêng;
  - dưới Landlock và seccomp: chỉ socket AF_UNIX, không ptrace, không mount, không tạo namespace;
  - trong `PROGRAM_LIMITS`: bộ nhớ 2 GiB, CPU 300 s, 256 file đang mở, file tối đa 256 MiB.

  Hệ quả: một trình duyệt headless cần tạo namespace cho sandbox của nó thì nhiều khả năng không chạy được trong chế độ này.
- R2.2 Không thực thi bất kỳ đoạn mã nào đến từ source: không JavaScript, không `click`/`href` mở được thứ gì, không nạp ảnh,
  font hay file nào được source tham chiếu tới.
- R2.3 SVG đầu ra không có `<script>`, `<foreignObject>`, event handler hay tham chiếu ra ngoài.
- R2.4 Mỗi lần render có giới hạn thời gian. Engine cũ cho 30 s mỗi diagram, timeout thì báo lỗi rõ ràng.
- R2.5 Không giữ tiến trình hay trạng thái nào giữa hai lần render.

### R3. Chạy offline

- R3.1 Không cần mạng lúc chạy, kể cả để tải font, theme hay cập nhật.
- R3.2 Font nằm sẵn trong image.

### R4. Phạm vi source phải render được

- R4.1 Flowchart đầy đủ, vì đây là loại diagram sửa được theo cấu trúc:
  - header `flowchart`/`graph` với mọi hướng TB, TD, BT, RL, LR;
  - subgraph lồng nhau, có `direction` riêng;
  - 14 shape mà `edit.py` sinh ra: rect, rounded, stadium, subroutine, cylinder, circle, diamond, hexagon, parallelogram,
    parallelogram_alt, trapezoid, trapezoid_alt, flag, double_circle;
  - mũi tên: các kiểu nét solid, dotted, thick, invisible; các đầu arrow, none, circle, cross, both; có nhãn; nhiều mũi tên
    song song giữa hai node; chuỗi `A --> B --> C`; nhóm `&`; chu trình;
  - `classDef`, `class`, `:::class`, `style`, `linkStyle` theo số thứ tự;
  - front matter YAML: `title`, `config.theme`, `config.themeVariables` (gồm `fontFamily` và cỡ chữ);
  - nhãn có `<br>`, entity (`#quot;`, `#amp;`…) và tiếng Việt có dấu.
- R4.2 Các loại diagram khác chỉ cần render, không cần sửa theo cấu trúc. **Cần chốt danh sách cho v1** (xem mục 7).
- R4.3 Gặp loại diagram không hỗ trợ thì báo lỗi rõ ràng, không render ra hình rỗng.

### R5. Đầu ra

- R5.1 SVG, có `viewBox`, cho phép engine chèn `<metadata>` để giấu source.
- R5.2 PNG được raster từ chính cây SVG đó, theo `scale` (mặc định 2x).
- R5.3 Layout JSON đúng định dạng `checks.py` đang đọc. Toạ độ tính theo đơn vị của SVG; hộp có dạng `[x, y, w, h]`:

  ```json
  {
    "width": 0, "height": 0,
    "nodes":     [{"id": "A", "box": [0,0,0,0], "label_box": [0,0,0,0]}],
    "edges":     [{"source": "A", "target": "B", "ordinal": 0, "points": [[0,0]], "label_box": [0,0,0,0]}],
    "subgraphs": [{"id": "phase1", "box": [0,0,0,0], "label_box": [0,0,0,0], "members": ["A", "B"]}],
    "font_px": 15,
    "font_family_used": "Noto Sans"
  }
  ```

  - `id` của node và subgraph trùng với id trong Mermaid source.
  - `ordinal` của mũi tên theo thứ tự trong source, khớp với số thứ tự mà `linkStyle` dùng.
  - `points` là đường đi thật của mũi tên, lấy mẫu sau khi áp transform của SVG.
  - Các hộp phải **đo trên hình đã vẽ**, không ước lượng.
- R5.4 Cả ba đầu ra phải khớp nhau: hình trong PNG đúng là hình trong SVG, toạ độ trong layout đúng là toạ độ trong SVG.

### R6. Lỗi cú pháp

- R6.1 Parse chặt chẽ. Source sai thì trả lỗi, không cố đoán rồi vẽ.
- R6.2 Lỗi có số dòng (1-based) và thông báo người đọc hiểu được. Engine chuyển nó thành `DiagramSyntaxError` để model tự sửa.
- R6.3 Phân biệt được lỗi do source (model sửa được) với lỗi do renderer (model không sửa được).
- R6.4 Bắt được các lỗi model hay mắc: ký tự đặc biệt hoặc ngoặc trong nhãn không có nháy, dùng từ khoá `end` làm id hay
  tên class, ngoặc mở và đóng không khớp.

### R7. Font và tiếng Việt

- R7.1 Shape chữ thật (dấu chồng, dấu kết hợp) với Noto Sans. Không có ô vuông hay dấu bị lệch.
- R7.2 Đo độ rộng chữ thật để kích thước node vừa nhãn.
- R7.3 Báo về font thực sự đã dùng (`font_family_used`), để engine phát hiện khi phải dùng font thay thế.

### R8. Tính xác định và định danh

- R8.1 Cùng source và cùng phiên bản renderer thì ra cùng kết quả byte-for-byte, để cache theo hash hoạt động.
- R8.2 id trong SVG ổn định giữa các lần render.
- R8.3 Có một chuỗi định danh phiên bản (giống `RENDERER_VERSION`). Engine đưa nó vào hash và vào source nhúng trong file.

## 4. Nên có

- Bố cục dễ đọc: hạn chế mũi tên cắt nhau và cắt qua node, subgraph không đè lên nhau.
- Hỗ trợ `themeCSS` cơ bản, ví dụ bo góc node.
- Render diagram 25 node và 35 mũi tên (ngưỡng `too_dense` của `checks.py`) trong vài giây. **Chưa có số đo, cần chốt.**
- Thông báo lỗi có kèm gợi ý sửa.

## 5. Không yêu cầu

- Bố cục giống hệt Mermaid.js. README của `mmdr` đã chấp nhận rằng bố cục và cách xuống dòng khác Mermaid.js.
- Render trong trình duyệt của người dùng hay chỉnh sửa tương tác.
- Đọc diagram từ ảnh.
- Tương thích với ảnh mà renderer cũ đã nhúng (tuỳ quyết định ở mục 7).

## 6. Tiêu chí nghiệm thu

1. 53 test cũ đang bị skip (phần lớn vì thiếu `mmdr`, một test vì thiếu LibreOffice) chạy pass trong image có renderer mới
   và LibreOffice, sau khi chỉnh lại chỗ test kiểm tra định danh `mmdr`. Các test này nằm trong `test_diagram_render.py`,
   `test_diagram_docx.py`, `test_diagram_pptx.py`, `test_diagram_checks.py`, `test_diagram_theme.py`, `test_diagram_embed.py`.
2. Render đúng các fixture cũ trong `tests/filez/data/diagrams/native/`: approval-sunset, bidding-slate, entities, parallel,
   sequence, subgraph, title. Fixture `invalid.mmd` phải trả lỗi cú pháp có số dòng.
3. Chạy trong image python-vm, dưới chế độ `exec` của `office_sandbox.py`, với `--network none`, trên cả amd64 và arm64.
4. Qua review bảo mật về nguồn gốc mã, license và hành vi với input độc hại: source cực lớn, lồng sâu, vòng lặp, nhãn rất dài.
5. Một người mở thử file DOCX/PPTX có diagram trong Word, LibreOffice, WPS và Google Docs/Slides, theo checklist mà
   `samples.py roundtrip` cũ đã dùng.

## 7. Cần chốt

1. Ngoài flowchart, v1 render những loại nào? Đề xuất: sequence và ER.
2. Ngưỡng thời gian render và bộ nhớ cụ thể là bao nhiêu?
3. Có cần đọc lại ảnh diagram mà renderer cũ đã nhúng trong file của người dùng không, hay coi đó là ảnh thường?
4. Ai duy trì renderer về lâu dài nếu team tự viết hoặc tự fork?
