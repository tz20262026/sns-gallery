# -*- coding: utf-8 -*-
"""
世界美女図鑑 — 後付け30カ国語ラベリングスクリプト
════════════════════════════════════════════════════
images/world_beauty_series/ 以下の全PNG画像を対象に
Gemini Vision で30カ国語タイトル + タグ15個を生成し
既存の image_labels.db と labeled_images.json に追記する。

実行方法:
  python label_world_beauty.py           ← 未処理画像のみ（再開可能）
  python label_world_beauty.py --force   ← 全画像を強制再処理
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

PROJECT_ID = "spreadsheet-bot-489912"
CATEGORY   = "world-beauty"

# コスト定数
GEM_IN_PER_M  = 0.15   # Gemini 2.5 Flash input $/M tokens
GEM_OUT_PER_M = 0.60   # Gemini 2.5 Flash output $/M tokens
USD_TO_JPY    = 150

# ─── Load environment ───────────────────────────────────────────────────────
load_dotenv(BASE_DIR / "01_SNS運用/spreadsheet_bot/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY が .env に見つかりません")

from google import genai
from google.genai import types

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL  = "gemini-2.5-flash"

# ─── 30言語リスト ──────────────────────────────────────────────────────────
COUNTRIES = [
    {"lang_code":"en-US","language":"English","native_name":"English"},
    {"lang_code":"ja-JP","language":"Japanese","native_name":"日本語"},
    {"lang_code":"zh-CN","language":"Chinese (Simplified)","native_name":"中文（简体）"},
    {"lang_code":"zh-TW","language":"Chinese (Traditional)","native_name":"中文（繁體）"},
    {"lang_code":"ko-KR","language":"Korean","native_name":"한국어"},
    {"lang_code":"fr-FR","language":"French","native_name":"Français"},
    {"lang_code":"de-DE","language":"German","native_name":"Deutsch"},
    {"lang_code":"es-ES","language":"Spanish","native_name":"Español"},
    {"lang_code":"pt-BR","language":"Portuguese (BR)","native_name":"Português (BR)"},
    {"lang_code":"pt-PT","language":"Portuguese (PT)","native_name":"Português (PT)"},
    {"lang_code":"it-IT","language":"Italian","native_name":"Italiano"},
    {"lang_code":"ru-RU","language":"Russian","native_name":"Русский"},
    {"lang_code":"ar-SA","language":"Arabic","native_name":"العربية"},
    {"lang_code":"hi-IN","language":"Hindi","native_name":"हिन्दी"},
    {"lang_code":"th-TH","language":"Thai","native_name":"ภาษาไทย"},
    {"lang_code":"vi-VN","language":"Vietnamese","native_name":"Tiếng Việt"},
    {"lang_code":"id-ID","language":"Indonesian","native_name":"Bahasa Indonesia"},
    {"lang_code":"tr-TR","language":"Turkish","native_name":"Türkçe"},
    {"lang_code":"nl-NL","language":"Dutch","native_name":"Nederlands"},
    {"lang_code":"pl-PL","language":"Polish","native_name":"Polski"},
    {"lang_code":"sv-SE","language":"Swedish","native_name":"Svenska"},
    {"lang_code":"da-DK","language":"Danish","native_name":"Dansk"},
    {"lang_code":"no-NO","language":"Norwegian","native_name":"Norsk"},
    {"lang_code":"fi-FI","language":"Finnish","native_name":"Suomi"},
    {"lang_code":"cs-CZ","language":"Czech","native_name":"Čeština"},
    {"lang_code":"hu-HU","language":"Hungarian","native_name":"Magyar"},
    {"lang_code":"ro-RO","language":"Romanian","native_name":"Română"},
    {"lang_code":"uk-UA","language":"Ukrainian","native_name":"Українська"},
    {"lang_code":"he-IL","language":"Hebrew","native_name":"עברית"},
    {"lang_code":"el-GR","language":"Greek","native_name":"Ελληνικά"},
]

COUNTRIES_BRIEF = "\n".join(
    f'  {c["lang_code"]}: {c["language"]} ({c["native_name"]})' for c in COUNTRIES
)

# ─── Database ──────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS image_labels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filepath TEXT UNIQUE,
        filename TEXT, subfolder TEXT, category TEXT,
        processed_at TEXT, input_tokens INTEGER, output_tokens INTEGER,
        cost_usd REAL, labels_json TEXT)""")
    conn.commit()
    return conn

def is_already_labeled(conn, filepath: str) -> bool:
    row = conn.execute(
        "SELECT id FROM image_labels WHERE filepath = ?", (filepath,)
    ).fetchone()
    return row is not None

