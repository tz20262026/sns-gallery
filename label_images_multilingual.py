# -*- coding: utf-8 -*-
"""
Multilingual Image Labeling Script using Gemini 1.5 Flash
- 30-country automatic language labeling
- 15 fixed categories
- SQLite storage + JSON export
- Budget management (500 JPY limit)
- Resume support (skips already processed images)
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

import os
import json
import sqlite3
import time
import base64
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / "01_SNS運用/spreadsheet_bot/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

DB_PATH = BASE_DIR / "image_labels.db"
EXPORT_JSON_PATH = BASE_DIR / "labeled_images.json"
BUDGET_JPY = 3000
USD_TO_JPY = 150  # Approximate exchange rate

# Gemini 2.5 Flash pricing (USD per 1M tokens)
# Note: gemini-1.5-flash not available; using gemini-2.5-flash (thinking disabled)
PRICE_INPUT_PER_M  = 0.15   # gemini-2.5-flash non-thinking input
PRICE_OUTPUT_PER_M = 0.60   # gemini-2.5-flash non-thinking output
IMAGE_TOKENS       = 258    # Approximate token count per image (from API metadata)

# 15 allowed categories (strict - no others allowed)
CATEGORIES = [
    "animals", "architecture", "backgrounds", "business", "education",
    "family", "food", "logos", "nature", "people", "plants-flowers",
    "sports", "technology", "travel", "wallpapers"
]

# Image folders to process (all subfolders will be scanned recursively)
IMAGE_FOLDERS = [
    BASE_DIR / "images/children",
    BASE_DIR / "images/huukei",
    BASE_DIR / "images/Macro",
    BASE_DIR / "images/Neon",
    BASE_DIR / "images/Ocean",
    BASE_DIR / "images/showa",
    BASE_DIR / "images/stock_images",
]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# ─────────────────────────────────────────
# Gemini Client Setup
# ─────────────────────────────────────────
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-2.5-flash"

# ─────────────────────────────────────────
# Database Setup
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS image_labels (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath      TEXT    UNIQUE,
            filename      TEXT,
            subfolder     TEXT,
            category      TEXT,
            processed_at  TEXT,
            input_tokens  INTEGER,
            output_tokens INTEGER,
            cost_usd      REAL,
            labels_json   TEXT
        );

        CREATE TABLE IF NOT EXISTS processing_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    return conn

def get_processed_paths(conn):
    cur = conn.cursor()
    cur.execute("SELECT filepath FROM image_labels")
    return {row[0] for row in cur.fetchall()}

def save_label(conn, filepath, filename, subfolder, category,
               input_tokens, output_tokens, cost_usd, labels):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO image_labels
        (filepath, filename, subfolder, category, processed_at, input_tokens, output_tokens, cost_usd, labels_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(filepath), filename, subfolder, category,
        datetime.now().isoformat(), input_tokens, output_tokens, cost_usd,
        json.dumps(labels, ensure_ascii=False)
    ))
    conn.commit()

def save_meta(conn, key, value):
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO processing_meta (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()

def get_meta(conn, key):
    cur = conn.cursor()
    cur.execute("SELECT value FROM processing_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else None

# ─────────────────────────────────────────
# Cost Calculation
# ─────────────────────────────────────────
def calc_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_INPUT_PER_M + output_tokens * PRICE_OUTPUT_PER_M) / 1_000_000

def usd_to_jpy(usd: float) -> float:
    return usd * USD_TO_JPY

# ─────────────────────────────────────────
# Step 1: Select 30 Countries via Gemini
# ─────────────────────────────────────────
def select_30_countries(conn) -> list[dict]:
    """Ask Gemini to select the optimal 30 countries for stock photo labeling."""
    cached = get_meta(conn, "countries_json")
    if cached:
        countries = json.loads(cached)
        print(f"[INFO] Using cached 30 countries ({len(countries)} loaded)")
        return countries

    print("[STEP 1] Asking Gemini to select 30 countries for stock photo labeling...")
    prompt = """You are a stock photo market expert. Select the 30 countries with the highest demand for stock photos, considering:
1. Internet population size
2. Stock photo purchase volume
3. Creative industry size
4. Geographic and linguistic diversity

Return ONLY a valid JSON array of exactly 30 objects, each with:
- "country": English country name
- "lang_code": BCP-47 language tag (e.g. "en-US", "ja-JP")
- "language": English language name
- "native_name": language name in that language

Example format:
[{"country":"United States","lang_code":"en-US","language":"English","native_name":"English"},...]

