"""Chia nhóm biến, tính WoE/IV và các chỉ số đánh giá mô hình PD.

Quy ước: WoE = ln(%Good / %Bad). WoE dương = nhóm an toàn hơn trung bình.
"""
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.metrics import roc_auc_score

MISSING = "Thiếu"


def make_bins(x, n_bins=5):
    """Ranh giới nhóm theo phân vị cho biến số; None nếu biến là phân loại."""
    if not pd.api.types.is_numeric_dtype(x):
        return None
    v = x.dropna().astype(float)
    mode = v.mode().iloc[0]
    if (v == mode).mean() > 0.5:
        # Biến dồn nhiều ở một giá trị (ví dụ dpd = 0): giá trị đó thành một nhóm riêng,
        # phần còn lại chia theo phân vị
        rest = v[v > mode]
        qs = np.unique(np.quantile(rest, np.linspace(0, 1, n_bins))[:-1]) if len(rest) else []
        inner = np.unique(np.concatenate([[mode], qs]))
        return np.concatenate([[-np.inf], inner, [np.inf]])
    qs = np.unique(np.quantile(v, np.linspace(0, 1, n_bins + 1)))
    if len(qs) <= 2:
        return np.array([-np.inf, np.inf])
    return np.concatenate([[-np.inf], qs[1:-1], [np.inf]])


def assign_bin(x, edges):
    """Gán nhãn nhóm. Giá trị thiếu là một nhóm riêng."""
    if edges is None:
        return x.astype(object).where(x.notna(), MISSING).astype(str)
    out = pd.cut(x.astype(float), edges, right=True).astype(str)
    return out.where(x.notna(), MISSING)


def woe_table(bins, y, smooth=0.5):
    """Bảng WoE/IV của một biến đã chia nhóm. y = 1 là default (Bad)."""
    t = pd.DataFrame({"bin": bins, "bad": y}).groupby("bin")["bad"].agg(["count", "sum"])
    t.columns = ["n", "bad"]
    t["good"] = t["n"] - t["bad"]
    pg = (t["good"] + smooth) / (t["good"].sum() + smooth * len(t))
    pb = (t["bad"] + smooth) / (t["bad"].sum() + smooth * len(t))
    t["bad_rate"] = t["bad"] / t["n"]
    t["woe"] = np.log(pg / pb)
    t["iv"] = (pg - pb) * t["woe"]
    return t


class WoeEncoder:
    """Học nhóm và WoE trên tập train, áp dụng cho tập khác."""

    def __init__(self, n_bins=5):
        self.n_bins = n_bins
        self.edges, self.tables = {}, {}

    def fit(self, X, y):
        for col in X.columns:
            self.edges[col] = make_bins(X[col], self.n_bins)
            self.tables[col] = woe_table(assign_bin(X[col], self.edges[col]), y)
        return self

    def iv(self):
        return (pd.Series({c: t["iv"].sum() for c, t in self.tables.items()})
                .sort_values(ascending=False).rename("iv"))

    def transform(self, X):
        out = pd.DataFrame(index=X.index)
        for col, t in self.tables.items():
            b = assign_bin(X[col], self.edges[col])
            out[col] = b.map(t["woe"]).fillna(0.0).astype(float)  # nhóm chưa gặp ở train -> WoE 0
        return out


def gini_ks(y, pd_hat):
    auc = roc_auc_score(y, pd_hat)
    ks = ks_2samp(pd_hat[y == 1], pd_hat[y == 0]).statistic
    return {"auc": auc, "gini": 2 * auc - 1, "ks": ks}


def auc_ci(y, pd_hat, n_boot=2000, seed=7):
    """Khoảng tin cậy 95% của AUC bằng bootstrap phân tầng."""
    rng = np.random.default_rng(seed)
    y, pd_hat = np.asarray(y), np.asarray(pd_hat)
    bad, good = np.where(y == 1)[0], np.where(y == 0)[0]
    aucs = []
    for _ in range(n_boot):
        idx = np.concatenate([rng.choice(bad, len(bad)), rng.choice(good, len(good))])
        aucs.append(roc_auc_score(y[idx], pd_hat[idx]))
    return np.percentile(aucs, [2.5, 97.5])


def psi(expected, actual, edges):
    """Population Stability Index giữa hai phân phối điểm."""
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))
