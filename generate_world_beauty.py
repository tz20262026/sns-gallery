# -*- coding: utf-8 -*-
"""
世界美女図鑑 第2章 — 400枚生成 + 30カ国語ラベリング統合スクリプト
══════════════════════════════════════════════════════════════════
モデル : Imagen 3 Fast (Vertex AI) + Gemini 2.5 Flash (Gemini API)
出力  : images/world_beauty_series/{nationality}/
命名  : {seq}_{nationality}_{outfit}_{location}_{angle}.png
DB   : image_labels.db（既存DBに追記）
JSON : labeled_images.json（生成・ラベリング後に更新）
開始番号: 2957（既存2,956枚の次）

実行方法:
  テスト(4枚):    python generate_world_beauty.py --test
  バッチ実行:     python generate_world_beauty.py --batch 1   # 1〜8 (各50枚)
  全件実行:       python generate_world_beauty.py
  再開:           python generate_world_beauty.py             ← 自動的に続きから
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

import os, json, time, argparse, sqlite3, base64, re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ─── Paths & Config ────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
OUTPUT_DIR  = BASE_DIR / "images" / "world_beauty_series"
CHECKPOINT  = BASE_DIR / "world_beauty_progress.json"
DB_PATH     = BASE_DIR / "image_labels.db"
EXPORT_JSON = BASE_DIR / "labeled_images.json"

PROJECT_ID      = "spreadsheet-bot-489912"
LOCATION        = "us-central1"
CANDIDATE_COUNT = 1          # 1リクエスト = 1枚（独立した単一画像）
START_SEQ       = 2957       # ステップ1確認済み: 既存2,956枚の次
TOTAL_SETS      = 100        # 100セット × 4枚 = 400枚
BATCH_SIZE      = 13         # --batch 1 〜 8 (13セット≒50枚、最終バッチは9セット)
CATEGORY        = "world-beauty"

# コスト定数
GEM_IN_PER_M  = 0.15
GEM_OUT_PER_M = 0.60
USD_TO_JPY    = 150

# ─── Load environment ───────────────────────────────────────────────────────
load_dotenv(BASE_DIR / "01_SNS運用/spreadsheet_bot/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY が .env に見つかりません")

from google import genai
from google.genai import types

imagen_client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
IMAGEN_MODEL  = "imagen-3.0-fast-generate-001"
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

# ─── 4カメラアングル（セット内固定ローテーション） ────────────────────────
CAMERA_ANGLES = [
    {
        "key": "closeup",
        "desc": "extreme close-up portrait, face and shoulders filling the entire frame, "
                "pore-level skin detail, intimate distance, eyes sharp and piercing",
    },
    {
        "key": "fullbody",
        "desc": "full-body shot from head to toe, entire outfit visible, "
                "elegant posture, environmental context visible around her",
    },
    {
        "key": "lowangle",
        "desc": "dramatic low-angle shot looking up from ground level, "
                "empowering perspective, sky or ceiling as backdrop, "
                "dynamic and cinematic composition",
    },
    {
        "key": "thirds",
        "desc": "rule-of-thirds composition, subject powerfully offset to one side, "
                "environment fills the complementary two-thirds, "
                "balanced and visually compelling framing",
    },
]

# ─── 品質タグ（全プロンプト共通） ────────────────────────────────────────
QUALITY_TAGS = (
    "masterpiece quality, best quality, highly detailed, tack sharp throughout entire frame, "
    "deep focus f/11, no bokeh, no blur, crisp sharp background details, "
    "ray tracing lighting, 8K ultra-high resolution, photorealistic Unreal Engine 5 quality, "
    "street photography style, cinematic color grading"
)

# ─── 100セット定義 ─────────────────────────────────────────────────────────
#
# 各セット: (nationality, outfit_key, outfit_desc, location_key, location_desc, lighting_desc)
#
# nationality  → サブフォルダ名 & ファイル名の国籍フィールド
# outfit_key   → ファイル名の服装フィールド（英数字のみ）
# outfit_desc  → プロンプト内の服装説明
# location_key → ファイル名の場所フィールド（英数字のみ）
# location_desc → プロンプト内の場所説明
# lighting     → ドラマチックなライティング指定

BEAUTY_SETS = [
    # ── JAPANESE (4セット) ────────────────────────────────────────────────
    ("japanese", "hoodie",    "oversized pastel hoodie, wide-leg jeans, white chunky sneakers",
     "shibuya",   "Shibuya Crossing at night, neon signs reflecting on wet pavement, Tokyo",
     "dramatic side-light from neon signs, hard rim light, electric blue and pink tones"),

    ("japanese", "kimono",    "modern cropped kimono with obi belt, ankle boots, street-styled",
     "arashiyama","bamboo grove path in Arashiyama, Kyoto, soft golden hour shafts of light",
     "backlight through bamboo, dappled golden god rays, warm amber tones"),

    ("japanese", "techwear",  "black techwear jacket, cargo pants, tech sneakers, utility vest",
     "akihabara", "Akihabara electric town, neon-lit electronics storefronts, night time",
     "harsh overhead neon lighting, strong shadows, cyberpunk color palette"),

    ("japanese", "uniform",   "Japanese high school blazer uniform, pleated skirt, loafers",
     "kyoto_temple","vermillion torii gates of Fushimi Inari, misty morning light, Kyoto",
     "early morning mist, soft diffused light, peaceful serene atmosphere"),

    # ── KOREAN (4セット) ──────────────────────────────────────────────────
    ("korean", "streetwear", "K-pop streetwear: oversized graphic tee, wide cargo pants, platform sneakers",
     "hongdae",  "Hongdae street art district, Seoul, colorful murals, late afternoon",
     "warm golden afternoon light, strong directional side-light, vivid colors"),

    ("korean", "hanbok",     "modern fusion hanbok with contemporary silhouette, silk fabric",
     "gyeongbokgung","Gyeongbokgung Palace, Seoul, traditional gate architecture",
     "overcast diffused light, soft even illumination, cool blue tones"),

    ("korean", "coat",       "long structured camel overcoat, black turtleneck, ankle boots",
     "seoul_winter","Han River bridge in winter, Seoul skyline, blue winter sky",
     "bright winter sunlight, stark sharp shadows, ice blue and gold tones"),

    ("korean", "sportswear", "high-fashion athleisure: color-blocked hoodie, joggers, retro sneakers",
     "bukchon",  "Bukchon Hanok Village rooftops, traditional tiled roofs, Seoul",
     "dramatic backlight against sky, silhouette rim light, warm sunset tones"),

    # ── CHINESE (4セット) ─────────────────────────────────────────────────
    ("chinese", "qipao",     "modern fitted qipao in jade silk, high slit, contemporary style",
     "shanghai_bund","The Bund waterfront at golden hour, Shanghai Art Deco buildings",
     "golden hour backlight over Huangpu River, long warm shadows, cinematic"),

    ("chinese", "casualdress","floral casual midi dress, denim jacket, white sneakers",
     "guilin",   "karst limestone peaks reflected in Li River, Guilin, misty morning",
     "morning mist light, soft atmospheric haze, cool blue-green palette"),

    ("chinese", "streetwear","Beijing hutong streetwear: cropped hoodie, wide jeans, bucket hat",
     "beijing_hutong","ancient hutong alley, Beijing, traditional grey brick walls",
     "harsh midday light cutting through alley shadows, dramatic contrast"),

    ("chinese", "blazer",    "tailored red power blazer, black wide-leg trousers, heels",
     "hongkong",  "Hong Kong skyline from Victoria Peak, city lights at dusk",
     "city light reflections, dramatic dusk sky, blue hour magic light"),

    # ── FRENCH (4セット) ──────────────────────────────────────────────────
    ("french", "trenchcoat", "classic beige trench coat, silk scarf, ballet flats, Breton stripes",
     "paris_cafe","Parisian sidewalk cafe, Haussmann buildings, cobblestone street",
     "soft overcast Parisian light, gentle diffused illumination, warm tones"),

    ("french", "sundress",   "lightweight linen sundress, straw hat, espadrilles",
     "provence",  "lavender fields of Provence at peak bloom, purple horizon",
     "strong summer directional light, vivid purple and gold color palette"),

    ("french", "eveningwear","Parisian chic evening gown in midnight blue silk, minimal jewelry",
     "eiffel",   "Eiffel Tower at night illuminated, Paris, twinkling lights",
     "theatrical spot-lit from below, dramatic blue night sky, golden tower glow"),

    ("french", "casual",     "Breton stripe top, high-waist wide jeans, loafers, tote bag",
     "montmartre","Montmartre artists quarter, steep steps, whitewashed walls, Paris",
     "dappled afternoon light through plane trees, warm Paris golden light"),

    # ── GERMAN (3セット) ──────────────────────────────────────────────────
    ("german", "dirndl",     "traditional Bavarian dirndl with apron, puffed sleeves, braids",
     "neuschwanstein","Neuschwanstein Castle on forested hill, Bavaria, autumn colors",
     "dramatic cloudy sky backlight, moody atmospheric light, deep autumn colors"),

    ("german", "minimalist", "German minimalist fashion: clean white linen shirt, structured trousers",
     "berlin_wall","East Side Gallery murals, Berlin Wall, vibrant graffiti art",
     "flat even light on murals, bright urban daylight, vivid color saturation"),

    ("german", "techwear",   "European techwear: functional jacket, technical trousers, clean boots",
     "munich",   "BMW Museum futuristic architecture, Munich, silvery modern steel",
     "architectural reflected light, cool industrial tones, stark modern light"),

    # ── SPANISH (3セット) ─────────────────────────────────────────────────
    ("spanish", "flamenco",  "traditional flamenco dress with ruffled layers, vibrant red and black",
     "seville",  "Seville cathedral and Giralda tower, Spanish square, evening light",
     "warm Spanish sunset light, dramatic golden hour, deep red and orange tones"),

    ("spanish", "casual",    "casual Mediterranean style: linen shirt knotted, wide shorts, sandals",
     "barcelona_beach","Barceloneta Beach, Barcelona, turquoise Mediterranean sea",
     "bright Mediterranean midday sun, strong light and shadow, warm sea tones"),

    ("spanish", "urbanfashion","Spanish urban fashion: crop top, high-waist trousers, block heels",
     "madrid_plaza","Plaza Mayor, Madrid, historic arcaded square, daytime",
     "even open shade light under arcades, warm stone reflected light"),

    # ── BRAZILIAN (3セット) ───────────────────────────────────────────────
    ("brazilian", "beachwear","Brazilian beach fashion: colorful cropped top, high-waist bikini bottom",
     "copacabana","Copacabana promenade, Rio de Janeiro, ocean and Sugarloaf Mountain",
     "harsh tropical sun at peak, strong shadows on mosaic sidewalk, vibrant colors"),

    ("brazilian", "streetwear","São Paulo streetwear: oversized graphic tee, board shorts, slides",
     "saopaulo_graffiti","São Paulo street art corridor, massive urban murals, city grit",
     "diffused overcast light on murals, even urban light, vivid color saturation"),

    ("brazilian", "dress",   "vibrant tropical wrap dress, natural curly hair, gold earrings",
     "amazon",   "Amazon rainforest waterfall, lush green canopy, tropical light",
     "backlight through jungle canopy, god rays piercing green foliage, warm green tones"),

    # ── ITALIAN (3セット) ─────────────────────────────────────────────────
    ("italian", "sunwear",   "Italian summer style: linen co-ord set, oversized sunglasses, sandals",
     "amalfi",  "Amalfi Coast cliffside road, pastel buildings, turquoise sea below",
     "intense Mediterranean noon sun, strong shadows, vivid blue sea backdrop"),

    ("italian", "fashionweek","Milan Fashion Week editorial look: structured blazer, tailored column skirt",
     "milan_duomo","Milan Duomo cathedral facade, Gothic spires, piazza",
     "diffused European light, architectural detail sharp, cool marble tones"),

    ("italian", "casualchic","Italian casual chic: silk blouse, wide linen trousers, leather mules",
     "venice",  "Venice canal bridge, gondolas below, historic buildings reflected",
     "soft water-reflected light, shimmering ripples on walls, warm golden tones"),

    # ── RUSSIAN (3セット) ─────────────────────────────────────────────────
    ("russian", "fur_coat",  "luxurious long fur coat over black turtleneck, leather boots",
     "moscow_winter","Red Square in heavy snowfall, St Basil's Cathedral, Moscow winter",
     "blue winter overcast light, snowfall diffusion, dramatic cold palette"),

    ("russian", "ballet",    "white classical ballet dress tutu, pointe shoes, elegant posture",
     "bolshoi",  "Bolshoi Theatre grand interior, chandelier, gilded columns",
     "dramatic stage theatrical lighting from above, warm gold spotlight"),

    ("russian", "streetstyle","Russian street style: oversized parka, chunky sneakers, mom jeans",
     "stpetersburg","Nevsky Prospect canal, St Petersburg, European baroque facades",
     "low winter sun angle, long shadows on snow, muted cool tones"),

    # ── ARABIC/EMIRATI (3セット) ──────────────────────────────────────────
    ("arabic", "abaya_modern","modern tailored abaya in deep navy, subtle embroidery, minimal",
     "dubai_skyline","Dubai Marina skyline at sunset, glass towers, waterfront",
     "golden hour backlight over Gulf waters, dramatic tower silhouettes"),

    ("arabic", "traditional","flowing traditional thobe in white with gold thread embroidery",
     "desert",  "Arabian desert dunes at sunrise, rolling golden sand, vast sky",
     "low desert sunrise backlight, rim-lit against pale blue sky, golden sand glow"),

    ("arabic", "couture",    "Arab haute couture: structured embroidered jacket, wide silk trousers",
     "alula",   "AlUla ancient rock formation landscape, Hegra sandstone cliffs",
     "dramatic raking side-light on rock faces, warm ochre sand tones"),

    # ── INDIAN (3セット) ──────────────────────────────────────────────────
    ("indian", "saree",      "vibrant silk saree in peacock blue and gold, traditional jewelry",
     "taj_mahal","Taj Mahal at dawn, marble reflecting pool, Agra",
     "soft pink dawn light on white marble, perfect reflection, magical atmosphere"),

    ("indian", "salwar",     "embroidered salwar kameez in deep crimson, dupatta draped",
     "jaipur_palace","Hawa Mahal pink sandstone facade, Jaipur, Rajasthan",
     "afternoon warm golden light on pink sandstone, rich warm tones"),

    ("indian", "fusion",     "Indo-western fusion: embroidered crop top, wide dhoti pants, kolhapuri sandals",
     "kerala_backwater","Kerala backwater canals, coconut palms, houseboat, green landscape",
     "soft tropical overcast light, rich green atmosphere, warm humid tones"),

    # ── THAI (3セット) ────────────────────────────────────────────────────
    ("thai", "traditional",  "Thai traditional dress in golden silk, intricate headdress",
     "bangkok_temple","Wat Phra Kaew Grand Palace, golden chedi spires, Bangkok",
     "strong tropical midday light, golden reflections on spires, vivid blues and golds"),

    ("thai", "streetwear",   "Bangkok street style: pastel crop top, plaid mini skirt, platform boots",
     "chatuchak","Chatuchak weekend market, Bangkok, colorful stalls, tropical daylight",
     "bright open market light, vibrant color chaos, tropical heat haze"),

    ("thai", "resort",       "Thai resort wear: floral slip dress, golden accessories, bare feet",
     "railay_beach","Railay Beach limestone cliffs, Krabi, turquoise Andaman Sea",
     "perfect golden hour backlight over sea, silhouette rim light, warm tropical glow"),

    # ── VIETNAMESE (3セット) ──────────────────────────────────────────────
    ("vietnamese", "aodai",  "traditional Vietnamese áo dài in silk, fitted with flowing panels",
     "hoi_an",  "Hoi An ancient town, paper lanterns at night, Thu Bon river",
     "warm lantern light, colored reflections on water, magical night atmosphere"),

    ("vietnamese", "streetwear","Hanoi street style: graphic tee, high-waist jeans, slip-on sneakers",
     "hanoi_oldquarter","Hanoi Old Quarter narrow alley, French colonial architecture",
     "soft overcast tropical light, even illumination, warm weathered wall tones"),

    ("vietnamese", "casual", "lightweight linen set in sage green, sandals, woven hat",
     "halong_bay","Ha Long Bay limestone islands, emerald water, morning mist",
     "morning mist atmospheric light, cool blue-green tones, mystical soft light"),

    # ── INDONESIAN (2セット) ──────────────────────────────────────────────
    ("indonesian", "batik",  "traditional batik sarong and kebaya blouse, flower in hair",
     "bali_temple","Pura Besakih mother temple, Bali, volcanic mountain backdrop",
     "dramatic stormy sky backlight, volcanic rim light, deep spiritual atmosphere"),

    ("indonesian", "casual", "casual Balinese style: floral crop top, linen wide pants, sandals",
     "bali_terraces","Tegalalang rice terraces, Bali, vivid green terraced landscape",
     "tropical backlight, brilliant green rice, warm afternoon gold"),

    # ── TURKISH (3セット) ─────────────────────────────────────────────────
    ("turkish", "contemporary","Turkish contemporary fashion: structured kaftan coat over slim trousers",
     "istanbul_bosphorus","Bosphorus strait, Galata Bridge, Istanbul skyline, twilight",
     "blue hour magic light over water, warm bridge lights, cool sky tones"),

    ("turkish", "casual",    "casual Istanbul style: oversized blazer, straight jeans, sneakers",
     "grand_bazaar","Grand Bazaar covered market interior, colorful lanterns, Istanbul",
     "warm lantern light filtering through bazaar dome, rich warm gold tones"),

    ("turkish", "traditional","traditional Anatolian embroidered dress, silver jewelry",
     "cappadocia","Cappadocia fairy chimneys at sunrise, hot air balloons in distance",
     "soft pink sunrise light on tuff columns, warm golden horizon tones"),

    # ── DUTCH (2セット) ───────────────────────────────────────────────────
    ("dutch", "cycling_chic","Dutch cycling chic: structured wool coat, midi skirt, loafers",
     "amsterdam_canals","Amsterdam canal houses, bicycles, tulips, spring morning",
     "soft Dutch diffused northern light, even beautiful flat illumination"),

    ("dutch", "tulip",       "spring dress in tulip yellow, white blouse, comfortable flats",
     "keukenhof","Keukenhof tulip gardens, millions of blooms, Netherlands spring",
     "bright spring overcast light, saturated flower colors, even soft light"),

    # ── POLISH (2セット) ──────────────────────────────────────────────────
    ("polish", "folk",       "Polish folk dress: embroidered blouse, floral pattern skirt, folk jewelry",
     "krakow",  "Krakow Market Square, St Mary's Basilica, cobblestones, Poland",
     "warm afternoon European light, long shadows on cobblestones, rich tones"),

    ("polish", "streetwear", "Warsaw street fashion: oversized leather jacket, straight jeans",
     "warsaw",  "Warsaw Palace of Culture brutalist architecture, wide avenue",
     "dramatic low sun angle, strong architectural shadows, cool eastern European tones"),

    # ── SWEDISH (2セット) ─────────────────────────────────────────────────
    ("swedish", "minimalist", "Swedish minimalist fashion: clean white suit, minimal accessories",
     "stockholm_winter","Stockholm waterfront, Gamla Stan old town, winter blue light",
     "cold blue winter light, crisp sharp shadows on snow, Scandinavian palette"),

    ("swedish", "casual",    "Scandinavian casual: chunky knit sweater, straight jeans, leather boots",
     "swedish_forest","Swedish pine forest in autumn, red wooden cottage, golden foliage",
     "warm golden autumn backlight, rim-lit through pine trees, cozy atmosphere"),

    # ── DANISH (2セット) ──────────────────────────────────────────────────
    ("danish", "hygge",      "Danish hygge fashion: oversized chunky knit, wide corduroy trousers",
     "copenhagen","Nyhavn colorful harbor houses, Copenhagen, autumn afternoon",
     "soft overcast Nordic light, beautiful muted tones, hygge warmth"),

    ("danish", "minimalist", "Danish design minimalist: structured wool blazer, clean lines",
     "denmark_coast","Danish North Sea coastline, white sand dunes, grey sea sky",
     "dramatic coastal side-light, powerful cloud formations, cool grey tones"),

    # ── NORWEGIAN (2セット) ───────────────────────────────────────────────
    ("norwegian", "parka",   "high-performance outdoor parka, thermal layers, hiking boots",
     "fjord",   "Geirangerfjord from mountain viewpoint, waterfalls, deep blue fjord",
     "dramatic mountain backlight, misty waterfall atmosphere, epic scale light"),

    ("norwegian", "sweater", "traditional Selburose Nordic sweater pattern, warm wool",
     "aurora",  "Northern Lights aurora borealis over Norwegian mountain lake, reflection",
     "green and purple aurora light, icy reflection, cold starry sky atmosphere"),

    # ── FINNISH (2セット) ─────────────────────────────────────────────────
    ("finnish", "linen",     "Finnish linen summer dress, simple and clean Scandinavian style",
     "lakeland", "Finnish lake at midsummer midnight sun, birch trees, calm mirror water",
     "magical midnight sun golden light, extremely long shadows, warm pink tones"),

    ("finnish", "winter",    "Finnish winter fashion: down parka, wool hat, thermal layers",
     "lapland",  "Finnish Lapland snow landscape, pine trees heavy with snow, reindeer",
     "blue-white winter light, soft snowfall diffusion, magical Nordic silence"),

    # ── CZECH (2セット) ───────────────────────────────────────────────────
    ("czech", "bohemian",    "Bohemian style: flowy floral blouse, peasant skirt, ankle boots",
     "prague",  "Prague Old Town Square, Astronomical Clock, Gothic architecture",
     "warm golden hour light on Gothic stones, romantic Prague atmosphere"),

    ("czech", "casual",      "Czech casual: simple sweater, high-waist jeans, sneakers",
     "czech_countryside","Bohemian countryside, rolling green hills, castle on horizon",
     "soft European diffused light, lush green landscape, peaceful atmosphere"),

    # ── HUNGARIAN (2セット) ───────────────────────────────────────────────
    ("hungarian", "folk",    "Hungarian folk embroidery dress, Kalocsa floral pattern",
     "budapest", "Budapest Parliament on Danube River at golden hour, reflection",
     "spectacular golden hour over Danube, Parliament glow, warm ceremonial light"),

    ("hungarian", "urban",   "Budapest urban fashion: structured coat, ankle boots, leather bag",
     "budapest_ruin_bar","Budapest ruin bar district, eclectic decor, vintage courtyards",
     "warm string light atmosphere, eclectic colored lights, bohemian warmth"),

    # ── ROMANIAN (2セット) ────────────────────────────────────────────────
    ("romanian", "folk",     "Romanian folk costume: embroidered blouse, floral skirt, head wreath",
     "transylvania","Transylvanian medieval castle, Bran Castle on rocky hillside, Romania",
     "dramatic moody sky, atmospheric fog on hillside, Gothic mystery light"),

    ("romanian", "casual",   "casual Romanian style: knit cardigan, straight jeans, flat boots",
     "bucharest_park","Herastrau Park, Bucharest, lake reflections, city behind trees",
     "soft park light through trees, dappled afternoon shadows, calm tones"),

    # ── UKRAINIAN (2セット) ───────────────────────────────────────────────
    ("ukrainian", "vyshyvanka","traditional Ukrainian vyshyvanka embroidered blouse, sunflower wreath",
     "ukraine_sunflowers","Ukrainian sunflower field, vast horizon, blue sky with white clouds",
     "brilliant summer sun backlight, rim-lit hair in sunflower field, golden warmth"),

    ("ukrainian", "casual",  "urban Kyiv casual: oversized hoodie, wide straight jeans, white sneakers",
     "kyiv",    "Kyiv Maidan square, St Michael's Golden-Domed Monastery, blue sky",
     "bright summer daylight, clear blue sky, crisp architectural detail"),

    # ── HEBREW/ISRAELI (2セット) ──────────────────────────────────────────
    ("israeli", "urbanwear", "Tel Aviv urban fashion: linen shirt, tailored shorts, sandals",
     "telaviv_beach","Tel Aviv Bauhaus White City, beach promenade, Mediterranean",
     "Mediterranean afternoon light, warm white architecture, vivid blue sea sky"),

    ("israeli", "casual",    "casual desert-modern style: lightweight button shirt, cargo trousers",
     "negev",   "Negev Desert Ramon Crater, vast geological landscape, Israel",
     "dramatic desert light, long shadows in crater, warm ochre and deep blue sky"),

    # ── GREEK (2セット) ───────────────────────────────────────────────────
    ("greek", "summer",      "Greek island summer fashion: white linen dress, leather sandals",
     "santorini","Santorini caldera view, white cubic buildings, blue domed church",
     "brilliant Aegean afternoon light, deep blue sky and sea, blinding white walls"),

    ("greek", "evening",     "Mediterranean evening chic: draped silk dress in Aegean blue",
     "acropolis","Acropolis Parthenon at golden hour, Athens, ancient columns glowing",
     "warm golden hour on ancient marble, long column shadows, epic historical light"),

    # ── AMERICAN (4セット) ────────────────────────────────────────────────
    ("american", "jeans_tshirt","classic American look: fitted white tee, straight Levi's jeans, Chuck Taylors",
     "nyc_brooklyn","Brooklyn Bridge walkway, Manhattan skyline behind, New York",
     "dramatic NYC afternoon backlight, urban sky scraper silhouettes, power light"),

    ("american", "cowboy",   "American Western: Wrangler jeans, plaid shirt, cowboy boots and hat",
     "utah_canyon","Monument Valley buttes at sunset, Arizona, epic southwestern landscape",
     "incredible golden sunset backlight, silhouette buttes, red desert glow"),

    ("american", "streetwear","American street style: oversized varsity jacket, bike shorts, AJ1s",
     "la_sunset_strip","Sunset Strip, Los Angeles, palm trees, perpetual golden hour",
     "iconic LA golden hour side-light, warm California sun, long shadows"),

    ("american", "outdoors",  "Pacific Northwest outdoor: fleece pullover, hiking pants, trail runners",
     "yosemite", "Yosemite Valley, El Capitan granite wall, Half Dome, epic scale",
     "dramatic Yosemite light through valley, granite reflected light, majestic scale"),

    # ── MOROCCAN (3セット) ────────────────────────────────────────────────
    ("moroccan", "djellaba",  "traditional Moroccan djellaba in white with hood, babouche slippers",
     "marrakech_medina","Marrakech medina souk, spice market colors, narrow alley",
     "shaft of light through medina alley, dust particles in beam, warm spice tones"),

    ("moroccan", "fusion",    "modern Moroccan fusion: embroidered kaftan top, wide linen trousers",
     "sahara",  "Sahara Desert sand dunes, Erg Chebbi, Morocco, starry night sky",
     "milky way starlight, campfire warm light, desert night magic atmosphere"),

    ("moroccan", "caftan",    "formal Moroccan caftan in rich jewel tones, gold embroidery",
     "fes_medina","Fes tanneries colorful vats, medieval medina, aerial view",
     "strong midday overhead light, vivid tannery colors, geometric aerial composition"),

    # ── PORTUGUESE (2セット) ──────────────────────────────────────────────
    ("portuguese", "fado",    "Portuguese fado style: black dress, shawl, traditional elegant look",
     "lisbon_alfama","Lisbon Alfama district, tram tracks, azulejo tiles, golden light",
     "warm Lisbon late afternoon light, golden azulejo reflections, nostalgic tones"),

    ("portuguese", "casual",  "casual Portuguese style: linen shirt, wide trousers, espadrilles",
     "algarve",  "Algarve sea stacks and golden cliffs, Atlantic Ocean, Portugal",
     "dramatic Atlantic golden hour backlight, powerful cliff silhouettes, warm gold"),

    # ── MEXICAN (3セット) ─────────────────────────────────────────────────
    ("mexican", "folklore",   "Mexican folkloric dress: embroidered Oaxacan huipil, colorful skirt, flowers in hair",
     "oaxaca",  "Oaxaca central market, alebrijes and textiles, colonial architecture",
     "bright midday tropical light, vivid saturated colors, festive atmosphere"),

    ("mexican", "streetwear", "Mexico City street style: graphic crop top, high-waist jeans, platform sandals",
     "cdmx_reforma","Paseo de la Reforma boulevard, Mexico City, modern towers and monuments",
     "warm Mexican golden hour, long boulevard shadows, vibrant urban energy"),

    ("mexican", "charro",     "modern charra outfit: fitted riding jacket with embroidery, wide-brim hat",
     "guadalajara","Guadalajara Hospicio Cabañas colonial courtyard, UNESCO heritage site",
     "dramatic courtyard shaft of light, warm colonial stone reflected light"),

    # ── ARGENTINIAN (3セット) ─────────────────────────────────────────────
    ("argentinian", "tango",  "Argentine tango dress: fitted split skirt in deep red, stiletto heels",
     "buenosaires_santelmo","San Telmo street tango, cobblestone alley, Buenos Aires",
     "warm evening street light, intimate tango atmosphere, passionate golden tones"),

    ("argentinian", "gaucho", "modern gaucha fashion: wide bombacha trousers, leather boots, beret",
     "patagonia", "Patagonia Torres del Paine peaks, turquoise lake, dramatic sky",
     "dramatic Patagonian light, powerful storm clouds, epic wilderness scale"),

    ("argentinian", "urban",  "Buenos Aires chic: structured blazer, straight trousers, leather loafers",
     "palermo",  "Palermo Soho neighborhood, Buenos Aires, street art and cafes",
     "warm afternoon Buenos Aires light, tree-lined streets, dappled shadow"),

    # ── COLOMBIAN (2セット) ───────────────────────────────────────────────
    ("colombian", "vallenata", "Colombian traditional: colorful vallenata dress, sombrero vueltiao hat",
     "cartagena", "Cartagena walled city, colourful colonial facades, Caribbean warmth",
     "strong Caribbean midday sun, vivid color-washed walls, tropical vitality"),

    ("colombian", "casual",   "Medellín street fashion: colorful crop top, high-waist jeans, sneakers",
     "medellin",  "Medellín cable car over comunas, city spread across green valley",
     "dramatic aerial light over valley, golden hour from gondola, urban magic"),

    # ── KENYAN (2セット) ──────────────────────────────────────────────────
    ("kenyan", "maasai",      "Maasai-inspired modern fashion: red shuka wrap, beaded jewelry, bold",
     "maasai_mara","Maasai Mara savanna at sunrise, acacia tree, wildebeest silhouettes",
     "spectacular African sunrise backlight, warm orange savanna glow, acacia silhouette"),

    ("kenyan", "nairobi_style","contemporary Nairobi fashion: wax print structured blazer, tailored trousers",
     "nairobi",  "Nairobi city skyline, modern glass towers, urban Africa energy",
     "bold African noon light, strong architectural shadows, vibrant city palette"),

    # ── NIGERIAN (2セット) ────────────────────────────────────────────────
    ("nigerian", "ankara",    "Nigerian Ankara wax print fitted dress, head wrap gele, bold pattern",
     "lagos_island","Lagos Island skyline, Victoria Island waterfront, Gulf of Guinea",
     "tropical golden afternoon light, water reflections on city, warm African sun"),

    ("nigerian", "agbada_modern","modernized agbada-inspired silhouette: oversized embroidered top, wide trousers",
     "abuja",    "Abuja National Mosque, Federal Capital Territory, formal architecture",
     "clean afternoon light on white marble, architectural precision, Nigerian pride"),

    # ── FILIPINO (2セット) ────────────────────────────────────────────────
    ("filipino", "barong",    "feminine barong Tagalog in piña fabric, traditional elegance",
     "intramuros","Intramuros walled city, Manila, Spanish colonial fort walls",
     "late afternoon golden light on Spanish stone walls, warm historic atmosphere"),

    ("filipino", "casual",    "Manila street casual: graphic tee, denim shorts, chunky sneakers",
     "batanes_island","Batanes island rolling green hills, stone houses, Pacific Ocean",
     "dramatic Pacific light over clifftop, powerful cloud formations, vivid green"),

    # ── AUSTRALIAN (2セット) ──────────────────────────────────────────────
    ("australian", "beach",   "Australian beach style: surf brand crop tee, high-waist bikini shorts, flip-flops",
     "bondi_beach","Bondi Beach golden sand, breaking waves, Sydney in distance",
     "brilliant Australian summer sun, sparkling ocean, fresh energetic light"),

    ("australian", "outback", "Australian outback style: wide-brim Akubra hat, linen shirt, work boots",
     "uluru",    "Uluru sacred rock at sunset, red desert, Northern Territory",
     "dramatic red desert sunset, Uluru glowing deep crimson, vast outback sky"),

    # ── EGYPTIAN (1セット) ────────────────────────────────────────────────
    ("egyptian", "modern",    "modern Egyptian fashion: structured linen shirt, wide trousers, leather sandals",
     "giza_pyramids","Great Pyramids of Giza at sunset, golden desert sands, dramatic sky",
     "spectacular sunset backlight, pyramids silhouetted against blazing orange sky"),

    # ── SOUTH AFRICAN (2セット) ───────────────────────────────────────────
    ("southafrican", "ndebele","Ndebele-inspired geometric patterned outfit, traditional beaded collar",
     "cape_town_table","Cape Town Table Mountain, city bowl below, Atlantic Ocean",
     "dramatic Table Mountain cloud tablecloth light, panoramic coastal epic scale"),

    ("southafrican", "urban", "Cape Town creative fashion: printed linen co-ord, statement jewelry",
     "bo_kaap",  "Bo-Kaap colorful houses, Cape Malay Quarter, cobblestone steps",
     "bright Cape Town morning light, saturated pastel house colors, vivid street"),
]

assert len(BEAUTY_SETS) == TOTAL_SETS, f"セット数エラー: {len(BEAUTY_SETS)} (期待: {TOTAL_SETS})"

# ─── Checkpoint ────────────────────────────────────────────────────────────
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

# ─── 30言語ラベリング（Gemini Vision） ────────────────────────────────────
def label_image(image_path: Path, nationality: str) -> tuple[dict, int, int]:
    """画像を見て30カ国語タイトル + タグ15個を生成。Returns (labels_dict, in_tok, out_tok)"""
    img_bytes = image_path.read_bytes()

    gemini_prompt = f"""You are a world-class multilingual creative director specializing in travel and fashion photography.

