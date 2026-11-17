"""Chạy toàn bộ phần Python (bước 4 -> 7 và German Credit), lưu kết quả vào outputs/.

Cách dùng (từ thư mục gốc của project):  python src/chay_tat_ca.py
"""
import runpy
from pathlib import Path

SRC = Path(__file__).resolve().parent
STEPS = ["b4_chuan_bi_du_lieu.py", "b5_mo_hinh_pd.py", "b5c_german_credit.py",
         "b6_irb_rwa.py", "b7_kiem_dinh.py"]

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(SRC))
    for step in STEPS:
        print("\n" + "=" * 70 + f"\n{step}\n" + "=" * 70)
        runpy.run_path(str(SRC / step), run_name="__main__")
