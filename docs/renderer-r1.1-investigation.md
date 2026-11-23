# Điều tra R1.1 — snapshot 13/11/2026

**Cập nhật 16/11/2026:** bảng dưới là điều tra lịch sử của image ngày 13/11.
Image mới đã gỡ jsdom và lru-cache 11.5.3 của ứng dụng; lru-cache 11.5.1
trong npm base vẫn được phân phối. entities 9.0.0 (fb55/entities, BSD-2-Clause)
vốn có trong image được giữ làm dependency trực tiếp để decode entity văn bản,
không phải thay thế bằng một DOM library khác. khroma/robust-predicates không
thay đổi. R1.1 vẫn chưa được nâng thành đạt; phạm vi cấm upstream cá nhân cần
mentor chốt. Xem [diff dependency](../evidence/verification/2026-11-16-no-jsdom/dependency-diff.json)
và [diff manifest đã soát](../evidence/verification/2026-11-16-no-jsdom/reviewed-manifest-diff.json).

Phạm vi: ba package được audit/review cũ nêu tên là personal upstream:
khroma, lru-cache, robust-predicates; bổ sung bản lru-cache thực sự đi kèm npm
trong base image. Không phải cuộc kiểm toán toàn bộ 292 package record hay
phê duyệt security/license. Không thay dependency, backend hoặc bundle.

Image kiểm tra: `linux/arm64`,
`sha256:db5aa7c9cd3adc4f77f81a496543ad42ac03c6b5ac6d22d75647e5e98348ca40`.
[Image metadata/package.json thực tế](../evidence/verification/2026-11-13/image-content.json),
[lockfile](../renderer/package-lock.json),
[nguồn npm chính thức đã lưu](../evidence/verification/2026-11-13/upstream-registry.json),
[index nguồn GitHub](../evidence/verification/2026-11-13/upstream-index.json).
Nguồn chính thức được truy cập ngày 13/11/2026; metadata hiện tại không chứng minh
ai có quyền publish ở mọi thời điểm lịch sử.

## Bảng ngắn

Mọi chuỗi dưới bắt đầu từ renderer; version là resolution thực tế, không phải range.

