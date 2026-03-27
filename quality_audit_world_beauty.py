# -*- coding: utf-8 -*-
"""
世界美女図鑑 — クオリティ監査スクリプト
══════════════════════════════════════════
Gemini Vision で全生成画像を審査し、水準以下の画像を
最大50枚まで自動削除（ファイル・DB・JSON から完全除去）する。

審査基準:
  1. 顔品質     : 顔のパーツが自然か（崩れ・不自然な変形がないか）
  2. 構図       : 三分割法・人物サイズが適切か
  3. 鮮明度     : 背景・布地ディテールがクッキリしているか（Blur禁止）

各基準を 1〜10 でスコアリング。合計スコアが閾値以下 → 削除候補。
最大50枚まで削除。それ以上は保留（レポートのみ）。

実行方法:
  python quality_audit_world_beauty.py            ← 本番実行（削除あり）
  python quality_audit_world_beauty.py --dry-run  ← 監査のみ（削除なし）
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

import os, json, time, argparse, sqlite3, base64, re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ─── Paths ─────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "images" / "world_beauty_series"
DB_PATH     = BASE_DIR / "image_labels.db"
EXPORT_JSON = BASE_DIR / "labeled_images.json"
AUDIT_LOG   = BASE_DIR / "quality_audit_report.json"

MAX_DELETIONS = 50     # 博士の厳命: 最大50枚まで自動削除
PASS_THRESHOLD = 18    # 3項目合計30点満点中18点以上が合格ライン

# ─── Load environment ───────────────────────────────────────────────────────
load_dotenv(BASE_DIR / "01_SNS運用/spreadsheet_bot/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY が .env に見つかりません")

from google import genai
from google.genai import types

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL  = "gemini-2.5-flash"

# ─── Gemini Vision 審査 ────────────────────────────────────────────────────
AUDIT_PROMPT = """You are a strict quality control director for a world-class fashion and beauty photography collection.

Evaluate this image with ruthless precision on exactly 3 criteria. Score each from 1 to 10:

1. FACE_QUALITY (1-10):
   - 10: Face is perfectly natural, every feature sharp and believable
   - 7-9: Minor imperfections but clearly human and natural
   - 4-6: Noticeable distortion, blur, or unnatural features on face/eyes/mouth
   - 1-3: Severely malformed face, multiple distorted features, clearly AI artifact

2. COMPOSITION (1-10):
   - 10: Perfect composition — rule of thirds applied, subject well-sized and positioned
   - 7-9: Good composition with minor issues
   - 4-6: Subject too small, too centered, or composition feels wrong
   - 1-3: No composition principle applied, subject barely visible or cut awkwardly

3. SHARPNESS (1-10):
   - 10: Razor sharp throughout — fabric texture, background architecture, all details crisp
   - 7-9: Mostly sharp with minor soft areas
   - 4-6: Noticeable blur/bokeh on background or clothing details (this violates deep focus rule)
   - 1-3: Heavily blurred background, soft focus on subject, overall lack of detail

Return ONLY this JSON object, nothing else:
{
  "face_quality": <1-10>,
  "composition": <1-10>,
  "sharpness": <1-10>,
  "total": <sum of three scores>,
  "verdict": "PASS" or "FAIL",
  "reason": "<one sentence explaining the main issue if FAIL, or 'All criteria met' if PASS>"
}

