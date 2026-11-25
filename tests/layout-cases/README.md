# Bộ mẫu kiểm tra bố cục Mermaid

36 file `.mmd` để kiểm tra Dagre, ELK và chế độ `auto`. Đây là bộ **đầu vào kiểm thử**, không phải ảnh kết quả chuẩn để so khớp pixel.

## Thứ tự sử dụng

- `01–08`: hình cơ bản, từ một node đến nhiều thành phần rời.
- `09–18`: nhãn dài, chuỗi dài, cây, nhánh nhập/tách, vòng lặp, cạnh song song và nhóm.
- `19–24`: nhiều nhóm, kết nối chéo, kích thước không đều và nhóm lồng sâu.
- `25–27`: stress số lượng node/cạnh, nhánh rộng và đường phản hồi.
- `28`: bản sao nguyên vẹn `chat_flow.mmd` trong repo tại thời điểm tạo bộ mẫu.
- `29–36`: từng cặp sát ngưỡng chọn engine của `auto`; không phải thứ tự tăng độ khó.

Độ khó là phân loại phục vụ quan sát, không phải thước đo tuyệt đối. Một hình ít node nhưng nhiều vòng lặp vẫn có thể khó hơn hình lớn có cấu trúc đều.

## Render và so sánh

Chạy từ thư mục gốc repo; mỗi lệnh dùng một thư mục đầu ra mới:

```bash
bash scripts/render.sh tests/layout-cases/19-cross-group-connections.mmd artifacts/cases-19-dagre --layout dagre --scale 1
bash scripts/render.sh tests/layout-cases/19-cross-group-connections.mmd artifacts/cases-19-elk --layout elk --scale 1
bash scripts/render.sh tests/layout-cases/19-cross-group-connections.mmd artifacts/cases-19-auto --layout auto --scale 1
```

Khi so sánh hai engine, hãy chỉ định trực tiếp `dagre` và `elk`. `auto` chỉ chạy engine đã chọn, không chạy cả hai. Mặc định không truyền `--layout` vẫn là Dagre.

Quan sát: thứ tự đọc; khối chồng nhau; dây xuyên node/tiêu đề; nhãn đè nhau; cạnh trùng hoặc quá sát; số góc; đường quay lại; khoảng trống; tỷ lệ rộng/cao và thời gian render. Số node lớn không đồng nghĩa thuật toán chắc chắn bố trí xấu.

## Các cặp kiểm tra auto

Theo chính sách hiện tại: chọn ELK nếu có ít nhất 25 node, 35 cạnh, 3 subgraph hoặc độ sâu nhóm từ 2; còn lại chọn Dagre.

| Cặp | Dưới ngưỡng → Dagre | Chạm ngưỡng → ELK |
|---|---|---|
| Node | `29`: 24 node | `30`: 25 node |
| Cạnh | `31`: 34 cạnh, 13 node | `32`: 35 cạnh, 13 node |
| Số nhóm | `33`: 2 nhóm, sâu 1 cấp | `34`: 3 nhóm, sâu 1 cấp |
| Độ sâu | `35`: 1 nhóm, sâu 1 cấp | `36`: 2 nhóm, sâu 2 cấp |

Các cặp được thiết kế để các tiêu chí còn lại đều dưới ngưỡng.

## Danh mục

