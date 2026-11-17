-- Roll rate, cure rate, nhãn default và staging IFRS 9
-- Bảng chính: loan_snapshots (12 kỳ cuối tháng, 11/2025 -> 10/2026)
-- Nhóm nợ theo Thông tư 31/2024: dpd < 10 -> 1 | 10-90 -> 2 | 91-180 -> 3 | 181-360 -> 4 | > 360 -> 5


-- 1. Ba khoản vay lớn nhất mỗi sản phẩm và tỷ trọng trong sản phẩm (rủi ro tập trung)
WITH xep_hang AS (
    SELECT
        product,
        loan_id,
        outstanding,
        ROW_NUMBER() OVER (PARTITION BY product ORDER BY outstanding DESC) AS stt,
        SUM(outstanding) OVER (PARTITION BY product)                      AS tong_san_pham
    FROM loans
    WHERE outstanding > 0
)
SELECT
    product,
    stt,
    loan_id,
    outstanding,
    ROUND(100.0 * outstanding / tong_san_pham, 1) AS ty_trong_pct
FROM xep_hang
WHERE stt <= 3
ORDER BY product, stt;


-- 2a. Diễn biến DPD của một khoản vay
SELECT
    snapshot_date,
    dpd,
    LAG(dpd) OVER (PARTITION BY loan_id ORDER BY snapshot_date) AS dpd_thang_truoc
FROM loan_snapshots
WHERE loan_id = 'L000036'
ORDER BY snapshot_date;

-- 2b. Số lần chuyển từ đúng hạn sang quá hạn
WITH ls AS (
    SELECT
        dpd,
        LAG(dpd) OVER (PARTITION BY loan_id ORDER BY snapshot_date) AS dpd_truoc
    FROM loan_snapshots
)
SELECT COUNT(*) AS so_lan_chuyen_sang_qua_han
FROM ls
WHERE dpd_truoc = 0 AND dpd > 0;


-- 3. Ma trận chuyển nhóm nợ
WITH nhom AS (
    SELECT
        loan_id,
        snapshot_date,
        CASE
            WHEN dpd < 10   THEN 1
            WHEN dpd <= 90  THEN 2
            WHEN dpd <= 180 THEN 3
            WHEN dpd <= 360 THEN 4
            ELSE 5
        END AS nhom_no
    FROM loan_snapshots
),
chuyen AS (
    SELECT
        LAG(nhom_no) OVER (PARTITION BY loan_id ORDER BY snapshot_date) AS tu_nhom,
        nhom_no                                                         AS sang_nhom
    FROM nhom
)
SELECT
    tu_nhom,
    sang_nhom,
    COUNT(*) AS so_luot,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY tu_nhom), 2) AS ty_le_pct
FROM chuyen
WHERE tu_nhom IS NOT NULL
GROUP BY tu_nhom, sang_nhom
ORDER BY tu_nhom, sang_nhom;


-- 4. Roll rate nhóm 1 -> 2 và cure rate nhóm 2 -> 1 theo tháng
WITH nhom AS (
    SELECT
        loan_id,
        snapshot_date,
        CASE
            WHEN dpd < 10   THEN 1
            WHEN dpd <= 90  THEN 2
            WHEN dpd <= 180 THEN 3
            WHEN dpd <= 360 THEN 4
            ELSE 5
        END AS nhom_no
    FROM loan_snapshots
),
chuyen AS (
    SELECT
        snapshot_date,
        LAG(nhom_no) OVER (PARTITION BY loan_id ORDER BY snapshot_date) AS tu_nhom,
        nhom_no                                                         AS sang_nhom
    FROM nhom
)
SELECT
    snapshot_date,
    SUM(tu_nhom = 1)                                   AS dau_ky_nhom1,
    SUM(tu_nhom = 1 AND sang_nhom = 2)                 AS roi_xuong_nhom2,
    ROUND(100.0 * SUM(tu_nhom = 1 AND sang_nhom = 2)
          / NULLIF(SUM(tu_nhom = 1), 0), 2)            AS roll_rate_1_2_pct,
    SUM(tu_nhom = 2)                                   AS dau_ky_nhom2,
    SUM(tu_nhom = 2 AND sang_nhom = 1)                 AS tu_khoi,
    ROUND(100.0 * SUM(tu_nhom = 2 AND sang_nhom = 1)
          / NULLIF(SUM(tu_nhom = 2), 0), 2)            AS cure_rate_2_1_pct
FROM chuyen
WHERE tu_nhom IS NOT NULL
GROUP BY snapshot_date
ORDER BY snapshot_date;


