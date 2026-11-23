# Đối chiếu renderer với R1–R8

Đối chiếu riêng chế độ ELK sau khi chỉ giữ hai luồng Dagre/ELK, ngày
23/11/2026: [elk-requirements-audit.md](elk-requirements-audit.md).
Các snapshot dưới đây là lịch sử; không dùng chúng để xác nhận revision mới.

Nguồn chuẩn: [requirements.md](requirements.md),
đang ở trạng thái bản nháp/chưa chốt. Bảng này không tự thay đổi tiêu chí hay
quyết định danh sách diagram v1.

## Cách đọc trạng thái

- **đã kiểm chứng**: có phép kiểm tra đã chạy hoặc bằng chứng tĩnh trực tiếp,
  với phạm vi ghi ngay trên dòng. Kiểm chứng một khai báo/file không đồng nghĩa
  với kiểm chứng toàn bộ hành vi runtime.
- **chưa kiểm chứng**: chưa chạy được, thiếu dữ liệu/tích hợp/quyết định, hoặc
  chỉ có kết quả của revision trước. Có test trong repo không đủ để ghi PASS.
- **chưa đáp ứng**: có khoảng trống xác định được trong code/phân phối hiện tại.

## Snapshot hiện tại — raster 100MP, 16/11/2026

Theo yêu cầu người dùng, `MAX_RASTER_PIXELS` tăng từ 16.000.000 lên
100.000.000. Chiều tối đa 16384, RAM 2 GiB, timeout 30 s và container policy
không đổi. Không thêm dependency hoặc đổi backend. Renderer identity tự đổi
thành `aiz-mermaid-v1-sha256:7b19eda6f23278ee57aa4df5b7a7c9be6ba3d517152a820fe4754094384f7871`.

**Đã kiểm chứng:** `chat_flow.mmd` mặc định scale 2 xuất PNG 6423 × 14956
(96.062.388 pixel), exit 0; [render report](../evidence/verification/2026-11-16-raster100m/render-report.json).
Test biên chấp nhận 100MP, từ chối quá 100MP hoặc chiều quá 16384;
không bỏ assertion/fixture có sẵn.

Sáu nhóm edges, subgraphs, theme-labels, contract, runtime và regression đều
**PASS/0 trên ARM64**, tổng exit 0; Bash render argv PASS/0.
[Log](../evidence/verification/2026-11-16-raster100m/all.log),
[latest](../evidence/verification/2026-11-16-raster100m/latest.json),
[source hash](../evidence/verification/2026-11-16-raster100m/source.json).
ARM64 và AMD64 build/manifest gate exit 0; image/code/mount khớp
[identity](../evidence/verification/2026-11-16-raster100m/identity-check.json).
Image local/arm64/amd64 đã cập nhật theo
[active tags](../evidence/verification/2026-11-16-raster100m/active-image-tags.json).

Runtime AMD64, tích hợp công ty/Landlock/Office/private consumer vẫn **chưa kiểm chứng**;
SLA và quyết định mentor còn nguyên. Số đo benchmark mới được lưu trong latest,
không tự suy ra đạt SLA. Các phần R6.3/wrapper/rebuild dưới đây giữ làm lịch sử,
không dùng source hash/image cũ để xác nhận revision hiện tại.

Snapshot R6.3 bên dưới là lịch sử; xem snapshot raster 100MP ở trên.
**16/11/2026 — sửa R6.3, runtime ARM64 độc lập**.
Đã bổ sung `DiagramSourceError(RendererError)` và category source/engine. Syntax
vẫn là `DiagramSyntaxError` với kind=syntax, line 1-based. Source policy/style/config,
font yêu cầu không có, glyph và unsupported diagram được phân loại source;
dependency/timeout/I/O/output hỏng/lỗi nội bộ giữ engine. Lỗi không rõ nguồn giữ engine.
CLI thêm `category` và kind=source; consumer private cần kiểm tra việc nhận field/class mới.
[Hợp đồng lỗi](error-handling.md).

**49 ca taxonomy PASS** qua API/CLI và fault injection:
[error-taxonomy-report.json](../evidence/verification/2026-11-16-r63-errors/error-taxonomy-report.json).
Có phân biệt font do source yêu cầu không có với font bắt buộc của image bị thiếu;
JSON shaping hỏng và exception nội bộ có location không bị nhận nhầm syntax/source;
source error không bị đổi thành dependency chỉ vì nội dung thông báo chứa tên lỗi.