| File | Nội dung | Mục tiêu quan sát |
|---|---|---|
| [01-single-node.mmd](01-single-node.mmd) | Một node | Kích thước và căn nhãn cơ bản |
| [02-short-chain.mmd](02-short-chain.mmd) | Chuỗi ngắn | Thứ tự đọc và khoảng cách |
| [03-decision.mmd](03-decision.mmd) | Một điều kiện | Nhãn cạnh và hai nhánh |
| [04-diamond-join.mmd](04-diamond-join.mmd) | Tách rồi nhập nhánh | Bố cục hình thoi |
| [05-fan-out.mmd](05-fan-out.mmd) | Một nguồn nhiều đích | Độ rộng khi tách nhánh |
| [06-fan-in.mmd](06-fan-in.mmd) | Nhiều nguồn một đích | Hội tụ đường dây |
| [07-independent-nodes.mmd](07-independent-nodes.mmd) | Các node độc lập | Đóng gói không có cạnh |
| [08-disconnected-components.mmd](08-disconnected-components.mmd) | Ba thành phần rời | Khoảng cách giữa thành phần |
| [09-mixed-shapes-labels.mmd](09-mixed-shapes-labels.mmd) | Hình dạng và nhãn dài | Node lớn nhỏ và nhãn nhiều dòng |
| [10-long-chain-td.mmd](10-long-chain-td.mmd) | Chuỗi dài TD | Tránh kéo hình quá cao |
| [11-long-chain-lr.mmd](11-long-chain-lr.mmd) | Chuỗi dài LR | Tránh kéo hình quá ngang |
| [12-binary-tree.mmd](12-binary-tree.mmd) | Cây phân nhánh ba tầng | Cân đối nhánh |
| [13-repeated-diamonds.mmd](13-repeated-diamonds.mmd) | Nhiều lần tách và nhập | Dây và nhãn qua nhiều tầng |
| [14-feedback-cycle.mmd](14-feedback-cycle.mmd) | Chu trình phản hồi | Cạnh quay lại và thứ tự đọc |
| [15-parallel-edges.mmd](15-parallel-edges.mmd) | Cạnh song song cùng đầu cuối | Khoảng cách dây và nhãn độc lập |
| [16-self-loops.mmd](16-self-loops.mmd) | Cạnh tự nối | Self-loop và cạnh phản hồi |
| [17-two-groups.mmd](17-two-groups.mmd) | Hai nhóm | Đầu nối xuyên khung |
| [18-nested-groups.mmd](18-nested-groups.mmd) | Nhóm lồng hai cấp | Padding tiêu đề và cạnh xuyên cấp |
| [19-cross-group-connections.mmd](19-cross-group-connections.mmd) | Nhiều cạnh chéo nhóm | Đầu nối bên trong và đường đi xuyên khung |
| [20-unequal-groups.mmd](20-unequal-groups.mmd) | Nhóm có kích thước khác nhau | Cân đối khối lớn và khối nhỏ |
| [21-six-stage-pipeline.mmd](21-six-stage-pipeline.mmd) | Pipeline sáu khối | Bố trí theo dây thay vì hết hàng |
| [22-mesh-4x4.mmd](22-mesh-4x4.mmd) | Lưới kết nối 4 × 4 | Nhiều nút có hai đầu vào và hai đầu ra |
| [23-retry-workflow.mmd](23-retry-workflow.mmd) | Luồng có retry và xử lý lỗi | Nhãn cạnh và đường quay lại nhiều nhóm |
| [24-three-level-nesting.mmd](24-three-level-nesting.mmd) | Nhóm lồng ba cấp | Tích lũy khung và đường xuyên nhiều cấp |
| [25-mesh-6x6.mmd](25-mesh-6x6.mmd) | Lưới kết nối 6 × 6 | Kiểm tra độ dày dây và thời gian xử lý |
| [26-dense-feedback.mmd](26-dense-feedback.mmd) | Chuỗi nhiều cạnh tắt và phản hồi | Stress đường dài và nhiều vòng lặp |
| [27-wide-fork-join.mmd](27-wide-fork-join.mmd) | Tách 22 nhánh rồi hội tụ | Stress độ rộng và vùng hội tụ |
| [28-real-chat-flow.mmd](28-real-chat-flow.mmd) | Luồng chat thực tế | Bản sao nguyên vẹn chat_flow.mmd tại thời điểm tạo bộ mẫu |
| [29-boundary-nodes-24.mmd](29-boundary-nodes-24.mmd) | 24 node: dưới ngưỡng node | auto dự kiến chọn Dagre |
| [30-boundary-nodes-25.mmd](30-boundary-nodes-25.mmd) | 25 node: chạm ngưỡng node | auto dự kiến chọn ELK |
| [31-boundary-edges-34.mmd](31-boundary-edges-34.mmd) | 34 cạnh: dưới ngưỡng cạnh | auto dự kiến chọn Dagre; 13 node |
| [32-boundary-edges-35.mmd](32-boundary-edges-35.mmd) | 35 cạnh: chạm ngưỡng cạnh | auto dự kiến chọn ELK; 13 node |
| [33-boundary-groups-2.mmd](33-boundary-groups-2.mmd) | Hai nhóm: dưới ngưỡng nhóm | auto dự kiến chọn Dagre |
| [34-boundary-groups-3.mmd](34-boundary-groups-3.mmd) | Ba nhóm: chạm ngưỡng nhóm | auto dự kiến chọn ELK |
| [35-boundary-depth-1.mmd](35-boundary-depth-1.mmd) | Nhóm sâu một cấp | auto dự kiến chọn Dagre |
| [36-boundary-depth-2.mmd](36-boundary-depth-2.mmd) | Nhóm sâu hai cấp | auto dự kiến chọn ELK |

`manifest.json` chứa danh mục có cấu trúc để dùng khi viết công cụ chạy batch.

## Kiểm tra đầu vào

Cả 36 file đã render thành công với `--layout auto` bằng runtime hiện tại; 8 file sát ngưỡng đều chọn đúng engine nêu trên. [Báo cáo lần chạy](../../artifacts/layout-cases-smoke/report.json) ghi số node/cạnh/nhóm, engine đã chọn, kích thước và thời gian render. Kết quả này xác nhận khả năng render ở chế độ `auto`, chưa phải đánh giá chất lượng thẩm mỹ hay xác nhận cả hai engine cho từng file.