| Package/version: lock → image | Chuỗi dependency | Upstream/chủ thể duy trì | Vai trò build/runtime | Có phân phối? | Kết luận và đề xuất |
| --- | --- | --- | --- | --- | --- |
| khroma 2.1.0 → 2.1.0 | mermaid 12.3.0 → khroma | [fabiospampinato/khroma](https://github.com/fabiospampinato/khroma), Fabio Spampinato; npm publisher `fabiospampinato`; có contributor khác | Production transitive; xử lý màu/theme Mermaid, không phải dev-only | Có: `/app/node_modules/khroma`; core import package, browser/ESM bundles còn nhúng code khroma 2.1.0 | Vướng câu cấm upstream cá nhân nếu áp dụng transitive; chưa có bằng chứng governance/security-response đáp ứng tiêu chuẩn team. Có release/contributors. Đề xuất tự duy trì adapter màu và rebuild Mermaid có kiểm soát; chi phí trung bình/cao, nguy cơ lệch theme/palette. |
| lru-cache 11.5.3 → 11.5.3 | jsdom 31.0.0 → lru-cache | [isaacs/node-lru-cache](https://github.com/isaacs/node-lru-cache), Isaac Z. Schlueter; npm publisher `isaacs`; CONTRIBUTORS nhiều tác giả | Production runtime; jsdom CSS parser/selector caches, không phải build-only | Có: `/app/node_modules/lru-cache` | Vướng câu cấm theo cách đọc chặt, nhưng không đủ căn cứ nói thiếu cộng đồng. Đề xuất giữ chờ mentor hoặc tự duy trì cache adapter/patch jsdom; chi phí trung bình, rủi ro CSS/cache/performance. |
| robust-predicates 3.0.3 → 3.0.3 | mermaid 12.3.0 → d3 7.9.2 → d3-delaunay 6.0.6 → delaunator 5.1.0 → robust-predicates; nhánh khác qua dagre-d3-es 7.0.14 → cùng d3 | [mourner/robust-predicates](https://github.com/mourner/robust-predicates), Vladimir Agafonkin; npm publisher `mourner`; có contributor khác | Production dependency graph; chưa chứng minh thuật toán Delaunay được gọi trong flowchart hiện tại | Có: `/app/node_modules/robust-predicates`; chưa chứng minh code robust được nhúng riêng trong Mermaid bundle | Vướng câu cấm nếu gồm code phân phối dù không dùng. Đề xuất build Mermaid flowchart-only loại nhánh Delaunay khỏi dependency graph sau khi chứng minh unreachable và kiểm tra bundle; chi phí cao, ảnh hưởng diagram dùng triangulation. Tự viết robust predicates còn tốn kém/rủi ro sai số hình học. |
| lru-cache: không có resolution 11.5.1 trong app lock → 11.5.1 trong npm base | Node image → npm 11.19.1 → cacache 20.0.4 → lru-cache 11.5.1; còn @npmcli/arborist 9.9.1 và các consumers khác | Cùng upstream Isaac như trên; bản khác với jsdom | Công cụ build/package management; không được entry point renderer gọi, nhưng tồn tại ở runtime filesystem | Có: `/usr/local/lib/node_modules/npm/node_modules/lru-cache` | Không thể chỉ loại bản app rồi coi image sạch. Đề xuất final stage bỏ npm/Yarn/tooling sau build, chi phí thấp/trung bình; thay Dockerfile/manifest/identity và kiểm tra không cần npm runtime. Không giải quyết bản jsdom. |

Đánh giá chi phí trên là ước lượng kỹ thuật tương đối, chưa phải lịch triển khai.
Không thể xóa thư mục node_modules rồi khẳng định đã loại code bundle; cũng không
thể đổi URL sang fork tổ chức để tự coi là có cộng đồng duy trì. Nếu team chọn tự
viết/tự duy trì như R1.1 cho phép, phải thực sự nhận ownership, cập nhật và kiểm thử.
Mọi phương án sẽ đổi identity và cần build/review/rerun; chưa thực hiện phương án nào.

## Bằng chứng về duy trì và phát hành

- **khroma:** [npm chính thức](https://registry.npmjs.org/khroma) ghi 10 versions,
  registry tạo 03/02/2020; 2.0.0 ngày 07/04/2022, 2.1.0 ngày 12/10/2023.
  [Tags upstream](https://github.com/fabiospampinato/khroma/tags) còn có v1.0.0
  ngày 26/09/2019, phân biệt tag với ngày publish npm.
  [package.json upstream](https://github.com/fabiospampinato/khroma/blob/master/package.json)
  khai repo và test/compile/prepublish scripts.
  [Contributors API](https://api.github.com/repos/fabiospampinato/khroma/contributors)
  có Fabio (69 commits), AbleLincoln (29), vfonic (1), tài khoản agent (1) tại snapshot.
  Một npm publisher không đồng nghĩa chỉ một người đóng góp; khoảng cách release
  dài cũng chưa đủ để kết luận bỏ bảo trì hay có lỗ hổng không được xử lý.
- **lru-cache:** [npm chính thức](https://registry.npmjs.org/lru-cache) ghi 164 versions,
  registry tạo 16/07/2011; 11.5.1 ngày 27/05/2026, 11.5.2 ngày 07/07/2026,
  11.5.3 ngày 18/09/2026. [CHANGELOG](https://github.com/isaacs/node-lru-cache/blob/main/CHANGELOG.md)
  mô tả các thế hệ, fixes và API changes;
  [CONTRIBUTORS](https://github.com/isaacs/node-lru-cache/blob/main/CONTRIBUTORS)
  liệt kê nhiều người ngoài Isaac. Trang GitHub Releases trống không có nghĩa là
  không phát hành: npm và changelog là bằng chứng phát hành ở đây.
- **robust-predicates:** [npm chính thức](https://registry.npmjs.org/robust-predicates)
  ghi 12 versions, tạo 01/09/2019; 3.0.1 ngày 05/04/2021, 3.0.2 ngày 25/05/2023,
  3.0.3 ngày 22/03/2026.
  [Release v3.0.3](https://github.com/mourner/robust-predicates/releases/tag/v3.0.3)
  ghi fix loss of precision hiếm gặp trong orient3d; đây là sửa đúng đắn tính toán,
  không tự gọi là xử lý CVE. [Contributors API](https://api.github.com/repos/mourner/robust-predicates/contributors)
  có mourner (99), tinko92 (1); [README](https://github.com/mourner/robust-predicates)
  công nhận thuật toán gốc của Jonathan Shewchuk, không biến Berkeley thành đơn vị
  bảo trì bản port npm này.

Snapshot contributor là lịch sử đóng góp, không phải danh sách current maintainers
hay quyền publish. Npm maintainer metadata, package author và repo ownership cho
thấy các cá nhân chịu trách nhiệm chính; chưa xác minh được tổ chức chịu trách nhiệm
chính thức, quy trình kế nhiệm hoặc lịch sử xử lý lỗ hổng theo mức team yêu cầu.
Không lấy “chưa xác minh được” thành bằng chứng rằng không có các quy trình đó.
Một request `SECURITY.md` root của lru-cache trả 404 được lưu trong index; không đủ
để kết luận dự án không có security policy ở đường dẫn khác hoặc inherited policy.

## Runtime và artifact

Lockfile không gắn `dev: true` cho cả ba production resolutions; Dockerfile dùng
`npm ci --omit=dev --ignore-scripts`, giữ nguyên node_modules trong final image.
DevDependencies của chính upstream (TypeScript/rollup/test tools) không tự trở
thành dependencies renderer. Ba production package không thể được phân loại
build-only chỉ vì upstream dùng bundler.

[Static imports trong image](../evidence/verification/2026-11-13/runtime-imports.json)
xác nhận jsdom require lru-cache. [Kiểm tra Mermaid](../evidence/verification/2026-11-13/mermaid-bundled-code.json)
xác nhận core import khroma và bundle browser nhúng code khroma 2.1.0;
[sourcemaps](../evidence/verification/2026-11-13/mermaid-bundle-sources.json)
cũng ghi khroma. Không tìm được tên robust-predicates trong phép quét bundle này,
không dùng điều đó để khẳng định không có code tương đương; package 3.0.3 nằm
trong filesystem đã được xác nhận. Sourcemap browser có d3-delaunay 6.0.4, khác
resolution 6.0.6 cài trong lockfile; không gán version lock cho mọi code bundle.
Renderer import JSDOM và Mermaid thật ở runtime. Không có execution trace để khẳng
định mọi nhánh của các bundle được chạy; hiện diện/phân phối đã được xác nhận độc lập.
[Consumers của npm base](../evidence/verification/2026-11-13/lru-consumers.json)
ghi npm version và các parent package thực tế. License cho phép sử dụng thương mại
không phải bằng chứng đạt R1.1 và không thay phê duyệt license của team.

## Kết luận cần mentor

R1.1 gồm hai ý khác nhau: **tổ chức/cộng đồng đáng tin có lịch sử release/xử lý
lỗ hổng**, và **không dùng repo cá nhân bên thứ ba**. Nếu ý cấm áp dụng tuyệt đối
cho mọi production transitive/bundle/tool được phân phối thì image hiện tại
**chưa đáp ứng**: upstream cá nhân đã xác nhận cùng package thật trong image,
không chỉ một URL tình cờ trong metadata. Đây là căn cứ cho gap đang giữ trong audit.
Không có căn cứ khẳng định ba dự án đều thiếu cộng đồng hoặc không có release.

Mentor cần quyết định: lệnh cấm chỉ nhắm backend trực tiếp hay cả transitives và
npm/tooling; “repo cá nhân” là namespace sở hữu hay mô hình quản trị; cộng đồng
nhiều contributor nhưng một publisher có được chấp nhận không; bằng chứng nào
về security response/ownership được coi là đủ; code đã bundle nhưng chưa được gọi
có thuộc phạm vi cấm không. Các điểm này **chưa kiểm chứng/chưa có quyết định**,
không tự đổi R1.1 sang đạt và không tự phê duyệt ngoại lệ.