Hai build ARM64 và AMD64 qua manifest gate, exit 0:
[ARM64](../evidence/verification/2026-11-16-r63-errors/final-arm64-build.log),
[AMD64](../evidence/verification/2026-11-16-r63-errors/final-amd64-build.log).
Không thêm dependency, không đổi lockfile/manifests/Dockerfile/verify.sh runtime limits
hoặc fixture có sẵn. Image ARM64 `sha256:52a3e7c97646a75901a12b7388c2a1ab58c4090a5aeaa98ce42f19d36dede148`, USER node.
Renderer identity: `aiz-mermaid-v1-sha256:64746a32a589726259348e42ad277457a2bb54ab8ddf9d138fc227844af6c737`.
[Image/source/mount hashes](../evidence/verification/2026-11-16-r63-errors/identity-check.json),
[hai image](../evidence/verification/2026-11-16-r63-errors/image-identities.json),
[source SHA256](../evidence/verification/2026-11-16-r63-errors/source.json).
Workspace không có `.git`; không dùng commit ID giả.

[latest.json](../evidence/verification/latest.json) được summarize từ
[all.log](../evidence/verification/all.log) của revision cuối, tổng exit **0**.
Bash 3.2 compatibility PASS/0; code không bị sửa trong lần full run cuối.

| Nhóm | Kết quả | Exit code | Phạm vi |
| --- | --- | --- | --- |
| edges | PASS | 0 | Toàn bộ assertion ARM64 |
| subgraphs | PASS | 0 | Toàn bộ assertion ARM64, unsupported features là lỗi source |
| theme-labels | PASS | 0 | Toàn bộ assertion ARM64, source policy/labels/fonts |
| contract | PASS | 0 | API/CLI, lifecycle và 49 ca taxonomy |
| runtime | PASS | 0 | Policy probes, source/SVG attacks, no-DOM, determinism ARM64 |
| regression | PASS | 0 | Corpus/stress/benchmark/R6.4 và unsupported loại source |

[So sánh output hợp lệ](../evidence/verification/2026-11-16-r63-errors/positive-output-comparison.json):
PNG/layout mẫu 14 hình giống từng byte với trước; SVG chỉ đổi identity. Image mặc
định đã trỏ đúng revision qua [active-image-tags.json](../evidence/verification/2026-11-16-r63-errors/active-image-tags.json).
Các log taxonomy/development trung gian giữ riêng, không thay kết quả full run cuối.
Lần development-all có mismatch identity do source được chỉnh trong lúc chạy đã
được bỏ khỏi kết luận và rerun toàn bộ trên source/image khớp nhau.

[Audit trước sửa](../evidence/verification/2026-11-16-r63-errors/previous-audit.md),
[latest trước sửa](../evidence/verification/2026-11-16-r63-errors/previous-latest.json)
và các snapshot cũ vẫn giữ nguyên. Runtime AMD64, consumer private, Office và
sandbox công ty vẫn chưa kiểm chứng; build AMD64 không tự thành runtime PASS.

## Wrapper scale — lịch sử trước thay đổi 100MP, 16/11/2026

`scripts/render.sh` đã nhận `--scale` (mặc định vẫn 2). Chỉ wrapper/argv test thay
đổi; renderer, image và giới hạn runtime không đổi. Test Bash 3.2 kiểm tra default,
scale nguyên/thập phân, path có khoảng trắng, option không hợp lệ/duplicate và
failure propagation PASS/0. `test.mmd` LR vượt raster limit ở scale 2 đã render
thành công ở scale 1: PNG **8538 × 954**, 8145252 pixels, exit 0; source không đổi.
[Report](../evidence/verification/2026-11-16-render-scale/report.json),
[shell log](../evidence/verification/2026-11-16-render-scale/shell.log).
Tại thời điểm snapshot wrapper: không nới chiều tối đa 16384 hoặc tổng 16000000 pixels. Đây là kiểm chứng wrapper
riêng; không thay kết quả sáu nhóm renderer của snapshot R6.3 ở trên.

## Kiểm tra R1.3 sau hai clean build — lịch sử trước sửa R6.3

Phép thử này dùng revision trước sửa R6.3; không xác nhận revision mới đã qua
clean rebuild comparison. Dockerfile/đóng gói chưa đổi, gap image chưa được sửa.
Đã chạy hai lần `docker build --no-cache` tuần tự trên cùng builder ARM64,
cùng một frozen source/context (nội dung, mode và mtime không đổi), không ghi đè
image mặc định. Cả hai build qua manifest gate, exit 0; không RUN instruction nào
được báo CACHED. [Frozen source](../evidence/verification/2026-11-16-r13-rebuild/frozen-source.json),
[builder](../evidence/verification/2026-11-16-r13-rebuild/builder.txt),
[lệnh/exit codes](../evidence/verification/2026-11-16-r13-rebuild/commands.json).