-- 5. Default mới theo tháng (lần đầu dpd > 90), lũy kế và trung bình trượt 3 tháng
WITH lan_dau AS (
    SELECT
        loan_id,
        snapshot_date,
        ROW_NUMBER() OVER (PARTITION BY loan_id ORDER BY snapshot_date) AS stt
    FROM loan_snapshots
    WHERE dpd > 90
),
theo_thang AS (
    SELECT snapshot_date, COUNT(*) AS so_default_moi
    FROM lan_dau
    WHERE stt = 1
    GROUP BY snapshot_date
)
SELECT
    snapshot_date,
    so_default_moi,
    SUM(so_default_moi) OVER (ORDER BY snapshot_date) AS luy_ke,
    ROUND(AVG(so_default_moi) OVER (ORDER BY snapshot_date
                                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS tb_truot_3t
FROM theo_thang
ORDER BY snapshot_date;


-- 6. Tỷ lệ default quan sát (ODR) của cohort chưa default tại 30/11/2025
WITH dau_ky AS (
    SELECT s.loan_id, l.product
    FROM loan_snapshots AS s
    JOIN loans AS l ON l.loan_id = s.loan_id
    WHERE s.snapshot_date = '2025-11-30'
      AND s.dpd <= 90
),
co_default AS (
    SELECT
        loan_id,
        MAX(CASE WHEN dpd > 90 THEN 1 ELSE 0 END) AS default_flag
    FROM loan_snapshots
    WHERE snapshot_date > '2025-11-30'
    GROUP BY loan_id
),
gop AS (
    SELECT d.product, c.default_flag
    FROM dau_ky AS d
    JOIN co_default AS c ON c.loan_id = d.loan_id
)
SELECT product, COUNT(*) AS so_khoan_dau_ky, SUM(default_flag) AS so_default,
       ROUND(100.0 * SUM(default_flag) / COUNT(*), 2) AS odr_pct
FROM gop
GROUP BY product
UNION ALL
SELECT 'Toan danh muc', COUNT(*), SUM(default_flag),
       ROUND(100.0 * SUM(default_flag) / COUNT(*), 2)
FROM gop;


-- 7. Staging IFRS 9 có nhìn lại 3 tháng, so với staging chỉ theo dpd hiện tại (31/10/2026)
WITH cua_so AS (
    SELECT
        loan_id,
        snapshot_date,
        dpd,
        outstanding,
        MAX(dpd) OVER (PARTITION BY loan_id ORDER BY snapshot_date
                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS max_dpd_3t
    FROM loan_snapshots
),
stage AS (
    SELECT
        loan_id,
        outstanding,
        CASE WHEN dpd > 90 THEN 3 WHEN dpd > 30 THEN 2 ELSE 1 END        AS stage_cu,
        CASE WHEN dpd > 90 THEN 3 WHEN max_dpd_3t > 30 THEN 2 ELSE 1 END AS stage_moi
    FROM cua_so
    WHERE snapshot_date = '2026-10-31'
)
SELECT stage_cu, stage_moi, COUNT(*) AS so_khoan, ROUND(SUM(outstanding), 0) AS du_no
FROM stage
GROUP BY stage_cu, stage_moi
ORDER BY stage_cu, stage_moi;


-- 8. Tái phạm sau khi cure: nhóm 2 -> nhóm 1, rồi quay lại nhóm >= 2 trong 3 tháng sau
WITH nhom AS (
    SELECT
        loan_id,
        snapshot_date,
        CASE
            WHEN dpd < 10   THEN 1
            WHEN dpd <= 90  THEN 2
            WHEN dpd <= 180 THEN 3
            WHEN dpd <= 360 THEN 4
            ELSE 5
        END AS nhom_no
    FROM loan_snapshots
),
dien_bien AS (
    SELECT
        nhom_no,
        LAG(nhom_no)     OVER w AS nhom_truoc,
        LEAD(nhom_no, 1) OVER w AS sau_1,
        LEAD(nhom_no, 2) OVER w AS sau_2,
        LEAD(nhom_no, 3) OVER w AS sau_3
    FROM nhom
    WINDOW w AS (PARTITION BY loan_id ORDER BY snapshot_date)
)
SELECT
    COUNT(*)                                                       AS so_lan_cure,
    SUM(sau_1 >= 2 OR sau_2 >= 2 OR sau_3 >= 2)                    AS so_lan_tai_pham,
    ROUND(100.0 * SUM(sau_1 >= 2 OR sau_2 >= 2 OR sau_3 >= 2) / COUNT(*), 1) AS ty_le_tai_pham_pct
FROM dien_bien
WHERE nhom_truoc = 2
  AND nhom_no = 1
  AND sau_3 IS NOT NULL;


-- 9. Đối chiếu dư nợ giữa bảng loans và snapshot cuối kỳ
SELECT
    l.loan_id,
    l.product,
    l.outstanding AS du_no_loans,
    s.outstanding AS du_no_snapshot,
    ROUND(l.outstanding - s.outstanding, 2) AS chenh_lech
FROM loans AS l
JOIN loan_snapshots AS s
  ON s.loan_id = l.loan_id
 AND s.snapshot_date = '2026-10-31'
WHERE ABS(l.outstanding - s.outstanding) > 0.01
ORDER BY l.loan_id;