Return ONLY the JSON array, no other text."""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
    )
    raw = response.text.strip()
    # Extract JSON array from response
    match = re.search(r'\[[\s\S]*\]', raw)
    if not match:
        raise ValueError(f"Could not parse countries JSON:\n{raw}")
    countries = json.loads(match.group())
    if len(countries) != 30:
        raise ValueError(f"Expected 30 countries, got {len(countries)}")

    save_meta(conn, "countries_json", json.dumps(countries, ensure_ascii=False))
    print(f"[STEP 1] ✓ Selected {len(countries)} countries:")
    for i, c in enumerate(countries, 1):
        print(f"  {i:2}. {c['country']} ({c['lang_code']}) - {c['language']}")
    return countries

# ─────────────────────────────────────────
# Step 2: Collect All Image Paths
# ─────────────────────────────────────────
def collect_images() -> list[Path]:
    images = []
    for folder in IMAGE_FOLDERS:
        if folder.exists():
            for f in sorted(folder.rglob("*")):
                if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file():
                    images.append(f)
    return images

# ─────────────────────────────────────────
# Step 3: Build Per-Image Prompt
# ─────────────────────────────────────────
def build_label_prompt(countries: list[dict]) -> str:
    lang_list = "\n".join(
        f'  {i+1}. "{c["lang_code"]}" ({c["country"]} / {c["language"]})'
        for i, c in enumerate(countries)
    )
    categories_str = ", ".join(CATEGORIES)
    return f"""You are a professional stock photo metadata specialist. Analyze this image and generate multilingual metadata.

TASK:
1. Classify the image into EXACTLY ONE of these 15 categories: {categories_str}
   - Choose the single best-fitting category. Do NOT create new categories.

2. For each of the 30 languages below, generate:
   - "title": A descriptive, SEO-optimized title (5-10 words) in that language
   - "tags": Exactly 15 relevant search tags (single words or short phrases) in that language, localized for that market

Languages (use these exact lang_code keys):
{lang_list}

CRITICAL: Return ONLY valid JSON in this exact structure, no other text:
{{
  "category": "<one of the 15 categories>",
  "labels": {{
    "en-US": {{"title": "...", "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10","tag11","tag12","tag13","tag14","tag15"]}},
    "ja-JP": {{"title": "...", "tags": ["...x15"]}},
    ... (all 30 lang_codes)
  }}
}}