| Phép kiểm tra | Kết quả | Phạm vi |
| --- | --- | --- |
| Ghim nguồn, version/checksum; không checkout nhánh Git lúc build | đã kiểm chứng | [pinned-input-check.json](../evidence/verification/2026-11-16-r13-rebuild/pinned-input-check.json): Dockerfile/helper build, 119 npm resolutions, base digest và Debian snapshot |
| Runtime manifest sau hai clean build | đã kiểm chứng | Giống từng byte và đều khớp manifest ARM64 đã ghim; đây là các nội dung được inventory theo dõi |
| Render lại sau rebuild | đã kiểm chứng | showcase, dense-25-35 và theme-labels: 6 lượt CLI/fresh containers đều exit 0, cả 9 cặp SHA256 SVG/PNG/layout bằng nhau |
| Toàn bộ image Docker giống từng byte | chưa đáp ứng | Image IDs/config Created và layer digests khác nhau; đây là gap tái lập đóng gói image, không phải lỗi render hay lỗi môi trường kiểm tra |
| Archive OCI và AMD64 clean rebuild comparison | chưa kiểm chứng | Chưa export/so byte archive OCI riêng hoặc chạy phép so rebuild AMD64; không suy từ ARM64 |

[report.json](../evidence/verification/2026-11-16-r13-rebuild/report.json) ghi kết quả đầy đủ.
[filesystem-samples.json](../evidence/verification/2026-11-16-r13-rebuild/filesystem-samples.json)
ghi mtime package khác dù nội dung giống và checksum log apt/dpkg khác. Image IDs:
`98f424d62d457230796699a99440ff1c2520570499071bea458b311516bf4d24` và
`9f78ff01325f1a85d64bf5559991636d9f22fe07d915d5ca90e90d61bff2f223`.
Không chuẩn hóa/xóa log hoặc sửa Dockerfile để che khác biệt trong lượt kiểm tra.

Ảnh giống nhau sau rebuild là bằng chứng cho determinism R8.1 trong các fixture
đã chạy, không tự chứng minh toàn bộ artifact build R1.3 byte-identical. Không
cần mentor phê duyệt để chạy test; nếu tài liệu chưa rõ, điều cần thống nhất là
artifact nghiệm thu R1.3 (nội dung runtime hay toàn image phân phối). Kết quả
quan sát ở hai mức vẫn ghi riêng, không tự đổi tiêu chí thành đạt.

Bằng chứng lịch sử: [initial-arm64-report.json](../evidence/runtime/initial-arm64-report.json)
ghi rõ image/version của revision trước đã qua một số phép thử runtime;
[STATUS.json](../evidence/runtime/STATUS.json) không ghi matrix cuối là pass.
Không dùng bằng chứng cũ để suy ra toàn bộ source hiện tại đã chạy thành công.

## Hợp đồng đầu vào/đầu ra

| Mục | Trạng thái | Test hoặc bằng chứng, phạm vi |
| --- | --- | --- |
| Khai báo `Rendered(svg: str, png: bytes, layout: dict)`; mặc định scale=2, timeout=30 | đã kiểm chứng | Introspection API trên host: [host-validation.json](../evidence/verification/host-validation.json); [renderer.py](../renderer/renderer.py). Chưa phải positive render. |
| API render thật trả đủ SVG/PNG/layout, CLI, retry, chạy đồng thời, công bố atomic | đã kiểm chứng | `contract` PASS/0 ARM64 revision sau sửa E1: positive API/CLI, retry/concurrency/atomic publication; chỉ phạm vi fixtures đã chạy. |
| Nhúng source, cache, edit/theme/embed/Office do engine khác đảm nhiệm | chưa kiểm chứng | Engine và các consumer private không có trong workspace; không thay bằng test tự viết rồi coi là tương thích engine cũ. |