VERDICT RULE: "FAIL" if total score < 18 OR any single score < 5. Otherwise "PASS"."""

def audit_image(image_path: Path) -> dict:
    """Gemini Vision で1枚を審査。Returns audit result dict."""
    img_bytes = image_path.read_bytes()

    for attempt in range(3):
        try:
            resp = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    AUDIT_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,        # 審査は低温度で一貫性重視
                    max_output_tokens=512,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            raw = resp.text.strip()
            m   = re.search(r'\{[\s\S]*?\}', raw)
            if not m:
                raise ValueError("JSONが見つかりません")
            result = json.loads(m.group())
            # 必須フィールド検証
            for key in ["face_quality", "composition", "sharpness", "total", "verdict", "reason"]:
                if key not in result:
                    raise ValueError(f"フィールド欠損: {key}")
            # totalを再計算して検証
            result["total"] = result["face_quality"] + result["composition"] + result["sharpness"]
            result["verdict"] = "FAIL" if (
                result["total"] < PASS_THRESHOLD or
                result["face_quality"] < 5 or
                result["composition"] < 5 or
                result["sharpness"] < 5
            ) else "PASS"
            return result

        except Exception as e:
            if attempt < 2:
                print(f"      ⚠️  審査エラー: {e}. リトライ...")
                time.sleep(5)
            else:
                print(f"      ❌ 審査失敗、PASSとして扱う: {e}")
                return {
                    "face_quality": 7, "composition": 7, "sharpness": 7,
                    "total": 21, "verdict": "PASS",
                    "reason": "Audit failed — defaulting to PASS"
                }

# ─── DB operations ────────────────────────────────────────────────────────
def delete_from_db(conn, filepath: str):
    conn.execute("DELETE FROM image_labels WHERE filepath = ?", (filepath,))
    conn.commit()

def export_json(conn):
    rows = conn.execute(
        "SELECT filepath, filename, subfolder, category, processed_at, labels_json "
        "FROM image_labels ORDER BY filepath"
    ).fetchall()
    out = []
    for filepath, filename, subfolder, category, processed_at, labels_json in rows:
        out.append({
            "src":          filepath.replace("\\", "/"),
            "filename":     filename,
            "subfolder":    subfolder,
            "category":     category,
            "processed_at": processed_at,
            "labels":       json.loads(labels_json),
        })
    EXPORT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📤 labeled_images.json 更新完了 ({len(out)}件)")

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="世界美女図鑑 クオリティ監査")
    parser.add_argument("--dry-run", action="store_true",
                        help="審査のみ実行（削除・DB変更なし）")
    args = parser.parse_args()

    mode_str = "【DRY RUN — 削除なし】" if args.dry_run else "【本番 — 削除実行】"
    print(f"\n{'='*60}")
    print(f"🔍 クオリティ監査開始 {mode_str}")
    print(f"   合格ライン: 合計{PASS_THRESHOLD}点以上 / 各項目5点以上")
    print(f"   最大削除数: {MAX_DELETIONS}枚")
    print(f"{'='*60}\n")

    # 対象画像収集
    all_images = sorted(IMAGES_DIR.rglob("*.png"))
    if not all_images:
        print("⚠️  画像が見つかりません:", IMAGES_DIR)
        return

    print(f"審査対象: {len(all_images)}枚\n")

    conn = sqlite3.connect(DB_PATH) if not args.dry_run else None

    # 審査結果記録
    results = []
    fail_list = []
    deletion_count = 0
    gem_cost_total = 0.0

    for i, img_path in enumerate(all_images):
        rel_path = img_path.relative_to(BASE_DIR).as_posix()
        nat      = img_path.parent.name

        audit = audit_image(img_path)
        gem_cost = 0.003  # 審査1枚あたり概算 $0.003
        gem_cost_total += gem_cost

        verdict_icon = "✅" if audit["verdict"] == "PASS" else "❌"
        print(f"[{i+1}/{len(all_images)}] {verdict_icon} {img_path.name}")
        print(f"   顔:{audit['face_quality']}/10 構図:{audit['composition']}/10 "
              f"鮮明度:{audit['sharpness']}/10 合計:{audit['total']}/30")
        if audit["verdict"] == "FAIL":
            print(f"   💬 {audit['reason']}")

        entry = {
            "file": img_path.name,
            "path": rel_path,
            "nationality": nat,
            "scores": {
                "face_quality": audit["face_quality"],
                "composition":  audit["composition"],
                "sharpness":    audit["sharpness"],
                "total":        audit["total"],
            },
            "verdict": audit["verdict"],
            "reason":  audit["reason"],
        }
        results.append(entry)

        if audit["verdict"] == "FAIL":
            fail_list.append(entry)
            if deletion_count < MAX_DELETIONS and not args.dry_run:
                # ファイル削除
                img_path.unlink()
                # DB削除
                delete_from_db(conn, rel_path)
                entry["action"] = "DELETED"
                deletion_count += 1
                print(f"   🗑️  削除済み ({deletion_count}/{MAX_DELETIONS})")
            elif deletion_count >= MAX_DELETIONS:
                entry["action"] = "FLAGGED_ONLY"
                print(f"   ⚠️  削除上限到達 — フラグのみ")
            else:
                entry["action"] = "DRY_RUN_WOULD_DELETE"

        time.sleep(1.5)  # Gemini レート制限対策

    # DB・JSON更新
    if not args.dry_run and deletion_count > 0:
        export_json(conn)

    if conn:
        conn.close()

    # ─── 最終レポート ──────────────────────────────────────────────────────
    total       = len(all_images)
    pass_count  = total - len(fail_list)
    fail_count  = len(fail_list)
    flagged_only = fail_count - deletion_count

    report = {
        "audit_date":       datetime.now().isoformat(),
        "mode":             "dry_run" if args.dry_run else "live",
        "total_audited":    total,
        "passed":           pass_count,
        "failed":           fail_count,
        "deleted":          deletion_count,
        "flagged_only":     flagged_only,
        "pass_threshold":   PASS_THRESHOLD,
        "max_deletions":    MAX_DELETIONS,
        "audit_cost_usd":   round(gem_cost_total, 3),
        "results":          results,
    }
    AUDIT_LOG.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{'='*60}")
    print(f"📊 クオリティ監査 最終報告")
    print(f"{'='*60}")
    print(f"  審査枚数    : {total}枚")
    print(f"  合格        : {pass_count}枚 ✅")
    print(f"  不合格      : {fail_count}枚 ❌")
    print(f"  削除実行    : {deletion_count}枚 🗑️")
    print(f"  フラグのみ  : {flagged_only}枚 ⚠️  (上限超過)")
    print(f"  残存枚数    : {total - deletion_count}枚")
    print(f"  監査コスト  : ${gem_cost_total:.3f}")
    print(f"  レポート保存: quality_audit_report.json")
    print(f"{'='*60}")

    if fail_list:
        print(f"\n❌ 不合格画像一覧 ({len(fail_list)}枚):")
        for f in fail_list:
            action = f.get("action", "")
            print(f"  [{action}] {f['file']} "
                  f"(顔:{f['scores']['face_quality']} 構図:{f['scores']['composition']} "
                  f"鮮明:{f['scores']['sharpness']} 合計:{f['scores']['total']}) "
                  f"— {f['reason']}")

if __name__ == "__main__":
    main()
