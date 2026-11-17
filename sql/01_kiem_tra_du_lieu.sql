-- Kiểm tra chất lượng dữ liệu và bức tranh danh mục
-- Dữ liệu: customers, loans, loan_snapshots (đơn vị: triệu đồng)


-- 1. Số dòng mỗi bảng
SELECT 'customers' AS bang, COUNT(*) AS so_dong FROM customers
UNION ALL
SELECT 'loans', COUNT(*) FROM loans
UNION ALL
SELECT 'loan_snapshots', COUNT(*) FROM loan_snapshots;


-- 2. Dư nợ và tỷ trọng theo sản phẩm
SELECT
    product,
    COUNT(*)         AS so_khoan_vay,
    SUM(outstanding) AS tong_du_no,
    ROUND(100.0 * SUM(outstanding) / (SELECT SUM(outstanding) FROM loans), 1) AS ty_trong_pct
FROM loans
GROUP BY product
ORDER BY tong_du_no DESC;


-- 3a. Lỗi: dư nợ âm
SELECT loan_id, product, outstanding
FROM loans
WHERE outstanding < 0;

-- 3b. Lỗi: có tài sản bảo đảm là BĐS nhưng thiếu giá trị
SELECT loan_id, product, collateral_type, collateral_value
FROM loans
WHERE collateral_type = 'RealEstate'
  AND collateral_value IS NULL;

-- 3c. Lỗi: ngày đáo hạn trước ngày giải ngân
SELECT loan_id, disbursement_date, maturity_date
FROM loans
WHERE maturity_date < disbursement_date;

-- 3d. Lỗi: khách hàng bị trùng
SELECT customer_id, COUNT(*) AS so_lan_xuat_hien
FROM customers
GROUP BY customer_id
HAVING COUNT(*) > 1;

-- 3e. Lỗi: khoản vay không tìm thấy khách hàng
SELECT l.loan_id, l.customer_id, l.outstanding
FROM loans AS l
LEFT JOIN customers AS c ON c.customer_id = l.customer_id
WHERE c.customer_id IS NULL;


-- 4. Dư nợ theo nhóm nợ (Thông tư 31/2024) tại 31/10/2026
SELECT
    CASE
        WHEN dpd < 10   THEN '1 - Du tieu chuan'
        WHEN dpd <= 90  THEN '2 - Can chu y'
        WHEN dpd <= 180 THEN '3 - Duoi tieu chuan'
        WHEN dpd <= 360 THEN '4 - Nghi ngo'
        ELSE                 '5 - Co kha nang mat von'
    END              AS nhom_no,
    COUNT(*)         AS so_khoan_vay,
    SUM(outstanding) AS tong_du_no
FROM loan_snapshots
WHERE snapshot_date = '2026-10-31'
GROUP BY nhom_no
ORDER BY nhom_no;

-- Tỷ lệ nợ xấu (nhóm 3-5)
SELECT
    ROUND(100.0 * SUM(CASE WHEN dpd > 90 THEN outstanding ELSE 0 END) / SUM(outstanding), 2) AS npl_pct
FROM loan_snapshots
WHERE snapshot_date = '2026-10-31';


-- 5. EAD của hạn mức chưa giải ngân (CCF theo phương pháp chuẩn)
SELECT
    product,
    SUM(outstanding) AS tong_du_no,
    ROUND(SUM(outstanding + (limit_amt - outstanding)
              * CASE WHEN product = 'CreditCard' THEN 0.10 ELSE 0.40 END), 0) AS tong_ead
FROM loans
WHERE product IN ('CreditCard', 'SME_Overdraft', 'Project_ADC')
  AND outstanding > 0
GROUP BY product;


-- 6. Dư nợ theo phân khúc: khử trùng khách hàng trước khi JOIN
--    (JOIN thẳng sẽ đếm hai lần khoản vay của khách bị trùng)
WITH customers_clean AS (
    SELECT DISTINCT customer_id, segment
    FROM customers
)
SELECT c.segment, SUM(l.outstanding) AS tong_du_no
FROM loans AS l
JOIN customers_clean AS c ON c.customer_id = l.customer_id
WHERE l.outstanding > 0
GROUP BY c.segment;

-- Đối chiếu: tổng trên phải bằng tổng dư nợ hợp lệ của các khoản vay có khách hàng
SELECT SUM(outstanding) AS tong_kiem_soat
FROM loans
WHERE outstanding > 0
  AND customer_id IN (SELECT customer_id FROM customers);


-- 7. Nhóm nợ Việt Nam so với stage IFRS 9 tại 31/10/2026
SELECT
    CASE
        WHEN dpd < 10   THEN 1
        WHEN dpd <= 90  THEN 2
        WHEN dpd <= 180 THEN 3
        WHEN dpd <= 360 THEN 4
        ELSE 5
    END              AS nhom_no,
    CASE
        WHEN dpd <= 30 THEN 'Stage 1'
        WHEN dpd <= 90 THEN 'Stage 2'
        ELSE                'Stage 3'
    END              AS ifrs9_stage,
    COUNT(*)         AS so_khoan_vay,
    SUM(outstanding) AS tong_du_no
FROM loan_snapshots
WHERE snapshot_date = '2026-10-31'
GROUP BY nhom_no, ifrs9_stage
ORDER BY nhom_no, ifrs9_stage;
