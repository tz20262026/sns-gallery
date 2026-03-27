# -*- coding: utf-8 -*-
"""check_progress.py - ラベリング処理の進捗確認スクリプト"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "image_labels.db"
TOTAL_IMAGES = 2565

if not DB_PATH.exists():
    print("image_labels.db が見つかりません。スクリプトはまだ実行されていません。")
    sys.exit()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT COUNT(*), COALESCE(SUM(cost_usd),0), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM image_labels")
count, cost_usd, in_tok, out_tok = cur.fetchone()

cur.execute("SELECT MIN(processed_at), MAX(processed_at) FROM image_labels")
start_at, last_at = cur.fetchone()

cur.execute("SELECT category, COUNT(*) FROM image_labels GROUP BY category ORDER BY COUNT(*) DESC")
cats = cur.fetchall()

cur.execute("SELECT subfolder, COUNT(*) FROM image_labels GROUP BY subfolder ORDER BY subfolder")
folders = cur.fetchall()

cost_jpy = cost_usd * 150
pct = count / TOTAL_IMAGES * 100
remaining = TOTAL_IMAGES - count
cost_per_image = cost_jpy / count if count > 0 else 0
est_total = cost_per_image * TOTAL_IMAGES

print("=" * 60)
print("  多言語ラベリング進捗レポート")
print("=" * 60)
print(f"  処理済み    : {count:,} / {TOTAL_IMAGES:,} 枚  ({pct:.1f}%)")
print(f"  残り        : {remaining:,} 枚")
print(f"  累計コスト  : ${cost_usd:.4f} (¥{cost_jpy:.1f})")
print(f"  予算上限    : ¥3,000")
print(f"  1枚あたり   : ¥{cost_per_image:.3f}")
print(f"  全件推定    : ¥{est_total:.0f}")
if start_at:
    print(f"  開始時刻    : {start_at}")
    print(f"  最終処理    : {last_at}")
print()
print("  【フォルダ別進捗】")
for folder, n in folders:
    print(f"    {folder:20} : {n:4} 枚")
print()
print("  【カテゴリ分布】")
for cat, n in cats:
    bar = "█" * (n // 20)
    print(f"    {cat:20} : {n:4} 枚  {bar}")
print("=" * 60)

conn.close()