Ensure each "tags" array has EXACTLY 15 items. Localize naturally for each market."""

# ─────────────────────────────────────────
# Step 4: Process Single Image
# ─────────────────────────────────────────
def process_image(image_path: Path, prompt: str, subfolder: str) -> tuple[str, int, int, float, dict]:
    """
    Returns: (category, input_tokens, output_tokens, cost_usd, labels_dict)
    """
    # Read and encode image
    image_data = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(suffix, "image/png")

    image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)

    response = client.models.generate_content(
        model=MODEL,
        contents=[image_part, prompt],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=8192,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
    )

    # Token usage
    usage = response.usage_metadata
    input_tokens  = getattr(usage, 'prompt_token_count', IMAGE_TOKENS + 400)
    # candidates_token_count can be None for gemini-2.5-flash; use total - prompt as fallback
    output_tokens = getattr(usage, 'candidates_token_count', None)
    if output_tokens is None:
        total = getattr(usage, 'total_token_count', None)
        output_tokens = (total - input_tokens) if total else 3000
    cost_usd = calc_cost_usd(input_tokens, output_tokens)

    # Parse JSON response
    raw = response.text.strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError(f"No JSON found in response for {image_path.name}")
    data = json.loads(match.group())

    category = data.get("category", "backgrounds").lower().strip()
    if category not in CATEGORIES:
        # Find closest match
        category = "backgrounds"

    labels = data.get("labels", {})
    return category, input_tokens, output_tokens, cost_usd, labels

# ─────────────────────────────────────────
# Step 5: Export JSON for Frontend
# ─────────────────────────────────────────
def export_json(conn):
    print("\n[EXPORT] Generating labeled_images.json for frontend...")
    cur = conn.cursor()
    cur.execute("""
        SELECT filepath, filename, subfolder, category, processed_at, labels_json
        FROM image_labels ORDER BY subfolder, filename
    """)
    rows = cur.fetchall()
    result = []
    for row in rows:
        filepath, filename, subfolder, category, processed_at, labels_json = row
        labels = json.loads(labels_json) if labels_json else {}
        # Build relative path for web use
        rel_path = str(Path(filepath).relative_to(BASE_DIR)).replace("\\", "/")
        result.append({
            "src": rel_path,
            "filename": filename,
            "subfolder": subfolder,
            "category": category,
            "processed_at": processed_at,
            "labels": labels
        })
    with open(EXPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] ✓ Saved {len(result)} images to {EXPORT_JSON_PATH.name}")

# ─────────────────────────────────────────
# Main Processing Loop
# ─────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Multilingual Image Labeling  |  Gemini 1.5 Flash")
    print("  Budget Limit: ¥500 JPY")
    print("=" * 60)

    # Init DB
    conn = init_db()

    # Step 1: Get 30 countries
    countries = select_30_countries(conn)

    # Step 2: Collect all images
    all_images = collect_images()
    print(f"\n[SCAN] Found {len(all_images)} total images across all folders")

    # Check already processed
    processed_paths = get_processed_paths(conn)
    remaining = [p for p in all_images if str(p) not in processed_paths]
    print(f"[SCAN] Already processed: {len(processed_paths)}")
    print(f"[SCAN] Remaining to process: {len(remaining)}")

    if not remaining:
        print("\n[DONE] All images already processed!")
        export_json(conn)
        return

    # Build prompt (shared for all images)
    prompt = build_label_prompt(countries)

    # Load cumulative cost from DB
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM image_labels")
    cumulative_cost_usd = float(cur.fetchone()[0])
    cumulative_cost_jpy = usd_to_jpy(cumulative_cost_usd)

    print(f"\n[COST] Cumulative so far: ${cumulative_cost_usd:.4f} (¥{cumulative_cost_jpy:.1f})")
    print(f"\n[START] Processing {len(remaining)} images... (non-stop)\n")
    print("-" * 60)

    start_time = time.time()
    success_count = 0
    error_count = 0

    for idx, image_path in enumerate(remaining, 1):
        # Budget check BEFORE processing
        if cumulative_cost_jpy >= BUDGET_JPY:
            print(f"\n{'='*60}")
            print(f"[BUDGET ALERT] ¥{cumulative_cost_jpy:.1f} / ¥{BUDGET_JPY}")
            print(f"  Processed {success_count} new images this session.")
            print(f"  Total processed: {len(processed_paths) + success_count}/{len(all_images)}")
            response = input("\n  累計コストが¥500を超えました。続行しますか？ (y/n): ").strip().lower()
            if response != 'y':
                print("[STOP] ユーザーにより停止されました。")
                break
            print("[CONTINUE] 処理を続行します...")

        # Determine subfolder (relative to images/)
        try:
            rel = image_path.relative_to(BASE_DIR / "images")
            subfolder = rel.parts[0]
        except ValueError:
            subfolder = image_path.parent.name

        try:
            category, in_tok, out_tok, cost_usd, labels = process_image(
                image_path, prompt, subfolder
            )
            save_label(conn, image_path, image_path.name, subfolder,
                      category, in_tok, out_tok, cost_usd, labels)

            cumulative_cost_usd += cost_usd
            cumulative_cost_jpy = usd_to_jpy(cumulative_cost_usd)
            success_count += 1

            # Progress display
            elapsed = time.time() - start_time
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining_count = len(remaining) - idx
            eta_sec = remaining_count / rate if rate > 0 else 0
            eta_str = f"{int(eta_sec//3600):02}:{int((eta_sec%3600)//60):02}:{int(eta_sec%60):02}"

            print(
                f"[{idx:4}/{len(remaining)}] ✓ {subfolder}/{image_path.name[:30]:<30} "
                f"| {category:<20} "
                f"| tokens: {in_tok}+{out_tok} "
                f"| ¥{cumulative_cost_jpy:6.1f} "
                f"| ETA: {eta_str}"
            )

            # Rate limiting: small delay to avoid hitting API limits
            time.sleep(0.3)

        except Exception as e:
            error_count += 1
            print(f"[{idx:4}/{len(remaining)}] ✗ ERROR {image_path.name}: {e}")
            # On repeated errors, wait longer
            if error_count % 5 == 0:
                print("[WARN] Multiple errors. Waiting 10 seconds...")
                time.sleep(10)
            else:
                time.sleep(1)

    # Final summary
    elapsed_total = time.time() - start_time
    print("\n" + "=" * 60)
    print("  PROCESSING COMPLETE")
    print("=" * 60)
    print(f"  New images processed : {success_count}")
    print(f"  Errors               : {error_count}")
    print(f"  Total in DB          : {len(processed_paths) + success_count}")
    print(f"  Session cost         : ${cumulative_cost_usd:.4f} (¥{cumulative_cost_jpy:.1f})")
    print(f"  Elapsed time         : {int(elapsed_total//60)}m {int(elapsed_total%60)}s")
    print("=" * 60)

    # Export JSON for frontend
    export_json(conn)

    print("\n[DONE] labeled_images.json を生成しました。")
    print("       フロントエンドで language_detector.js を使用してください。")

if __name__ == "__main__":
    main()