Analyze this image. It shows a beautiful {nationality} woman in a specific fashion style at a specific location.

For each of the 30 language codes listed below, create:
1. "title": An evocative, poetic title (5–10 words) describing this specific woman, outfit, and location — in that language
2. "tags": Exactly 15 descriptive keywords/tags in that language covering: the nationality, clothing style, location/landmark, mood, lighting, colors, and photographic style (no hashtags, no punctuation)

Return ONLY a valid JSON object:
{{
  "en-US": {{"title": "...", "tags": ["tag1", ..., "tag15"]}},
  "ja-JP": {{"title": "...", "tags": ["tag1", ...]}},
  ...all 30 languages...
}}

Language codes:
{COUNTRIES_BRIEF}

Rules:
- Write naturally in each target language (not word-for-word translation)
- Tags must reflect what is actually visible in the image
- Use native script (Japanese kanji/kana, Arabic, Cyrillic, etc.)
- Return ONLY the JSON object, no markdown, no explanation"""

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
                print(f"        ⚠️  ラベリングエラー: {e}. {wait}秒後リトライ...")
                time.sleep(wait)
            else:
                print(f"        ❌ ラベリング失敗（フォールバック）: {e}")
                fb = {}
                for c in COUNTRIES:
                    fb[c["lang_code"]] = {
                        "title": f"Beautiful {nationality.capitalize()} woman",
                        "tags":  ["world beauty", "fashion", "travel", nationality,
                                  "portrait", "street photography", "style", "culture",
                                  "elegant", "global beauty", "woman", "photography",
                                  "lifestyle", "fashion art", "international"],
                    }
                return fb, 500, 200

# ─── JSON export ───────────────────────────────────────────────────────────
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
    print(f"    📤 labeled_images.json 更新完了 ({len(out)}件)")

# ─── Checkpoint ────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "completed_sets": [],
        "total_images": 0,
        "total_cost_usd": 0.0,
        "started_at": datetime.now().isoformat(),
    }

def save_checkpoint(cp: dict):
    CHECKPOINT.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")

# ─── Prompt builder ────────────────────────────────────────────────────────
def build_prompt(nationality: str, outfit_desc: str, location_desc: str,
                 lighting_desc: str, camera: dict) -> str:
    # 国籍を自然な形で埋め込む
    nat_map = {
        "japanese": "Japanese woman", "korean": "Korean woman",
        "chinese": "Chinese woman", "french": "French woman",
        "german": "German woman", "spanish": "Spanish woman",
        "brazilian": "Brazilian woman", "italian": "Italian woman",
        "russian": "Russian woman", "arabic": "Emirati woman",
        "indian": "Indian woman", "thai": "Thai woman",
        "vietnamese": "Vietnamese woman", "indonesian": "Indonesian woman",
        "turkish": "Turkish woman", "dutch": "Dutch woman",
        "polish": "Polish woman", "swedish": "Swedish woman",
        "danish": "Danish woman", "norwegian": "Norwegian woman",
        "finnish": "Finnish woman", "czech": "Czech woman",
        "hungarian": "Hungarian woman", "romanian": "Romanian woman",
        "ukrainian": "Ukrainian woman", "israeli": "Israeli woman",
        "greek": "Greek woman", "american": "American woman",
        "moroccan": "Moroccan woman", "portuguese": "Portuguese woman",
    }
    subject = nat_map.get(nationality, f"{nationality.capitalize()} woman")

    prompt = (
        f"A beautiful {subject} wearing {outfit_desc}, "
        f"photographed at {location_desc}. "
        f"Camera: {camera['desc']}. "
        f"Lighting: {lighting_desc}. "
        f"{QUALITY_TAGS}."
    )
    return prompt

# ─── Image generation with retry ──────────────────────────────────────────
def generate_single_image(prompt_text: str, out_dir: Path, filename: str,
                          max_retries: int = 5) -> Path | None:
    """
    1プロンプト → 1枚の独立した単一画像を生成。
    コラージュ・グリッド・マルチパネルは一切生成しない。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    delay = 30

    for attempt in range(max_retries):
        try:
            resp = imagen_client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=prompt_text,
                config=types.GenerateImagesConfig(
                    number_of_images=1,           # 必ず1枚のみ
                    aspect_ratio="3:4",           # ポートレート比率
                    output_mime_type="image/png",
                    safety_filter_level="BLOCK_ONLY_HIGH",
                    person_generation="ALLOW_ADULT",
                ),
            )
            if not resp.generated_images:
                print(f"    ⚠️  画像なし (空レスポンス). スキップ: {filename}")
                return None
            fpath = out_dir / filename
            fpath.write_bytes(resp.generated_images[0].image.image_bytes)
            print(f"      💾 {fpath.name}")
            return fpath

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                wait = delay * (2 ** attempt)
                print(f"    ⚠️  レート制限 (429). {wait}秒後にリトライ ({attempt+1}/{max_retries})...")
                time.sleep(wait)
            elif "block" in err_str.lower() or "safety" in err_str.lower():
                print(f"    ⛔ セーフティブロック. スキップ: {filename}")
                return None
            elif attempt < max_retries - 1:
                print(f"    ❌ エラー: {e}. 30秒後リトライ ({attempt+1}/{max_retries})...")
                time.sleep(30)
            else:
                print(f"    ❌ {max_retries}回失敗. スキップ: {e}")
                return None
    return None

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="世界美女図鑑 第2章 生成スクリプト")
    parser.add_argument("--test",  action="store_true", help="テスト: 最初の1セット(4枚)のみ生成")
    parser.add_argument("--batch", type=int, default=0, metavar="N",
                        help="バッチ番号 1〜8 を指定 (各バッチ約50枚)")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトを表示するだけ (生成しない)")
    args = parser.parse_args()

    # ── 対象セット範囲の決定 ──
    if args.test:
        target_sets = [0]           # セット0の4枚のみ
        print("[MODE] テスト: 1セット (4枚) のみ生成")
    elif args.batch > 0:
        if not 1 <= args.batch <= 8:
            print("❌ --batch は 1〜8 で指定してください")
            return
        start = (args.batch - 1) * BATCH_SIZE
        end   = min(start + BATCH_SIZE, TOTAL_SETS)
        target_sets = list(range(start, end))
        print(f"[MODE] バッチ {args.batch}/8: セット{start}〜{end-1} ({len(target_sets)}セット = {len(target_sets)*4}枚)")
    else:
        target_sets = list(range(TOTAL_SETS))
        print(f"[MODE] 全件: {TOTAL_SETS}セット = {TOTAL_SETS*4}枚")

    cp = load_checkpoint()
    completed = set(cp["completed_sets"])
    pending   = [i for i in target_sets if i not in completed]

    print(f"\n[STATUS] 完了済みセット: {len(completed)}/{TOTAL_SETS}")
    print(f"[STATUS] 今回対象: {len(target_sets)}セット / 残り実行: {len(pending)}セット")
    print(f"[STATUS] 総出力画像: {cp['total_images']}枚 / 総コスト: ${cp['total_cost_usd']:.3f}\n")

    if not pending:
        print("✅ 対象セットはすべて完了しています。")
        return

    conn                = init_db()
    IMG_PRICE_PER_IMAGE = 0.020   # Imagen 3 Fast: $0.02/枚
    images_generated    = 0
    label_cost_total    = 0.0

    for i, set_idx in enumerate(pending):
        nat, out_key, out_desc, loc_key, loc_desc, lighting = BEAUTY_SETS[set_idx]

        # 通し連番 = START_SEQ + set_idx × 4 (1セット4枚)
        seq_base = START_SEQ + set_idx * 4
        out_dir  = OUTPUT_DIR / nat
        subfolder = f"world_beauty_series/{nat}"

        print(f"[{i+1}/{len(pending)}] セット{set_idx:03d} | {nat.upper()} | {out_key} | {loc_key}")
        print(f"  連番: {seq_base}〜{seq_base+3} | 出力: {out_dir.name}/")

        # ── 4回の独立したリクエスト（各1枚・各カメラアングル）────────────
        set_saved_paths = []
        for j, angle in enumerate(CAMERA_ANGLES):
            seq   = seq_base + j
            fname = f"{seq:04d}_{nat}_{out_key}_{loc_key}_{angle['key']}.png"

            # 1画像1プロンプト — コラージュ・マルチパネル指示は一切含まない
            prompt = build_prompt(nat, out_desc, loc_desc, lighting, angle)

            if args.dry_run:
                print(f"  [{angle['key']}] seq={seq} | {prompt[:110]}...")
                continue

            result = generate_single_image(prompt, out_dir, fname)
            if result:
                set_saved_paths.append(result)
                images_generated += 1
                cp["total_images"] += 1
                cp["total_cost_usd"] = round(
                    cp["total_cost_usd"] + IMG_PRICE_PER_IMAGE, 4)

            # Imagen レート制限対策
            time.sleep(4)

        if args.dry_run:
            print()
            continue

        if not set_saved_paths:
            print(f"  ⚠️  セット全滅 (生成失敗)\n")
            continue

        # ── 生成済み画像を1枚ずつ30言語ラベリング ───────────────────────
        print(f"  🎨 ラベリング開始 ({len(set_saved_paths)}枚)...")
        for img_path in set_saved_paths:
            labels, in_tok, out_tok = label_image(img_path, nat)
            gem_cost = (in_tok * GEM_IN_PER_M + out_tok * GEM_OUT_PER_M) / 1_000_000
            label_cost_total += gem_cost
            cp["total_cost_usd"] = round(cp["total_cost_usd"] + gem_cost, 4)

            rel_path = img_path.relative_to(BASE_DIR).as_posix()
            save_label(conn, rel_path, img_path.name, subfolder, CATEGORY,
                       in_tok, out_tok, IMG_PRICE_PER_IMAGE + gem_cost, labels)
            print(f"    ✅ {img_path.name} → DB保存")
            time.sleep(2)  # Gemini レート制限対策

        cp["completed_sets"].append(set_idx)
        save_checkpoint(cp)
        print(f"  ✅ {len(set_saved_paths)}枚生成 + ラベル済み | "
              f"累計: {cp['total_images']}枚 / ${cp['total_cost_usd']:.3f}\n")

        # 10セットごとにJSONエクスポート
        if (i + 1) % 10 == 0:
            export_json(conn)

    # 最終JSONエクスポート
    if not args.dry_run:
        export_json(conn)

    print("=" * 60)
    print(f"✅ 完了: {images_generated}枚生成 + 全画像ラベリング済み")
    print(f"   累計: {cp['total_images']}枚 | 総コスト: ${cp['total_cost_usd']:.3f}")
    print(f"   ラベリングコスト: ${label_cost_total:.3f} (¥{label_cost_total*USD_TO_JPY:,.0f})")
    print(f"   保存先: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