def save_label(conn, filepath, filename, subfolder, category,
               in_tok, out_tok, cost_usd, labels: dict):
    conn.execute("""INSERT OR REPLACE INTO image_labels
        (filepath, filename, subfolder, category, processed_at,
         input_tokens, output_tokens, cost_usd, labels_json)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (str(filepath), filename, subfolder, category,
         datetime.now().isoformat(), in_tok, out_tok, cost_usd,
         json.dumps(labels, ensure_ascii=False)))
    conn.commit()

# ─── Gemini labeling ───────────────────────────────────────────────────────
def label_image(image_path: Path, nationality: str) -> tuple[dict, int, int]:
    """
    Gemini Vision で画像を見て30カ国語タイトル + タグ15個を生成。
    Returns (labels_dict, input_tokens, output_tokens)
    """
    img_bytes = image_path.read_bytes()

    gemini_prompt = f"""You are a world-class multilingual creative director specializing in travel and fashion photography.

Analyze this image. It shows a beautiful {nationality} woman in a specific fashion style at a specific location.

For each of the 30 language codes listed below, create:
1. "title": An evocative, poetic title (5–10 words) describing this specific woman, outfit, and location — in that language
2. "tags": Exactly 15 descriptive keywords/tags in that language covering: the nationality, clothing style, location/landmark, mood, lighting, colors, and photographic style (no hashtags, no punctuation)

Return ONLY a valid JSON object with this exact structure:
{{
  "en-US": {{"title": "...", "tags": ["tag1", "tag2", ..., "tag15"]}},
  "ja-JP": {{"title": "...", "tags": ["tag1", ...]}},
  ...all 30 languages...
}}

Language codes to include:
{COUNTRIES_BRIEF}

Rules:
- Write title and tags naturally in the target language (not word-for-word translation)
- Tags must be relevant to what is actually visible: person, clothing, location, lighting, mood
- Use native script for non-Latin languages (Japanese kanji/kana, Arabic, etc.)
- Return ONLY the JSON object, no markdown fences, no explanation"""

    for attempt in range(4):
        try:
            resp = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    gemini_prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            raw = resp.text.strip()
            m   = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                raise ValueError("JSONが見つかりません")
            labels  = json.loads(m.group())
            in_tok  = resp.usage_metadata.prompt_token_count     if resp.usage_metadata else 500
            out_tok = resp.usage_metadata.candidates_token_count if resp.usage_metadata else 2000
            return labels, in_tok, out_tok

        except Exception as e:
            if attempt < 3:
                wait = 10 * (2 ** attempt)
                print(f"      ⚠️  ラベリングエラー: {e}. {wait}秒後リトライ...")
                time.sleep(wait)
            else:
                print(f"      ❌ ラベリング失敗（フォールバック）: {e}")
                fb = {}
                for c in COUNTRIES:
                    fb[c["lang_code"]] = {
                        "title": f"Beautiful {nationality.capitalize()} woman",
                        "tags":  ["world beauty", "fashion photography", "travel",
                                  nationality, "portrait", "street photography",
                                  "style", "culture", "elegant", "global beauty",
                                  "woman", "photography", "lifestyle", "fashion", "art"],
                    }
                return fb, 500, 200

# ─── JSON export ───────────────────────────────────────────────────────────
def export_json(conn):
    print("\n  📤 labeled_images.json 更新中...")
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
    print(f"  ✅ {len(out)} 件エクスポート完了 → labeled_images.json")

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="世界美女図鑑 後付けラベリング")
    parser.add_argument("--force", action="store_true", help="DB登録済み画像も再処理")
    args = parser.parse_args()

    conn = init_db()

    # world_beauty_series 以下の全PNG収集
    all_images = sorted(IMAGES_DIR.rglob("*.png"))
    if not all_images:
        print("⚠️  画像が見つかりません:", IMAGES_DIR)
        return

    # 未処理のみフィルタ（--force時は全件）
    pending = []
    for img in all_images:
        rel = img.relative_to(BASE_DIR).as_posix()
        if args.force or not is_already_labeled(conn, rel):
            pending.append(img)

    total     = len(all_images)
    skip_cnt  = total - len(pending)
    print(f"\n[STATUS] 画像総数: {total}枚 | 処理済みスキップ: {skip_cnt}枚 | 今回処理: {len(pending)}枚\n")

    if not pending:
        print("✅ 全画像処理済みです。")
        export_json(conn)
        return

    total_cost = 0.0
    done_cnt   = 0

    for i, img_path in enumerate(pending):
        # 国籍をパスから抽出 (world_beauty_series/{nationality}/filename.png)
        nationality = img_path.parent.name
        subfolder   = f"world_beauty_series/{nationality}"
        rel_path    = img_path.relative_to(BASE_DIR).as_posix()

        print(f"[{i+1}/{len(pending)}] {img_path.name}")

        labels, in_tok, out_tok = label_image(img_path, nationality)

        cost = (in_tok * GEM_IN_PER_M + out_tok * GEM_OUT_PER_M) / 1_000_000
        total_cost += cost

        save_label(conn, rel_path, img_path.name, subfolder, CATEGORY,
                   in_tok, out_tok, cost, labels)
        done_cnt += 1

        print(f"  ✅ ラベル保存 | cost: ${cost:.4f} | 累計: ${total_cost:.3f} (¥{total_cost*USD_TO_JPY:,.0f})")

        # Gemini レート制限対策
        time.sleep(2)

        # 50枚ごとに中間エクスポート
        if done_cnt % 50 == 0:
            export_json(conn)

    # 最終エクスポート
    export_json(conn)

    print("\n" + "=" * 60)
    print(f"✅ ラベリング完了: {done_cnt}枚")
    print(f"   総コスト: ${total_cost:.3f} (¥{total_cost*USD_TO_JPY:,.0f})")
    print("=" * 60)

if __name__ == "__main__":
    main()
