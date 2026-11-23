# Đối chiếu riêng chế độ ELK — 23/11/2026

Chuẩn đối chiếu: [requirements.md](requirements.md), vẫn là bản nháp, không
được sửa trong thay đổi này. Chế độ được kiểm tra là `--layout elk`; mặc định
công khai vẫn là Dagre. Đây là hai luồng trong cùng renderer, chọn qua CLI/API.

Cập nhật theo lựa chọn của người dùng: cả hai engine luôn giữ đường gốc,
không rút ngắn hoặc bo góc, không cần `--raw-edges`. Hai hàm postprocessing và
helper chỉ phục vụ chúng đã được loại bỏ; flag/API cũ được giữ để tương thích.
Kiểm tra thay đổi
mặc định này được lưu riêng trong
[evidence](../evidence/verification/2026-11-23-elk-original-default/).
Bảng full matrix bên dưới là snapshot trước thay đổi mặc định này.

## Thay đổi và phạm vi

- Chỉ giữ Dagre và ELK; loại bỏ layout/router lai, switch nội bộ để reroute,
  script so sánh ba chế độ và các test chỉ phục vụ chế độ đã bỏ.
- Dagre giữ hình học node/nhóm; Dijkstra thêm trạng thái trục đi vào, chi phí
  góc gấp, đoạn trùng/gần dây khác, giao cắt và làn phụ. Các cạnh nội bộ đơn
  giản vẫn dùng routing của Dagre như trước.
- ELK dùng `elkjs@0.12.1`, `layered`, orthogonal, cây nhóm thật. Adapter không
  gọi `dagre.layout` hoặc Dijkstra. Các phần parse, Pango, style, SVG và raster
  được tái sử dụng; graphlib chỉ làm kho dữ liệu dùng chung.
- Khai báo vùng tiêu đề với ELK. Nếu cạnh cắt chữ tiêu đề, yêu cầu port bên
  hông cho các cạnh qua biên đó và chạy lại ELK, tối đa bốn lượt. Mỗi lượt
  nhận bản sao sạch; kiểm tra endpoint thô khớp node và hệ tọa độ parent.
- Clipping vào shape giữ trục của port ELK, tránh đổi một đường thẳng an toàn
  thành đường chéo qua node khác. Cả hai engine luôn giữ routing gốc;
  `corner_radii` được giữ trong schema với toàn bộ giá trị bằng 0.
- `--elk-spacing` vẫn được hỗ trợ; không đổi kích thước node/font.

## Kết quả kiểm chứng

Log và fingerprint của lượt cuối nằm trong
[thư mục evidence](../evidence/verification/2026-11-23-dagre-elk/).
`report.json` ghi exit code, image ID, renderer identity và các nhóm đã chạy.
Các log có tên `development`/`ports-all` là lịch sử sửa lỗi, không phải bằng
chứng PASS cho revision cuối.

ARM64: sáu nhóm edges, subgraphs, theme-labels, contract, runtime và regression
đều PASS/0. Có test render khi cả `dagre.layout` và Dijkstra bị vô hiệu hóa;
có test raw port giữ trục trên 14 shape và mẫu 55 node/63 cạnh. Các test package,
API/CLI Dagre mặc định và argv Bash cũng PASS.
[Report cuối](../evidence/verification/2026-11-23-dagre-elk/report.json) ghi
image IDs, renderer identities, fingerprint source và exit code từng nhóm.

AMD64 chạy bằng giả lập trên máy ARM64: seccomp bổ sung trả
`seccomp_load failed: 22`, nên kiểm tra đó là **chưa kiểm chứng**, không phải
PASS. Năm nhóm edges, subgraphs, theme-labels, contract và regression đều
PASS/0; các phép thử checksum/offline/attack/determinism của runtime cũng
chạy đạt, nhưng tổng nhóm runtime là UNVERIFIED/3 vì thiếu bộ lọc bổ sung.
Không có nhóm FAIL ở lượt cuối; tổng AMD64 là exit 3, ARM64 là exit 0.