## R1 — Nguồn gốc và chuỗi cung ứng

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R1.1 Nguồn đáng tin; không dùng repo cá nhân của bên thứ ba | chưa đáp ứng | Theo cách đọc cấm mọi upstream cá nhân phân phối: khroma, robust-predicates, lru-cache của npm base và entities (nay trực tiếp, vốn đã phân phối) vẫn cần quyết định mentor. App lru-cache 11.5.3 cùng jsdom đã bị loại. Không kết luận thiếu cộng đồng từ namespace, không tự phê duyệt ngoại lệ. |
| R1.2 License dùng thương mại/phân phối on-prem | chưa kiểm chứng | Inventory có license/notice thực tế, gồm DOMPurify dual-license, ELKjs EPL/GPL và GPL/LGPL trong Debian. Không phải toàn image đều MIT/BSD; cần hoàn tất kiểm tra nghĩa vụ phân phối. [Review](../deployment/renderer/runtime/THIRD_PARTY_REVIEW.md). |
| R1.2 bổ sung: corresponding-source/source-offer cần cho các thành phần áp dụng | chưa đáp ứng | Chưa đóng gói source archives/offer; giữ copyright và URL upstream không thay thế việc hoàn tất nghĩa vụ. Đây là gap phân phối, không phải phán quyết pháp lý cho mọi package. |
| R1.3 Ghim npm/version/checksum, không checkout branch động | đã kiểm chứng | Kiểm tra tĩnh [package.json](../renderer/package.json), [package-lock.json](../renderer/package-lock.json): 119 resolution registry.npmjs.org có SHA512 integrity; Dockerfile dùng `npm ci --ignore-scripts`. Không suy ra audit CVE đã hoàn tất. |
| R1.3 Base digest, snapshot, package/font/checksum đã ghi | đã kiểm chứng | [Dockerfile](../deployment/renderer/Dockerfile), [build-policy.json](../deployment/renderer/runtime/build-policy.json), hai [manifest](../deployment/renderer/runtime/manifests): mỗi arch có 164 archive SHA256, 274 font files, fontconfig và target symlink, npm/tool hashes. Đây là kiểm tra dữ liệu đã lưu. |
| R1.3 Build hiện tại vượt manifest drift gate | đã kiểm chứng | Revision R6.3: build ARM64 và AMD64 đều qua gate, exit 0, không đổi dependency/manifests. Hai clean builds so sánh nội dung là bằng chứng lịch sử trước R6.3, không xác nhận revision mới đã được clean-rebuild comparison. |
| R1.3 Clean build tái lập toàn bộ image Docker | chưa đáp ứng | Revision trước R6.3 có hai image IDs/config/layer digests khác nhau do khác biệt timestamps/log cài đặt quan sát được; gap đóng gói chưa sửa vì Dockerfile/recipe không đổi. Chưa chạy lại clean rebuild comparison cho revision R6.3; không dùng output render giống nhau để kết luận image tái lập. |
| R1.4 Image python-vm cho linux/arm64 và linux/amd64 | chưa kiểm chứng | Standalone ARM64 và AMD64 đã build qua gate; chỉ ARM64 đã chạy đủ sáu nhóm runtime. Chưa phải image python-vm/office_sandbox thực tế; runtime AMD64 và matrix hiện tại chưa chạy. [Evidence cũ](../evidence/runtime/infrastructure-blocked-status.json) chỉ ghi blocker lịch sử, không phải Docker hiện tại. |
| R1.5 Quy trình cập nhật gắn đổi định danh | đã kiểm chứng | Quy trình được ghi trong [README](development.md), gồm review policy/lock/manifest và đổi identity theo hash. Chưa chứng minh một quy trình release thực tế của team đã áp dụng/được mentor phê duyệt. |

