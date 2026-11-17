"""Bước 5: mô hình PD bằng WoE + logistic regression, thang điểm và ECL.

Chạy riêng:  python src/b5_mo_hinh_pd.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve
from sklearn.model_selection import train_test_split

from b4_chuan_bi_du_lieu import FEATURES, OUT, make_dataset
from woe import WoeEncoder, gini_ks

IV_MIN = 0.02
SEED = 42

# Thang điểm: 600 điểm tại odds Good:Bad = 50:1, cứ 20 điểm odds tăng gấp đôi
PDO, BASE_SCORE, BASE_ODDS = 20, 600, 50
FACTOR = PDO / np.log(2)
OFFSET = BASE_SCORE - FACTOR * np.log(BASE_ODDS)

# Giả định LGD theo loại TSBĐ (chưa có dữ liệu thu hồi để ước lượng)
LGD = {"RealEstate": 0.25, "Deposit": 0.10, "Vehicle": 0.40, "None": 0.45}
CCF = {"CreditCard": 0.10, "SME_Overdraft": 0.40, "Project_ADC": 0.40}


def score_from_pd(p):
    return OFFSET + FACTOR * np.log((1 - p) / p)


def pd12_from_pd6(p6):
    """Quy đổi PD 6 tháng sang 12 tháng, giả định rủi ro hai nửa năm như nhau."""
    return 1 - (1 - p6) ** 2


def fit_model():
    data, book, loans, log, snap = make_dataset()
    X, y = data[FEATURES], data["default"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=SEED)

    enc = WoeEncoder(n_bins=5).fit(X_tr, y_tr)
    iv = enc.iv()
    selected = iv[iv >= IV_MIN].index.tolist()

    # Loại dần biến có hệ số sai dấu (dương), vì như vậy scorecard đi ngược với WoE của chính nó
    W_tr = enc.transform(X_tr)
    while True:
        model = LogisticRegression(C=1.0, max_iter=1000).fit(W_tr[selected], y_tr)
        coef = pd.Series(model.coef_[0], index=selected)
        if (coef < 0).all():
            break
        selected.remove(coef.idxmax())

    p_tr = model.predict_proba(enc.transform(X_tr)[selected])[:, 1]
    p_te = model.predict_proba(enc.transform(X_te)[selected])[:, 1]
    return dict(data=data, book=book, loans=loans, enc=enc, iv=iv, selected=selected, model=model,
                X_tr=X_tr, X_te=X_te, y_tr=y_tr, y_te=y_te, p_tr=p_tr, p_te=p_te)


def predict(r, X):
    return r["model"].predict_proba(r["enc"].transform(X)[r["selected"]])[:, 1]


def ecl_current_book(r):
    """ECL tại 31/10/2026 cho khoản vay chưa default: ECL = PD12 x LGD x EAD (Stage 1-2 đơn giản hóa)."""
    book = r["book"][r["book"]["dpd"] <= 90].copy()
    book["pd6"] = predict(r, book[FEATURES])
    book["pd12"] = pd12_from_pd6(book["pd6"])
    book["score"] = score_from_pd(book["pd6"])
    book["lgd"] = book["collateral_type"].map(LGD).fillna(0.45)
    ccf = book["product"].map(CCF).fillna(0.0)
    book["ead"] = book["outstanding"] + ccf * (book["limit_amt"] - book["outstanding"]).clip(lower=0)
    book["ecl"] = book["pd12"] * book["lgd"] * book["ead"]
    return book


def plot_outputs(r):
    fig, ax = plt.subplots(figsize=(5, 4.5))
    for name, y, p in [("Train", r["y_tr"], r["p_tr"]), ("Test", r["y_te"], r["p_te"])]:
        fpr, tpr, _ = roc_curve(y, p)
        ax.plot(fpr, tpr, label=f"{name} (Gini {gini_ks(y, p)['gini']:.2f})")
    ax.plot([0, 1], [0, 1], "--", color="grey", lw=1)
    ax.set(xlabel="Tỷ lệ khách tốt bị từ chối nhầm", ylabel="Tỷ lệ khách xấu bắt được",
           title="Đường ROC của mô hình PD")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "roc_pd.png", dpi=150)

    top = r["iv"].index[0]
    t = r["enc"].tables[top]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(t.index.astype(str), t["woe"])
    ax.axhline(0, color="black", lw=0.8)
    ax.set(title=f"WoE theo nhóm của biến mạnh nhất: {top}", ylabel="WoE")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(OUT / "woe_bien_manh_nhat.png", dpi=150)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    r = fit_model()
    print("Information Value:\n", r["iv"].round(3).to_string())
    print("\nBiến đưa vào mô hình:", r["selected"])
    coef = pd.Series(r["model"].coef_[0], index=r["selected"]).round(3)
    print("Hệ số (với WoE = ln(Good/Bad), hệ số phải âm):\n", coef.to_string())

    m_tr, m_te = gini_ks(r["y_tr"], r["p_tr"]), gini_ks(r["y_te"], r["p_te"])
    print(f"\nTrain: AUC {m_tr['auc']:.3f} | Gini {m_tr['gini']:.3f} | KS {m_tr['ks']:.3f} | "
          f"{r['y_tr'].sum()} default")
    print(f"Test : AUC {m_te['auc']:.3f} | Gini {m_te['gini']:.3f} | KS {m_te['ks']:.3f} | "
          f"{r['y_te'].sum()} default")

    book = ecl_current_book(r)
    print(f"\nDanh mục chưa default tại 31/10/2026: {len(book):,} khoản, EAD {book['ead'].sum():,.0f} triệu")
    print(f"ECL: {book['ecl'].sum():,.0f} triệu ({book['ecl'].sum() / book['ead'].sum():.2%} EAD)")
    print("ECL theo sản phẩm:\n", book.groupby("product")[["ead", "ecl"]].sum().round(0).to_string())

    r["iv"].round(4).to_csv(OUT / "information_value.csv", encoding="utf-8-sig")
    plot_outputs(r)
