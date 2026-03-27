# -*- coding: utf-8 -*-
import sqlite3, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

conn = sqlite3.connect("image_labels.db")
rows = conn.execute(
    "SELECT filepath, filename, subfolder, category, processed_at, labels_json FROM image_labels"
).fetchall()

out = []
for filepath, filename, subfolder, category, processed_at, labels_json in rows:
    src = filepath.replace("\\", "/")
    # 相対パスに正規化
    if "images/" in src:
        src = "images/" + src.split("images/")[-1]
    out.append({
        "src":          src,
        "filename":     filename,
        "subfolder":    subfolder,
        "category":     category,
        "processed_at": processed_at,
        "labels":       json.loads(labels_json),
    })

with open("labeled_images.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"✅ labeled_images.json 更新完了: {len(out)} 件")

cats = {}
for d in out:
    cats[d["category"]] = cats.get(d["category"], 0) + 1
for k, v in sorted(cats.items()):
    print(f"  {k}: {v}件")