## R2 — An toàn và vòng đời

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R2.1 `PROGRAMS`, `PROGRAM_READ`, scratch và exec trong office_sandbox.py | chưa kiểm chứng | Không có private file/chương trình đăng ký trong project; không truy cập hoặc yêu cầu source private. |
| R2.1 Landlock/path read-write allowlist | chưa kiểm chứng | Read-only root và scratch riêng trong Docker không phải Landlock. Không có bằng chứng syscall-level chỉ đọc đúng PROGRAM_READ. [runtime_guard.py](../tests/runtime_guard.py) ghi rõ phần không mô phỏng. |
| R2.1 AF_UNIX-only, không ptrace/mount/namespace | đã kiểm chứng | `runtime` PASS/0 ARM64: filter libseccomp bổ sung và positive/negative probes AF_UNIX/Internet/ptrace/mount/namespace. Chưa phải full private seccomp policy của office_sandbox.py; AMD64 hiện tại chưa chạy. |
| R2.1 RAM 2 GiB, CPU 300 s, FD 256, file 256 MiB | đã kiểm chứng | `runtime` PASS/0 ARM64: cgroup memory.max=2147483648, CPU rlimit 300 giây/process, FD=256, FSIZE=268435456; đã thử hết FD/vượt FSIZE. Chưa stress hết RAM/CPU hay chứng minh tổng CPU cây tiến trình. |
| R2.2 Source không thực thi JS/callback/link, tải ảnh/font/file ngoài | đã kiểm chứng | `runtime` và `theme-labels` PASS/0 ARM64 cho các ca callback/link/active tags/resource styles/config/YAML injection; environment/preload sentinel. Chỉ các attack cases đã chạy, không phải proof chống mọi lỗ hổng dependency. |
| R2.3 SVG không script/foreignObject/event handler/reference ngoài | đã kiểm chứng | `runtime` PASS/0 ARM64: validator từ chối script/foreignObject/image/event/external-reference/duplicate ID. Static allowlist và tests này chứng minh phạm vi đã nêu; invalid stroke-linecap enum/URL cũng bị chặn sau sửa E1. |
| R2.4 Timeout toàn lượt, mặc định 30 s, dừng cả cây | đã kiểm chứng | `contract` PASS/0 ARM64: deadline chung Node/Pango/raster, kill/reap cây process, scratch cleanup, retry. Không hứa hard real-time; có overhead cleanup/scheduling. |
| R2.5 Không giữ process/trạng thái giữa lượt | đã kiểm chứng | `contract` PASS/0 ARM64: private scratch mỗi call, concurrent API/CLI, descendants/scratch cleanup, retry; code tạo backend mới mỗi lượt. |
| Input quá giới hạn, scale/timeout không hợp lệ và source rỗng | đã kiểm chứng | 4 trường hợp early-validation chạy trên host trong [host-validation.json](../evidence/verification/host-validation.json). Chỉ phần trước khi gọi backend; không thay cho stress render. |
| Source lớn, lồng sâu, nhãn dài, chu trình | đã kiểm chứng | `regression` PASS/0 ARM64: source 44992 ký tự, 40 node/50 edge/cycle, 16 tầng, nhãn multiline 1642 ký tự; 256 tầng/line/raster/char/501-edge overflow bị chặn đúng limit. |

## R3 — Offline

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R3.1 Không mạng khi render, kể cả font/theme/update | đã kiểm chứng | Các nhóm thực sự chạy với --network none; `runtime` positive render dưới filter AF_UNIX-only, negative resource/font/config cases PASS/0 ARM64. Chỉ môi trường độc lập; không xác nhận office sandbox. |
| R3.2 Font nằm sẵn trong image | đã kiểm chứng | `runtime` PASS/0 ARM64 hash lại toàn bộ 274 font files và fontconfig khớp manifest; `theme-labels` kiểm tra missing family/glyph báo lỗi. Không hứa mọi font tùy ý có sẵn. |

## R4 — Phạm vi source

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R4.1 Flowchart đầy đủ theo toàn bộ danh sách yêu cầu | đã kiểm chứng | Sáu nhóm PASS/0 ARM64 revision hiện tại cho corpus công khai và các phân mục R4.1 bên dưới; fixture tổng hợp đủ 14 shapes/32 edges/5 subgraphs render thành công. Không suy ra private tests hoặc mọi source có thể có đều đúng. |
| R4.1 `flowchart`/`graph`, TB/TD/BT/RL/LR | đã kiểm chứng | `subgraphs` PASS/0 ARM64: 2 header × 5 hướng TB/TD/BT/RL/LR, vị trí và geometry của fixtures. |
| R4.1 Subgraph lồng nhau, direction riêng/ngoại lệ external links | đã kiểm chứng | `subgraphs` PASS/0: nesting/direction/membership/containment/title/external-leaf fallback; `regression` PASS/0 thêm 16 tầng, ARM64. Không đòi direction riêng khi leaf nối ngoài. |
| R4.1 14 shape | đã kiểm chứng | `subgraphs` và `theme-labels` PASS/0 ARM64: 14 legacy shapes, aliases, boundary contacts, styled fonts. Legacy flag=odd; modern paper-tape vẫn bị từ chối đúng phạm vi. |
| R4.1 4 nét, arrow/none/circle/cross/both, labels, parallel, chain, &, cycles | đã kiểm chứng | `edges` PASS/0 ARM64 sau sửa E1: solid/dotted/thick/invisible, arrow/none/circle/cross/both, labels, parallel, chain, &, cycles, single-ended variants và boundary contacts; không bỏ assertion. |
| R4.1 classDef/class/:::class/style/linkStyle theo ordinal | đã kiểm chứng | `theme-labels` PASS/0 ARM64: class/style precedence, shorthand, hai edge song song, linkStyle ordinal; chỉ thuộc tính allowlist, không arbitrary CSS. |
| R4.1 YAML title/config.theme/themeVariables/fontFamily/cỡ chữ | đã kiểm chứng | `theme-labels` PASS/0 ARM64: 5 palettes, title glyph pixels/geometry, header reserve và font trước layout, YAML/config trong phạm vi đã code hóa. |
| R4.1 br/entity/tiếng Việt | đã kiểm chứng | `theme-labels` PASS/0 ARM64: 3 br spellings, named/decimal entities, NFC/NFD glyph paths; regression PASS nhãn multiline dài. |
| R4.2 Danh sách diagram khác trong v1 | chưa kiểm chứng | Mentor chưa chốt. Renderer hiện flowchart-only; sequence/ER/pie chỉ là negative tests, không tự được thêm vào v1. |
| R4.3 Unsupported type báo lỗi, không SVG rỗng | đã kiểm chứng | `contract`/`regression` PASS/0 ARM64: sequence/ER/pie bị unsupported, nonzero CLI và không xuất destination; không quyết định phạm vi v1. |

