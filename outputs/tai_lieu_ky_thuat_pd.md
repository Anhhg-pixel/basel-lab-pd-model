# Tài liệu kỹ thuật: mô hình PD 6 tháng (Basel Lab)

## 1. Mục đích và phạm vi
Ước lượng xác suất một khoản vay chưa default chuyển sang default (dpd > 90) trong 6 tháng tới.
Dữ liệu là ngân hàng mô phỏng, không phải dữ liệu thật.

## 2. Dữ liệu và định nghĩa
- Mốc quan sát: 2026-04-30. Biến chỉ dùng thông tin đến mốc này (6 tháng gần nhất).
- Nhãn: default = 1 nếu dpd > 90 trong 6 tháng sau mốc quan sát.
- Mẫu: 2,225 khoản vay, 45 default (2.02%).
- Chia train/test 70/30 phân tầng theo nhãn: 31 default ở train, 14 ở test.

## 3. Chọn biến
Biến được chia nhóm và mã hóa WoE = ln(%Good/%Bad). Giữ biến có IV >= 0,02, sau đó loại dần biến có
hệ số logistic sai dấu.

| Biến | IV | Trong mô hình |
|---|---|---|
| dpd_hien_tai | 2.538 | Có |
| so_thang_qua_han_6t | 1.712 | Không |
| max_dpd_6t | 1.642 | Không |
| product | 0.509 | Có |
| lai_suat | 0.327 | Có |
| ltv | 0.240 | Có |
| tuoi_khoan_vay_thang | 0.145 | Có |
| thu_nhap_thang | 0.088 | Có |
| segment | 0.071 | Có |
| ty_le_su_dung | 0.000 | Không |

IV của `dpd_hien_tai` trên 0,5 là bình thường với mô hình hành vi (khoản đang quá hạn dễ default hơn),
không phải dấu hiệu rò rỉ: biến này chỉ dùng dpd tại mốc quan sát.

## 4. Mô hình

| Biến | Hệ số |
|---|---|
| dpd_hien_tai | -0.992 |
| product | -0.367 |
| lai_suat | -0.568 |
| ltv | -0.546 |
| tuoi_khoan_vay_thang | -0.941 |
| thu_nhap_thang | -1.011 |
| segment | -0.159 |

Thang điểm: 600 điểm tại odds 50:1, PDO = 20.

## 5. Kiểm định

**Khả năng phân biệt**

| | AUC | Gini | KS |
|---|---|---|---|
| Train | 0.890 | 0.779 | 0.708 |
| Test | 0.699 | 0.399 | 0.331 |

Khoảng tin cậy 95% của AUC test (bootstrap): 0.566 – 0.829.

**Hiệu chuẩn theo hạng (tập test, kiểm định nhị thức một phía)**

| Hạng | Số khoản | Default | PD bình quân | ODR | p-value | Kết quả |
|---|---|---|---|---|---|---|
| 1 | 111 | 0 | 0.14% | 0.00% | 1.000 | Đạt |
| 2 | 147 | 2 | 0.43% | 1.36% | 0.133 | Đạt |
| 3 | 134 | 4 | 0.77% | 2.99% | 0.020 | Không đạt |
| 4 | 137 | 2 | 1.22% | 1.46% | 0.497 | Đạt |
| 5 | 139 | 6 | 8.26% | 4.32% | 0.976 | Đạt |

**Ổn định**: PSI giữa điểm tập train và danh mục tại 31/10/2026 = 0.005 (ổn định).

## 6. Hạn chế
- Tập test chỉ có 14 default nên AUC test dao động mạnh; khoảng tin cậy rộng.
- Chưa kiểm định out-of-time vì dữ liệu chỉ có 12 tháng.
- PD 12 tháng quy đổi từ PD 6 tháng bằng giả định rủi ro đều; LGD là giả định theo loại tài sản bảo đảm.
