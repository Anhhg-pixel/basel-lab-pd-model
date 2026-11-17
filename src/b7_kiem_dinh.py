"""Bước 7: kiểm định mô hình PD và viết tài liệu kỹ thuật.

Gồm: khoảng tin cậy AUC, kiểm định nhị thức PD theo hạng, PSI giữa tập phát triển và danh mục
hiện tại. Kết quả ghi vào outputs/tai_lieu_ky_thuat_pd.md.

Chạy riêng:  python src/b7_kiem_dinh.py
"""
import numpy as np
import pandas as pd
from scipy.stats import binom

from b4_chuan_bi_du_lieu import FEATURES, OBS_DATE, OUT
from b5_mo_hinh_pd import ecl_current_book, fit_model, score_from_pd
from woe import auc_ci, gini_ks, psi

N_GRADES = 5


def master_scale(r):
    """Chia 5 hạng theo điểm trên tập train (hạng 1 = an toàn nhất)."""
    s_tr = score_from_pd(r["p_tr"])
    edges = np.unique(np.quantile(s_tr, np.linspace(0, 1, N_GRADES + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    return edges


def binomial_by_grade(r, edges):
    """Với mỗi hạng: PD bình quân dự báo so với tỷ lệ default thực tế trên tập test.

    p-value một phía = P(số default >= số quan sát | PD dự báo). p < 5% nghĩa là mô hình
    đánh giá thấp rủi ro của hạng đó.
    """
    df = pd.DataFrame({"score": score_from_pd(r["p_te"]), "pd": r["p_te"], "y": r["y_te"].values})
    labels = list(range(N_GRADES, 0, -1))           # điểm thấp -> hạng 5 (rủi ro nhất)
    df["hang"] = pd.cut(df["score"], edges, labels=labels[:len(edges) - 1])
    t = df.groupby("hang", observed=True).agg(so_khoan=("y", "size"), default=("y", "sum"),
                                              pd_tb=("pd", "mean"))
    t["odr"] = t["default"] / t["so_khoan"]
    t["p_value"] = [binom.sf(d - 1, n, p) for d, n, p in zip(t["default"], t["so_khoan"], t["pd_tb"])]
    t["ket_qua"] = np.where(t["p_value"] < 0.05, "Không đạt", "Đạt")
    t.index = t.index.astype(int)
    return t.sort_index()


def run():
    r = fit_model()
    m_tr, m_te = gini_ks(r["y_tr"], r["p_tr"]), gini_ks(r["y_te"], r["p_te"])
    lo, hi = auc_ci(r["y_te"], r["p_te"])
    edges = master_scale(r)
    grades = binomial_by_grade(r, edges)

    book = ecl_current_book(r)
    psi_val = psi(score_from_pd(r["p_tr"]), book["score"], edges)
    psi_note = "ổn định" if psi_val < 0.1 else ("cần theo dõi" if psi_val < 0.25 else "lệch đáng kể")

    return dict(r=r, m_tr=m_tr, m_te=m_te, ci=(lo, hi), grades=grades, psi=psi_val,
                psi_note=psi_note, book=book)


def write_doc(v):
    r, g = v["r"], v["grades"]
    coef = pd.Series(r["model"].coef_[0], index=r["selected"])
    iv_tbl = "\n".join(f"| {k} | {val:.3f} | {'Có' if k in r['selected'] else 'Không'} |"
                       for k, val in r["iv"].items())
    coef_tbl = "\n".join(f"| {k} | {val:.3f} |" for k, val in coef.items())
    g_tbl = "\n".join(f"| {h} | {row.so_khoan} | {row.default} | {row.pd_tb:.2%} | {row.odr:.2%} | "
                      f"{row.p_value:.3f} | {row.ket_qua} |" for h, row in g.iterrows())
    lo, hi = v["ci"]
    doc = f"""# Tài liệu kỹ thuật: mô hình PD 6 tháng (Basel Lab)

## 1. Mục đích và phạm vi
Ước lượng xác suất một khoản vay chưa default chuyển sang default (dpd > 90) trong 6 tháng tới.
Dữ liệu là ngân hàng mô phỏng, không phải dữ liệu thật.

## 2. Dữ liệu và định nghĩa
- Mốc quan sát: {OBS_DATE}. Biến chỉ dùng thông tin đến mốc này (6 tháng gần nhất).
- Nhãn: default = 1 nếu dpd > 90 trong 6 tháng sau mốc quan sát.
- Mẫu: {len(r['data']):,} khoản vay, {int(r['data']['default'].sum())} default ({r['data']['default'].mean():.2%}).
- Chia train/test 70/30 phân tầng theo nhãn: {int(r['y_tr'].sum())} default ở train, {int(r['y_te'].sum())} ở test.

## 3. Chọn biến
Biến được chia nhóm và mã hóa WoE = ln(%Good/%Bad). Giữ biến có IV >= 0,02, sau đó loại dần biến có
hệ số logistic sai dấu.

| Biến | IV | Trong mô hình |
|---|---|---|
{iv_tbl}

IV của `dpd_hien_tai` trên 0,5 là bình thường với mô hình hành vi (khoản đang quá hạn dễ default hơn),
không phải dấu hiệu rò rỉ: biến này chỉ dùng dpd tại mốc quan sát.

## 4. Mô hình

| Biến | Hệ số |
|---|---|
{coef_tbl}

Thang điểm: 600 điểm tại odds 50:1, PDO = 20.

## 5. Kiểm định

**Khả năng phân biệt**

| | AUC | Gini | KS |
|---|---|---|---|
| Train | {v['m_tr']['auc']:.3f} | {v['m_tr']['gini']:.3f} | {v['m_tr']['ks']:.3f} |
| Test | {v['m_te']['auc']:.3f} | {v['m_te']['gini']:.3f} | {v['m_te']['ks']:.3f} |

Khoảng tin cậy 95% của AUC test (bootstrap): {lo:.3f} – {hi:.3f}.

**Hiệu chuẩn theo hạng (tập test, kiểm định nhị thức một phía)**

| Hạng | Số khoản | Default | PD bình quân | ODR | p-value | Kết quả |
|---|---|---|---|---|---|---|
{g_tbl}

**Ổn định**: PSI giữa điểm tập train và danh mục tại 31/10/2026 = {v['psi']:.3f} ({v['psi_note']}).

## 6. Hạn chế
- Tập test chỉ có {int(r['y_te'].sum())} default nên AUC test dao động mạnh; khoảng tin cậy rộng.
- Chưa kiểm định out-of-time vì dữ liệu chỉ có 12 tháng.
- PD 12 tháng quy đổi từ PD 6 tháng bằng giả định rủi ro đều; LGD là giả định theo loại tài sản bảo đảm.
"""
    (OUT / "tai_lieu_ky_thuat_pd.md").write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    v = run()
    print(f"Train Gini {v['m_tr']['gini']:.3f} | Test Gini {v['m_te']['gini']:.3f}")
    print(f"AUC test 95% CI: {v['ci'][0]:.3f} – {v['ci'][1]:.3f}")
    print(v["grades"].round(4).to_string())
    print(f"PSI: {v['psi']:.3f} ({v['psi_note']})")
    write_doc(v)
    print("Đã ghi outputs/tai_lieu_ky_thuat_pd.md")