## R5 — SVG/PNG/layout

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R5.1 SVG có viewBox, engine có thể thêm metadata | đã kiểm chứng | Common checks ở sáu nhóm PASS/0 ARM64 kiểm tra viewBox; regression chèn inert metadata sau render rồi so PNG không đổi. Fixture tổng hợp cũng có output/geometry hợp lệ. |
| R5.2 PNG raster đúng SVG, scale mặc định 2 | đã kiểm chứng | `contract`/`runtime`/`regression` PASS/0 ARM64: exact reraster cùng SVG, PNG dimensions, default scale=2. Showcase cũng exact reraster PASS; chỉ corpus đã chạy. |
| R5.3 Layout schema `[x,y,w,h]`, font fields | đã kiểm chứng | `contract` và common checks PASS/0 ARM64: schema hộp/font và validation công khai. Consumer/checks.py private chưa kiểm chứng; chưa xác nhận ABI với engine công ty. |
| R5.3 Node/subgraph ID, edge ordinal, members | đã kiểm chứng | `edges` PASS/0 ARM64 kiểm tra parser order/ordinal khác suffix SVG ID; `subgraphs` PASS membership/direct IDs gồm subgraph con. Semantics direct members với private consumer vẫn chưa xác nhận. |
| R5.3 Points/hộp đúng hình học sau transform | đã kiểm chứng | Common/verify_geometry trong subgraphs/theme-labels/regression PASS/0 ARM64 đo primitive và glyph extents + translation, containment/points. Phạm vi fixtures thành công; hộp không cộng nửa stroke, semantics consumer còn cần xác nhận. |
| R5.4 Cả ba output khớp nhau | đã kiểm chứng | Sáu nhóm PASS/0 ARM64, geometry checks và exact reraster cho artifacts đã kiểm tra; fixture tổng hợp 14 nodes/32 edges/5 groups cũng PASS. Không khẳng định private consumer compatibility hay mọi source tùy ý. |

## R6 — Lỗi source/engine

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R6.1 Parse chặt, source sai không đoán/vẽ rỗng | đã kiểm chứng | `contract`/`regression` PASS/0 ARM64 cho negative syntax, unsupported, không output rỗng. Chỉ corpus đã chạy, không phải mọi cú pháp sai có thể có. |
| R6.2 SyntaxError line 1-based, có YAML/multiline | đã kiểm chứng | `contract` PASS/0 ARM64: exact lines 4/10/9/4, YAML/CRLF/comment/multiline và error message; regression bổ sung R6.4. |
| R6.3 Phân biệt lỗi source model sửa được với lỗi engine | đã kiểm chứng | Taxonomy API/CLI rõ syntax/source/engine và category source/engine; 49 ca positive/negative và fault injection PASS ARM64 trong contract. Unknown/internal lỗi giữ engine; lỗi source có kiểu/code tường minh, không đoán category từ message. Consumer private tiếp nhận class/field mới vẫn chưa kiểm chứng. Xem error-handling.md và error-taxonomy-report.json. |
| R6.4 Special chars/ngoặc không quote, end id/class, mismatch | đã kiểm chứng | `regression` PASS/0 ARM64: reserved end ID line 2, class end line 3, unquoted parenthesis line 2, delimiter mismatch line 2; không thay expected output. |