Ảnh đã mở kiểm tra:
[compare.png](../artifacts/dagre-elk-clean/compare.png),
[dagre.svg](../artifacts/dagre-elk-clean/dagre.svg),
[elk.svg](../artifacts/dagre-elk-clean/elk.svg).
Cùng source `chat_flow.mmd`, giữ đủ 55 node, 9 nhóm và 63 cạnh.

| Trên cùng mẫu, raw edges, scale 1 | Dagre trước | Dagre cải tiến | ELK |
| --- | ---: | ---: | ---: |
| Cặp dây trùng đoạn ít nhất 8 đơn vị | 7 | 1 | 0 |
| Tổng chiều dài trùng theo từng cặp | 2219.42 | 10.67 | 0 |
| Số góc gấp trên polyline | 184 | 92 | 98 |
| Kích thước SVG | 3211.44 × 7478 | 3211.44 × 7478 | 2510.33 × 4676 |

[Routing report](../evidence/verification/2026-11-23-dagre-elk/routing-quality.json)
khẳng định node/nhóm Dagre bằng nhau trước và sau, thay đổi nằm ở đường đi.
ELK gọn hơn trên ảnh này nhưng đổi thứ tự các nhóm (Core nằm phía dưới) và vẫn
có dây vòng ngoài dài; Dagre còn khoảng trắng lớn bên phải phần đầu. Không
thấy mất/cắt node hoặc nhãn trong ảnh, và các test geometry/ID đã đối chiếu.

