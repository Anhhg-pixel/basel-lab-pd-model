"""Bước 4: làm sạch dữ liệu, tạo biến và nhãn default.

Mốc quan sát 30/04/2026:
- Biến: chỉ dùng thông tin đến hết 30/04/2026 (6 tháng 11/2025 -> 04/2026).
- Nhãn: default = 1 nếu dpd > 90 ở bất kỳ tháng nào từ 05/2026 đến 10/2026.
- Tập mẫu: khoản vay chưa default tại mốc quan sát (dpd <= 90).

Chạy riêng:  python src/b4_chuan_bi_du_lieu.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "bank.db"
OUT = ROOT / "outputs"

OBS_DATE = "2026-04-30"
END_DATE = "2026-10-31"
FEATURES = ["product", "segment", "dpd_hien_tai", "max_dpd_6t", "so_thang_qua_han_6t",
            "ty_le_su_dung", "ltv", "lai_suat", "tuoi_khoan_vay_thang", "thu_nhap_thang"]


def load_raw():
    with sqlite3.connect(DB) as con:
        cust = pd.read_sql("SELECT * FROM customers", con)
        loans = pd.read_sql("SELECT * FROM loans", con)
        snap = pd.read_sql("SELECT * FROM loan_snapshots", con)
    return cust, loans, snap


def clean(cust, loans, snap):
    """Trả về dữ liệu sạch và nhật ký những gì đã sửa."""
    log = []

    n = cust.duplicated("customer_id").sum()
    cust = cust.drop_duplicates("customer_id", keep="first")
    log.append(("Khách hàng trùng mã", n, "Giữ dòng đầu tiên"))

    orphan = ~loans["customer_id"].isin(cust["customer_id"])
    log.append(("Khoản vay không có khách hàng", orphan.sum(), "Loại khỏi mẫu"))
    loans = loans[~orphan].copy()
    snap = snap[snap["loan_id"].isin(loans["loan_id"])].copy()

    neg = loans["outstanding"] < 0
    last = snap[snap["snapshot_date"] == END_DATE].set_index("loan_id")["outstanding"]
    loans.loc[neg, "outstanding"] = loans.loc[neg, "loan_id"].map(last)
    log.append(("Dư nợ âm ở bảng loans", neg.sum(), "Lấy theo snapshot 31/10/2026 (khớp đối chiếu SQL)"))

    miss = loans["collateral_type"].ne("None") & loans["collateral_value"].isna()
    log.append(("Có TSBĐ nhưng thiếu giá trị", miss.sum(), "Coi như không có TSBĐ khi tính LTV"))
    loans.loc[miss, "collateral_value"] = 0.0
    loans["collateral_value"] = loans["collateral_value"].fillna(0.0)

    return cust, loans, snap, pd.DataFrame(log, columns=["loi", "so_dong", "xu_ly"])


def build_features(loans, cust, snap, as_of):
    """Biến cho mỗi khoản vay, chỉ dùng dữ liệu đến hết ngày as_of."""
    hist = snap[snap["snapshot_date"] <= as_of].sort_values(["loan_id", "snapshot_date"])
    hist = hist.groupby("loan_id").tail(6)
    g = hist.groupby("loan_id")
    cur = hist[hist["snapshot_date"] == as_of].set_index("loan_id")

    df = loans.set_index("loan_id")[["customer_id", "product", "limit_amt", "interest_rate",
                                     "collateral_type", "collateral_value", "disbursement_date"]]
    df = df.join(cur[["dpd", "outstanding"]], how="inner")
    df = df.join(cust.set_index("customer_id")[["segment", "monthly_income"]], on="customer_id")

    df["dpd_hien_tai"] = df["dpd"]
    df["max_dpd_6t"] = g["dpd"].max()
    df["so_thang_qua_han_6t"] = g["dpd"].apply(lambda s: int((s > 0).sum()))
    df["ty_le_su_dung"] = (df["outstanding"] / df["limit_amt"].replace(0, np.nan)).clip(0, 2)
    df["ltv"] = np.where(df["collateral_value"] > 0, df["outstanding"] / df["collateral_value"], np.nan)
    df["lai_suat"] = df["interest_rate"]
    df["tuoi_khoan_vay_thang"] = ((pd.to_datetime(as_of) - pd.to_datetime(df["disbursement_date"]))
                                  .dt.days / 30.44).round(0)
    df["thu_nhap_thang"] = df["monthly_income"]
    return df


def build_label(snap, obs_date, end_date):
    win = snap[(snap["snapshot_date"] > obs_date) & (snap["snapshot_date"] <= end_date)]
    return (win.groupby("loan_id")["dpd"].max() > 90).astype(int).rename("default")


def make_dataset():
    cust, loans, snap = load_raw()
    cust, loans, snap, log = clean(cust, loans, snap)

    feat = build_features(loans, cust, snap, OBS_DATE)
    feat = feat[feat["dpd"] <= 90]                       # chỉ khoản chưa default tại mốc quan sát
    data = feat.join(build_label(snap, OBS_DATE, END_DATE), how="inner")

    book = build_features(loans, cust, snap, END_DATE)    # danh mục hiện tại để chấm điểm
    return data, book, loans, log, snap


def leakage_check(data, snap):
    """Ví dụ rò rỉ: biến lấy dpd lớn nhất SAU mốc quan sát -> mô hình 'nhìn trộm' nhãn."""
    from sklearn.metrics import roc_auc_score
    future = snap[snap["snapshot_date"] > OBS_DATE].groupby("loan_id")["dpd"].max()
    x = data.index.map(future)
    return roc_auc_score(data["default"], x)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    data, book, loans, log, snap = make_dataset()
    print("Nhật ký làm sạch:\n", log.to_string(index=False))
    print(f"\nMẫu mô hình: {len(data):,} khoản vay, {data['default'].sum()} default "
          f"({data['default'].mean():.2%})")
    print("Default theo sản phẩm:\n", data.groupby("product")["default"].agg(["count", "sum", "mean"]).round(3))
    print(f"\nAUC của biến 'dpd lớn nhất sau mốc quan sát' (rò rỉ): {leakage_check(data, snap):.3f}")
    log.to_csv(OUT / "nhat_ky_lam_sach.csv", index=False, encoding="utf-8-sig")
