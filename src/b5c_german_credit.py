"""Chạy cùng quy trình WoE + logistic trên dữ liệu thật German Credit (UCI Statlog).

1.000 khoản vay tiêu dùng của một ngân hàng Đức, 300 khoản default. Mã thuộc tính giữ nguyên
theo UCI (A11, A12, ...). Đây là dữ liệu lúc xét duyệt (application), không có biến quá hạn.

Chạy riêng:  python src/b5c_german_credit.py
"""
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from woe import WoeEncoder, auc_ci, gini_ks

ROOT = Path(__file__).resolve().parents[1]
IV_MIN = 0.02
# Không dùng giới tính/hôn nhân và quốc tịch người lao động làm biến xét duyệt (rủi ro phân biệt đối xử)
EXCLUDE = ["gioi_tinh_hon_nhan", "lao_dong_nuoc_ngoai"]


def run():
    df = pd.read_csv(ROOT / "data" / "german_credit.csv")
    y = df.pop("default")
    df = df.drop(columns=EXCLUDE)
    X_tr, X_te, y_tr, y_te = train_test_split(df, y, test_size=0.3, stratify=y, random_state=42)

    enc = WoeEncoder(n_bins=5).fit(X_tr, y_tr)
    iv = enc.iv()
    selected = iv[iv >= IV_MIN].index.tolist()
    W_tr, W_te = enc.transform(X_tr), enc.transform(X_te)
    while True:
        model = LogisticRegression(C=1.0, max_iter=1000).fit(W_tr[selected], y_tr)
        coef = pd.Series(model.coef_[0], index=selected)
        if (coef < 0).all():
            break
        selected.remove(coef.idxmax())

    p_tr = model.predict_proba(W_tr[selected])[:, 1]
    p_te = model.predict_proba(W_te[selected])[:, 1]
    return dict(iv=iv, selected=selected, enc=enc, y_tr=y_tr, y_te=y_te, p_tr=p_tr, p_te=p_te)


if __name__ == "__main__":
    r = run()
    print("Information Value:\n", r["iv"].round(3).to_string())
    top = r["iv"].index[0]
    print(f"\nWoE của biến mạnh nhất ({top}):\n",
          r["enc"].tables[top][["n", "bad_rate", "woe"]].round(3).to_string())
    m_tr, m_te = gini_ks(r["y_tr"], r["p_tr"]), gini_ks(r["y_te"], r["p_te"])
    lo, hi = auc_ci(r["y_te"], r["p_te"])
    print(f"\nTrain: Gini {m_tr['gini']:.3f} | KS {m_tr['ks']:.3f}")
    print(f"Test : Gini {m_te['gini']:.3f} | KS {m_te['ks']:.3f} | {r['y_te'].sum()} default")
    print(f"AUC test 95% CI: {lo:.3f} – {hi:.3f}")
    print(f"PD dự báo bình quân (test): {r['p_te'].mean():.1%} | tỷ lệ default thực tế: {r['y_te'].mean():.1%}")
