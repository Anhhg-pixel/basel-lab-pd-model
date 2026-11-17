"""
CRE31 – IRB risk weight functions (Basel III).
Tính K (capital requirement) và risk weight cho từng asset class.

Cách dùng:  python irb_risk_weight.py
"""
import numpy as np
from scipy.stats import norm

N = norm.cdf      # N(x): hàm phân phối chuẩn tắc       (Excel: NORM.S.DIST(x,TRUE))
G = norm.ppf      # G(z): nghịch đảo của N              (Excel: NORM.S.INV(z))


# ---------------------------------------------------------------- tương quan R
def r_corporate(pd, sales_mio_eur=None, large_fi=False):
    """CRE31.5 (+ điều chỉnh SME CRE31.8, + hệ số 1.25 cho tổ chức tài chính CRE31.7)"""
    w = (1 - np.exp(-50 * pd)) / (1 - np.exp(-50))
    r = 0.12 * w + 0.24 * (1 - w)
    if sales_mio_eur is not None and sales_mio_eur < 50:          # SME
        s = min(max(sales_mio_eur, 5), 50)
        r -= 0.04 * (1 - (s - 5) / 45)
    if large_fi:
        r *= 1.25
    return r


def r_hvcre(pd):
    """CRE31.11"""
    w = (1 - np.exp(-50 * pd)) / (1 - np.exp(-50))
    return 0.12 * w + 0.30 * (1 - w)


def r_mortgage(pd):
    """CRE31.14"""
    return 0.15


def r_qrre(pd):
    """CRE31.15"""
    return 0.04


def r_other_retail(pd):
    """CRE31.16"""
    w = (1 - np.exp(-35 * pd)) / (1 - np.exp(-35))
    return 0.03 * w + 0.16 * (1 - w)


# ---------------------------------------------------------------- K và RWA
def k_capital(pd, lgd, r, m=None):
    """
    K = [LGD * N( G(PD)/sqrt(1-R) + sqrt(R/(1-R)) * G(0.999) ) - PD*LGD] * MA
    MA (maturity adjustment) chỉ áp cho corporate/sovereign/bank (CRE31.5-31.6);
    retail không có M (CRE31.13).
    """
    cond_pd = N(G(pd) / np.sqrt(1 - r) + np.sqrt(r / (1 - r)) * G(0.999))
    k = lgd * cond_pd - pd * lgd
    if m is not None:
        b = (0.11852 - 0.05478 * np.log(pd)) ** 2
        k *= (1 + (m - 2.5) * b) / (1 - 1.5 * b)
    return k


def risk_weight(pd, lgd, r, m=None):
    """RW = K * 12.5 ;  RWA = RW * EAD"""
    return k_capital(pd, lgd, r, m) * 12.5


def k_defaulted(lgd, el_best_estimate):
    """CRE31.3: khoản vay đã vỡ nợ"""
    return max(0.0, lgd - el_best_estimate)


# ---------------------------------------------------------------- demo
if __name__ == "__main__":
    pds = [0.0003, 0.001, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20]
    print(f"{'PD':>7} | {'Corp':>7} {'SME 10m':>8} {'FI x1.25':>8} | "
          f"{'Mortgage':>8} {'QRRE':>7} {'OthRetail':>9}")
    print(f"{'':>7} | LGD 45%, M = 2.5 năm      | LGD 25%  LGD 45%  LGD 45%")
    for pd in pds:
        corp = risk_weight(pd, 0.45, r_corporate(pd), m=2.5)
        sme = risk_weight(pd, 0.45, r_corporate(pd, sales_mio_eur=10), m=2.5)
        fi = risk_weight(pd, 0.45, r_corporate(pd, large_fi=True), m=2.5)
        mort = risk_weight(pd, 0.25, r_mortgage(pd))
        qrre = risk_weight(pd, 0.45, r_qrre(pd))
        oth = risk_weight(pd, 0.45, r_other_retail(pd))
        print(f"{pd:7.2%} | {corp:7.1%} {sme:8.1%} {fi:8.1%} | "
              f"{mort:8.1%} {qrre:7.1%} {oth:9.1%}")

    # Ví dụ một khoản vay doanh nghiệp 100 tỷ
    pd, lgd, ead, m = 0.02, 0.40, 100_000, 2.5          # EAD: triệu đồng
    r = r_corporate(pd)
    k = k_capital(pd, lgd, r, m)
    print("\nVí dụ: cho doanh nghiệp vay 100 tỷ, PD 2%, LGD 40%, M 2.5 năm")
    print(f"  R  = {r:.4f}")
    print(f"  K  = {k:.4%}  -> vốn tối thiểu = {k*ead:,.0f} triệu đồng")
    print(f"  RW = {k*12.5:.1%}  -> RWA = {k*12.5*ead:,.0f} triệu đồng")
    print(f"  EL = PD x LGD x EAD = {pd*lgd*ead:,.0f} triệu đồng (do dự phòng gánh, CRE35)")