| Rule | Phép kiểm tra / kết luận có thể rút ra |
| --- | --- |
| R1.1 | Kiểm kê origin trong image; ELKjs ở tổ chức `kieler`, nguồn gốc Kiel University/Eclipse ELK. Chưa hoàn tất đánh giá quá trình xử lý lỗ hổng và toàn bộ upstream bắc cầu. Các dependency namespace cá nhân vẫn là điểm cần đối chiếu chính sách R1.1. |
| R1.2 | License/notice thực tế được giữ và inventory hash. ELK không phải MIT; xem [review](../deployment/renderer/runtime/THIRD_PARTY_REVIEW.md) và [EPL-2.0 chính thức](https://www.eclipse.org/legal/epl/epl-v20.html). Chưa có source-offer/corresponding-source bundle và chưa chốt nghĩa vụ on-prem: chưa kết luận đạt R1.2 toàn image. |
| R1.3 | `npm ci --ignore-scripts`, version/integrity trong lock, base digest, Debian snapshot và hai manifest gate. Không chạy lại hai clean build để chứng minh toàn image byte-identical; gap tái lập image từ audit cũ vẫn còn. |
| R1.4 | Build image ARM64/AMD64 và ghi rõ kiến trúc chạy test. Chạy AMD64 trên Docker Desktop ARM64 là giả lập, không xác nhận máy AMD64 thật hoặc image python-vm công ty. |
| R1.5 | Backend/lock/runtime fingerprint tham gia `RENDERER_VERSION`; test sửa backend phải đổi identity. |
| R2.1 | Docker không mạng, root read-only, USER node, cap-drop, no-new-privileges; 2 GiB, CPU 300 s, FD 256, file 256 MiB. Runtime test thêm seccomp AF_UNIX/ptrace/mount/namespace và probe FD/file size. Chưa phải PROGRAMS/PROGRAM_READ/Landlock/office_sandbox.py thực tế. |
| R2.2–R2.3 | Test source/code/URL/font/image/style injection và SVG validator: script, foreignObject, handler, tham chiếu ngoài, ID trùng phải bị từ chối. Không có browser/jsdom. |
| R2.4–R2.5 | API/CLI timeout toàn lượt, kill cây tiến trình, dọn scratch, retry, gọi đồng thời, công bố output atomic; không có worker giữ qua request. Không thực sự tiêu hết 300 CPU s hoặc 2 GiB để thử exhaustion. |
| R3.1–R3.2 | Render thật với `--network none`; font và npm/fontconfig/tool hash đối chiếu inventory trong image. |
| R4.1 | 14 shape, flowchart/graph và 5 hướng, nhóm lồng/hướng riêng, cạnh xuyên nhóm/compound/ancestor/self-loop/parallel, các đầu/nét/nhãn cạnh, style/class/linkStyle, theme/YAML/title/br/entity/tiếng Việt. Test va chạm dựa trên path SVG thực, không chỉ data-attribute. |
| R4.2–R4.3 | Chỉ flowchart được triển khai. Sequence/ER/pie trả lỗi rõ ràng; danh sách ngoài flowchart cho v1 vẫn chưa chốt. Không coi test từ chối là đã hỗ trợ. |
| R5.1–R5.4 | API `Rendered(svg,png,layout)`, viewBox, ID/members/ordinal, Cairo extents của hình/chữ, marker contacts, đường thực và layout; PNG so byte với lần raster độc lập của chính SVG, scale và metadata insertion. |
| R6.1–R6.4 | Parse chặt, dòng 1-based kể cả YAML/comment/multiline/CRLF; taxonomy source/syntax/engine, fault injection; từ khóa end, ngoặc sai và nhãn không quote. |
| R7.1–R7.3 | Pango outline/glyph thật, Noto Sans/Serif, NFC/NFD tiếng Việt, nhãn nhiều dòng/cỡ lớn, fallback theo glyph; font thiếu/glyph thiếu báo lỗi và font thực tế được trả về. |
| R8.1–R8.3 | Cùng engine/options/source/runtime: render nhiều tiến trình phải giống byte, ID ổn định, identity đổi theo code/môi trường. Cache consumer riêng chưa kiểm chứng; khi chọn engine/options phải đưa chúng cùng scale vào cache key. |

## Giới hạn nghiệm thu còn lại

Chưa có 53 test private, bộ fixture native cũ, tích hợp `checks.py`/embed/Office
và image python-vm/office_sandbox.py công ty trong workspace. Chưa kiểm tra
roundtrip thủ công Word, LibreOffice, WPS và Google Docs/Slides. Vì vậy kết quả
test công khai không phải chứng nhận đáp ứng toàn bộ mục 6 của requirements.

Benchmark 25 node/35 cạnh ghi wall time và peak RSS lấy mẫu trong report, không
tự đặt SLA. Các số đo dùng để quan sát, không phải bằng chứng RAM/CPU exhaustion.
Ba lượt ARM64 của revision cuối mất 0,876 / 0,766 / 0,818 giây; peak RSS cây
tiến trình lấy mẫu lần lượt khoảng 157,7 / 154,1 / 162,7 MiB.

## Chạy lại

```bash
docker build -f deployment/renderer/Dockerfile -t aiz-render-runtime:dagre-elk .
VERIFY_LAYOUT=elk RENDERER_IMAGE=aiz-render-runtime:dagre-elk bash scripts/verify.sh all

docker run --rm --network none --read-only --memory 2g \
  -v "$PWD:/workspace:ro" -v "$PWD/artifacts:/output:rw" \
  --tmpfs /tmp:rw,mode=1777 --entrypoint python3 \
  aiz-render-runtime:dagre-elk /workspace/scripts/compare_layouts.py \
  /workspace/chat_flow.mmd --raw-edges --output /output/dagre-elk-new
```

Ảnh so sánh dùng cùng font/theme/kích thước node, 1 đơn vị SVG = 1 pixel;
không co giãn riêng hai sơ đồ. Dagre bên trái, ELK bên phải. ELK khác ở cả
bố cục lẫn routing. Số cặp trùng đoạn không đồng nghĩa số giao cắt, và không
bảo đảm mọi source đều không trùng dây.
