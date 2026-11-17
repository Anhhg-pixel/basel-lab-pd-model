"""Chạy một file .sql trên data/bank.db và in kết quả từng câu lệnh.

Cách dùng:  python src/run_sql.py sql/01_kiem_tra_du_lieu.sql
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "bank.db"

sql_file = Path(sys.argv[1])
text = sql_file.read_text(encoding="utf-8")
lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

with sqlite3.connect(DB) as con:
    for i, stmt in enumerate(statements, 1):
        print(f"\n--- Câu lệnh {i} ---")
        try:
            print(pd.read_sql_query(stmt, con).to_string(index=False))
        except Exception as e:
            print("Lỗi:", e)
