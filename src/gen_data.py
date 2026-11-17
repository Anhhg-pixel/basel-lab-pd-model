"""
Sinh bộ dữ liệu khoản vay giả lập cho project.
Không dùng dữ liệu thật của bất kỳ ngân hàng nào.

Đầu ra (thư mục data/):
  customers.csv, loans.csv, loan_snapshots.csv  -> dùng cho Python
  bank.db                                        -> dùng cho SQL (SQLite)
  basel_lab.xlsx                                 -> dùng cho Excel

Đơn vị tiền: triệu đồng (mVND). Snapshot cuối tháng 11/2025 -> 10/2026.
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(2026)
OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------- customers
N_CUST = 1500
segments = rng.choice(["Retail", "SME", "Corporate"], N_CUST, p=[0.80, 0.15, 0.05])
provinces = rng.choice(
    ["Ha Noi", "TP HCM", "Hai Phong", "Da Nang", "Can Tho", "Binh Duong", "Bac Ninh"],
    N_CUST, p=[0.30, 0.30, 0.08, 0.08, 0.08, 0.08, 0.08])

cust = pd.DataFrame({
    "customer_id": [f"C{i:05d}" for i in range(1, N_CUST + 1)],
    "segment": segments,
    "province": provinces,
    "open_date": pd.to_datetime("2015-01-01")
                 + pd.to_timedelta(rng.integers(0, 3800, N_CUST), unit="D"),
})
# thu nhập tháng (Retail) / doanh thu năm (SME, Corporate), triệu đồng
cust["monthly_income"] = np.where(
    cust.segment == "Retail", np.round(rng.lognormal(np.log(18), 0.5, N_CUST), 1), np.nan)
cust["annual_revenue"] = np.select(
    [cust.segment == "SME", cust.segment == "Corporate"],
    [np.round(rng.lognormal(np.log(40_000), 0.6, N_CUST), 0),
     np.round(rng.lognormal(np.log(2_500_000), 0.8, N_CUST), 0)],
    default=np.nan)
cust["is_listed"] = np.where(
    (cust.segment == "Corporate") & (rng.random(N_CUST) < 0.4), "Y", "N")
# điểm "sức khỏe" ẩn quyết định PD; không lưu ra file để mô hình không nhìn thấy
latent = rng.normal(0, 1, N_CUST)

# ---------------------------------------------------------------- loans
rows = []
lid = 1
for i, c in cust.iterrows():
    n_loans = rng.choice([1, 2, 3], p=[0.6, 0.3, 0.1])
    for _ in range(n_loans):
        seg = c.segment
        if seg == "Retail":
            product = rng.choice(["Mortgage", "Consumer", "CreditCard"], p=[0.35, 0.35, 0.30])
        elif seg == "SME":
            product = rng.choice(["SME_Term", "SME_Overdraft"], p=[0.7, 0.3])
        else:
            product = rng.choice(["Corp_Term", "Project_ADC"], p=[0.8, 0.2])

        limit_ = {
            "Mortgage": rng.lognormal(np.log(1500), 0.5),
            "Consumer": rng.lognormal(np.log(150), 0.6),
            "CreditCard": rng.choice([30, 50, 100, 200]),
            "SME_Term": rng.lognormal(np.log(5000), 0.7),
            "SME_Overdraft": rng.lognormal(np.log(2000), 0.6),
            "Corp_Term": rng.lognormal(np.log(80_000), 0.8),
            "Project_ADC": rng.lognormal(np.log(300_000), 0.6),
        }[product]
        limit_ = round(float(limit_), 0)
        util = 1.0 if product in ("Mortgage", "Consumer", "SME_Term", "Corp_Term") \
            else float(rng.uniform(0.2, 0.95))
        if product == "Project_ADC":
            util = float(rng.uniform(0.4, 1.0))  # giải ngân theo tiến độ
        outstanding = round(limit_ * util, 0)

        if product == "Mortgage":
            coll_type, coll_val = "RealEstate", round(outstanding / rng.uniform(0.45, 0.95), 0)
        elif product in ("SME_Term", "Corp_Term", "Project_ADC"):
            coll_type = rng.choice(["RealEstate", "Savings", "Shares", "None"], p=[0.6, 0.1, 0.15, 0.15])
            coll_val = 0 if coll_type == "None" else round(outstanding * rng.uniform(0.5, 1.6), 0)
        elif product == "Consumer":
            coll_type = rng.choice(["None", "Savings"], p=[0.9, 0.1])
            coll_val = 0 if coll_type == "None" else round(outstanding * rng.uniform(1.0, 1.3), 0)
        else:
            coll_type, coll_val = "None", 0

        currency = "USD" if (seg != "Retail" and rng.random() < 0.08) else "VND"
        disb = pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(rng.integers(0, 2200)))
        tenor_m = {"Mortgage": 240, "Consumer": 36, "CreditCard": 12, "SME_Term": 60,
                   "SME_Overdraft": 12, "Corp_Term": 84, "Project_ADC": 48}[product]
        rows.append(dict(
            loan_id=f"L{lid:06d}", customer_id=c.customer_id, product=product,
            branch=c.province, currency=currency,
            disbursement_date=disb.date(),
            maturity_date=(disb + pd.DateOffset(months=tenor_m)).date(),
            limit_amt=limit_, outstanding=outstanding,
            interest_rate=round(float({"Mortgage": 9, "Consumer": 18, "CreditCard": 28,
                                       "SME_Term": 11, "SME_Overdraft": 12, "Corp_Term": 8.5,
                                       "Project_ADC": 10.5}[product] + rng.normal(0, 1)), 2),
            collateral_type=coll_type, collateral_value=coll_val,
            _latent=latent[i]))
        lid += 1

loans = pd.DataFrame(rows)

# ---------------------------------------------------------------- snapshots (DPD theo tháng)
months = pd.date_range("2025-11-30", "2026-10-31", freq="ME")
base_pd = {"Mortgage": 0.012, "Consumer": 0.05, "CreditCard": 0.06, "SME_Term": 0.035,
           "SME_Overdraft": 0.04, "Corp_Term": 0.012, "Project_ADC": 0.05}
snap = []
for _, L in loans.iterrows():
    # PD năm phụ thuộc sản phẩm + sức khỏe ẩn của khách
    pd_year = base_pd[L["product"]] * np.exp(-0.9 * L["_latent"])
    pd_month = 1 - (1 - min(pd_year, 0.6)) ** (1 / 12)
    dpd = 0 if rng.random() > 0.03 else int(rng.choice([5, 15, 35]))
    defaulted = False
    for m in months:
        if defaulted or dpd > 0:
            # đang trễ: 70% trễ thêm, 30% chữa khỏi (cure)
            if defaulted or rng.random() < 0.70:
                dpd += 30
            else:
                dpd = 0
        elif rng.random() < pd_month * 2.2:
            dpd = int(rng.choice([1, 10, 20]))
        if dpd > 90:
            defaulted = True
        snap.append((L.loan_id, m.date(), dpd, L.outstanding))
snaps = pd.DataFrame(snap, columns=["loan_id", "snapshot_date", "dpd", "outstanding"])

# ---------------------------------------------------------------- cài lỗi dữ liệu (để kiểm tra quy trình làm sạch)
cust = cust.drop(columns=[])
dup = cust.sample(6, random_state=1)                     # 1) khách hàng bị trùng
cust = pd.concat([cust, dup], ignore_index=True)
idx = cust[cust.segment == "Retail"].sample(25, random_state=2).index
cust.loc[idx, "monthly_income"] = np.nan                  # 2) thiếu thu nhập
bad = loans.sample(4, random_state=3).index
loans.loc[bad, "outstanding"] = -loans.loc[bad, "outstanding"]   # 3) dư nợ âm
bad2 = loans[loans.collateral_type == "RealEstate"].sample(5, random_state=4).index
loans.loc[bad2, "collateral_value"] = np.nan              # 4) TSBĐ thiếu giá trị
orphan = loans.sample(3, random_state=5).copy()           # 5) khoản vay "mồ côi"
orphan["loan_id"] = [f"L9{i:05d}" for i in range(3)]
orphan["customer_id"] = ["C99901", "C99902", "C99903"]
loans = pd.concat([loans, orphan], ignore_index=True)
bad3 = loans.sample(3, random_state=6).index              # 6) đáo hạn trước giải ngân
loans.loc[bad3, "maturity_date"] = pd.to_datetime(loans.loc[bad3, "disbursement_date"]) \
    .sub(pd.Timedelta(days=30)).dt.date

loans_public = loans.drop(columns=["_latent"])

# ---------------------------------------------------------------- xuất file
cust.to_csv(OUT / "customers.csv", index=False)
loans_public.to_csv(OUT / "loans.csv", index=False)
snaps.to_csv(OUT / "loan_snapshots.csv", index=False)

db = OUT / "bank.db"
db.unlink(missing_ok=True)
with sqlite3.connect(db) as con:
    cust.to_sql("customers", con, index=False)
    loans_public.to_sql("loans", con, index=False)
    snaps.to_sql("loan_snapshots", con, index=False)

with pd.ExcelWriter(OUT / "basel_lab.xlsx", engine="openpyxl") as xw:
    cust.to_excel(xw, sheet_name="customers", index=False)
    loans_public.to_excel(xw, sheet_name="loans", index=False)
    snaps[snaps.snapshot_date == months[-1].date()].to_excel(
        xw, sheet_name="snapshot_2026_10", index=False)

print(len(cust), "customers |", len(loans_public), "loans |", len(snaps), "snapshot rows")
print(loans_public.groupby("product").outstanding.agg(["count", "sum"]).round(0))
last = snaps[snaps.snapshot_date == months[-1].date()]
print("NPL (dpd>90) ratio by balance, 10/2026:",
      round(last.loc[last.dpd > 90, "outstanding"].sum() / last.outstanding.abs().sum(), 4))