## R7 — Font và tiếng Việt

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R7.1 Shaping Noto Sans, dấu dựng sẵn/kết hợp, không thiếu glyph | đã kiểm chứng | `theme-labels` PASS/0 ARM64: Pango/Cairo glyph paths, NFC/NFD equality, unknown_glyphs_count và missing glyph rejection. |
| R7.2 Đo width thật, node vừa nhãn | đã kiểm chứng | subgraphs/theme-labels/regression PASS/0 ARM64 dùng actual primitive và glyph path extents/corners: 14 shapes, styled fonts, long labels; không phải chỉ nhìn ảnh. |
| R7.3 Font thực sự dùng/fallback | đã kiểm chứng | `theme-labels` PASS/0 ARM64: Pango serialized runs, bỏ phantom empty-label fonts, generic mapping/local fallback/unknown family. |

## R8 — Determinism/identity

| ID / yêu cầu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| R8.1 Byte-for-byte SVG/PNG/layout trong cùng môi trường ghim | đã kiểm chứng | Revision R6.3: runtime 3 fixtures ×3 independent processes và regression 25/35 ×3 PASS ARM64. Clean rebuild comparison trước R6.3 là lịch sử, không dùng để xác nhận revision mới; matrix AMD64/cross-arch equality chưa kiểm chứng. |
| R8.2 SVG IDs ổn định, không collision | đã kiểm chứng | `runtime` PASS/0 ARM64: collision-source IDs, repeated ID lists, unique IDs; regression byte equality; edges hiện tại PASS sau sửa E1. |
| R8.3 Chuỗi version gắn backend/dependency/font/config | đã kiểm chứng | `runtime` PASS/0 ARM64: CLI/SVG identity, backend mutation đổi identity, thực tế npm/font/fontconfig khớp manifest; image/source/mount hashes khớp identity-check.json. Không xác nhận private cache integration. |
| R8.3 Engine đưa version vào cache hash/source nhúng | chưa kiểm chứng | Private cache/embed integration không có; không tự thêm cache/embed vào renderer để thay kiểm thử engine. |

## Các mục “nên có”, nghiệm thu và quyết định chưa chốt

| Mục tài liệu | Trạng thái | Test hoặc bằng chứng, giới hạn |
| --- | --- | --- |
| Bố cục dễ đọc, hạn chế edge/node/subgraph overlap | chưa kiểm chứng | Các assertion containment/title/sibling boxes và obstacle routing trong subgraphs PASS/0 ARM64; chưa có đánh giá dễ đọc/crossings toàn corpus. Cần review trực quan và tiêu chí mentor. |
| themeCSS cơ bản/bo góc qua CSS | chưa đáp ứng | config themeCSS, rx/ry và transform ngoài allowlist bị từ chối; không được coi là đã hỗ trợ. Đây là nice-to-have, không tự nâng thành blocker v1. |
| 25 node/35 edge trong vài giây, thời gian và bộ nhớ | chưa kiểm chứng | Revision R6.3: ba lượt ARM64 CLI 0.623993 / 0.585388 / 0.575722 giây; peak RSS lấy mẫu 151674880 / 151478272 / 151482368 byte. Geometry/exact reraster/byte equality PASS; SLA/RAM chưa có ngưỡng mentor phê duyệt. Xem latest.json trong snapshot R6.3 (lịch sử; số đo hiện tại nằm ở latest.json gốc). |
| Lỗi kèm gợi ý sửa | chưa đáp ứng | Có vài thông báo hướng dẫn (br/entity/font/flag), chưa có bộ hướng dẫn nhất quán cho mọi lỗi. |
| Nghiệm thu 1: 53 test private render/DOCX/PPTX/checks/theme/embed | chưa kiểm chứng | Không có tests/consumer private trong workspace; không tuyên bố đã chạy hoặc tự thay bằng fixtures tương tự. |
| Nghiệm thu 2: approval-sunset/bidding-slate/entities/parallel/sequence/subgraph/title/invalid cũ | chưa kiểm chứng | Native private fixtures không được cung cấp; fixtures mới trong scripts không phải bằng chứng thay thế. Sequence trong danh sách cũ không tự quyết định phạm vi v1 mới. |
| Nghiệm thu 3: python-vm + exec office sandbox + 2 kiến trúc | chưa kiểm chứng | Standalone container và probe không tương đương môi trường đích; native amd64 chưa chạy. |
| Nghiệm thu 4: review bảo mật/supply chain và source adversarial | chưa kiểm chứng | `runtime` và `regression` adversarial/stress scoped PASS/0 ARM64 hiện tại. Chưa phải security/supply-chain/license sign-off của team; R1 vẫn còn; E1 đã sửa và rerun đủ sáu nhóm. |
| Nghiệm thu 5: Word, LibreOffice, WPS, Google Docs/Slides roundtrip | chưa kiểm chứng | Không có DOCX/PPTX roundtrip thủ công/tích hợp trong lượt này; không truy cập các ứng dụng hay thay file engine. |
| Quyết định 7.1: non-flowchart v1 | chưa kiểm chứng | Mentor chưa chốt; không tự thêm sequence/ER. |
| Quyết định 7.2: ngưỡng performance/memory | chưa kiểm chứng | API có hard limits đã ghi, khác ngưỡng chất lượng/latency benchmark chưa chốt. |
| Quyết định 7.3: ảnh cũ/source nhúng renderer cũ | chưa kiểm chứng | Không có quyết định compatibility/migration; không tự chọn coi là ảnh thường hay tự viết migration. |
| Quyết định 7.4: đơn vị duy trì lâu dài | chưa kiểm chứng | Không thể suy ra từ code hoặc người chạy test; cần mentor/team chỉ định. |

