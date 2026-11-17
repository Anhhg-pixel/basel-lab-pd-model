"""Bước 6: so sánh RWA theo phương pháp chuẩn (SA) và theo IRB trên cùng danh mục.

Phạm vi: khoản vay chưa default tại 31/10/2026. Hệ số rủi ro SA lấy bình quân theo sản phẩm
từ file Excel; LGD là giả định (xem LGD trong b5). Kết quả chỉ để minh họa cơ chế, không phản ánh
một ngân hàng thật.

Chạy riêng:  python src/b6_irb_rwa.py
"""
import numpy as np
import pandas as pd

from b4_chuan_bi_du_lieu import OUT, load_raw
from b5_mo_hinh_pd import ecl_current_book, fit_model
from irb_risk_weight import (r_corporate, r_hvcre, r_mortgage, r_other_retail, r_qrre,
                             risk_weight)

# Hệ số rủi ro SA bình quân theo sản phẩm, lấy từ file excel/rwa_car_phuong_phap_chuan.xlsx
# (sheet TongHop: đã tính LTV, CCF, tài sản bảo đảm bằng tiền gửi theo CRE20-22)
RW_SA = {"Mortgage": 0.3375, "Consumer": 0.7060, "CreditCard": 0.7911, "SME_Term": 0.7838,
         "SME_Overdraft": 0.8827, "Corp_Term": 0.8667, "Project_ADC": 1.3142}
PD_FLOOR = {"CreditCard": 0.001}        # QRRE 0,10%; còn lại 0,05% (CRE32)
EUR_VND_MIO = 28_000                    # 1 triệu EUR ~ 28.000 triệu đồng (giả định)
OUTPUT_FLOOR = 0.725


def irb_rw(row):
    pd_ = max(row["pd12"], PD_FLOOR.get(row["product"], 0.0005))
    lgd, p = row["lgd"], row["product"]
    if p == "Mortgage":
        return risk_weight(pd_, lgd, r_mortgage(pd_))
    if p == "CreditCard":
        return risk_weight(pd_, lgd, r_qrre(pd_))
    if p == "Consumer":
        return risk_weight(pd_, lgd, r_other_retail(pd_))
    if p == "Project_ADC":
        return risk_weight(pd_, lgd, r_hvcre(pd_), m=2.5)
    sales = row["annual_revenue"] / EUR_VND_MIO if pd.notna(row["annual_revenue"]) else None
    return risk_weight(pd_, lgd, r_corporate(pd_, sales_mio_eur=sales), m=2.5)


def compare(r):
    book = ecl_current_book(r)
    cust = load_raw()[0].drop_duplicates("customer_id").set_index("customer_id")
    book["annual_revenue"] = book["customer_id"].map(cust["annual_revenue"])

    book["rwa_sa"] = book["product"].map(RW_SA) * book["ead"]
    book["rw_irb"] = book.apply(irb_rw, axis=1)
    book["rwa_irb"] = book["rw_irb"] * book["ead"]

    by = book.groupby("product")[["ead", "rwa_sa", "rwa_irb"]].sum()
    by["irb_tren_sa"] = by["rwa_irb"] / by["rwa_sa"]
    total = by[["ead", "rwa_sa", "rwa_irb"]].sum()
    return book, by, total


if __name__ == "__main__":
    r = fit_model()
    book, by, total = compare(r)
    ratio = total["rwa_irb"] / total["rwa_sa"]
    floor = OUTPUT_FLOOR * total["rwa_sa"]
    print(by.round(2).to_string())
    print(f"\nTổng RWA SA : {total['rwa_sa']:,.0f} triệu")
    print(f"Tổng RWA IRB: {total['rwa_irb']:,.0f} triệu ({ratio:.1%} SA)")
    print(f"Output floor 72,5% SA = {floor:,.0f} triệu -> "
          f"{'chạm sàn' if total['rwa_irb'] < floor else 'không chạm sàn'}")
    by.round(4).to_csv(OUT / "rwa_sa_vs_irb.csv", encoding="utf-8-sig")