## Cách chạy lại và đọc phép đo

```sh
python3 tests/verify_shell_args.py --bash /bin/bash
bash scripts/verify.sh all > evidence/verification/all.log 2>&1
python3 scripts/summarize_verification.py evidence/verification/all.log \
  --output evidence/verification/latest.json
```

`all` chạy `edges`, `subgraphs`, `theme-labels`, `contract`, `runtime`, `regression`
trong các container riêng, tiếp tục sau nhóm lỗi và trả nonzero nếu có lỗi/chưa
kiểm chứng. Không thay đổi các giới hạn container hoặc assertion có sẵn.

Khi `regression` chạy được, `REGRESSION_REPORT` chứa ba số đo
`wall_seconds`, `sampled_process_tree_peak_rss_bytes`, số mẫu và digests của
đúng bộ artifact vừa đo. RSS là tổng VmRSS lấy mẫu 10 ms của CLI và descendants:
shared pages có thể bị đếm nhiều lần, peak ngắn có thể bị bỏ lỡ, không phải PSS
hay peak cgroup chính xác. Monitor không nằm trong RSS được báo; chi phí sampling
có thể ảnh hưởng wall time. Không gọi đó là chứng minh stress RAM hay đạt SLA.

Report được in cả khi test sau benchmark fail để không mất số đo đã thực sự
thu được. Nếu không có report, summary giữ `measurements: null`, không tạo số
0 giả. Snapshot này đã rerun với Docker hoạt động; một nhóm pass vẫn không tự chốt
private integration, license acceptance, manual Office roundtrip hay quyết định mentor.

## Phân tách việc còn lại và thay đổi trạng thái

- **Hộp đen độc lập:** E1 đã sửa; cả sáu nhóm PASS/0 trên source/hash hiện tại ARM64.
  `edges`, R4.1/cross và R5.4 chuyển sang đã kiểm chứng trong phạm vi corpus công khai;
  không tuyên bố toàn bộ source tùy ý. Ba fixture qua hai clean build ARM64 ở revision trước R6.3 đã
  byte-identical ở đầu ra render, nhưng toàn image khác ID/layers nên chưa đáp ứng
  tiêu chí byte-identical image. Full runtime matrix AMD64 và archive OCI riêng
  chưa kiểm chứng. Build manifest gate đã qua.
- **Cần môi trường công ty:** office_sandbox.py registration/PROGRAM_READ/Landlock/full
  seccomp, python-vm, consumer/53 private tests, cache/embed và Office roundtrip vẫn
  chưa kiểm chứng. Docker độc lập không thay các kiểm tra này; không yêu cầu source private.
- **Mentor/team quyết định:** phạm vi R1.1 (transitive/bundled/build tools và định nghĩa
  cộng đồng), governance/security-response evidence, source/license distribution
  approval, diagram v1, SLA/RAM, layout member/box semantics, migration và đơn vị duy trì.
  Taxonomy R6.3 đã triển khai/kiểm chứng local; consumer private cần xác nhận class/field mới.
  Source-offer và nice-to-have themeCSS/gợi ý lỗi vẫn chưa đáp ứng.

[Điều tra R1.1](renderer-r1.1-investigation.md) thực hiện trên image trước sửa E1;
bản cập nhật ngày 16/11 ghi rõ jsdom/app lru-cache đã bị loại, entities vẫn phân phối
và npm base lru-cache còn lại. Lockfile/manifests đã cập nhật có review diff; R1.1
không được nâng thành đạt.
