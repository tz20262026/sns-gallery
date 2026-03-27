# -*- coding: utf-8 -*-
"""
宇宙テーマ 3,000枚 生成 + 30カ国語詩ラベリング
════════════════════════════════════════════════
モデル : Imagen 3 Fast (Vertex AI) + Gemini 2.5 Flash (Gemini API)
比率  : 1:1 スクエア
予算  : ¥15,000（$100）上限

実行方法:
  テスト(12枚):  python generate_cosmic.py --test
  本番(3000枚): python generate_cosmic.py
  再開         : python generate_cosmic.py          ← 自動的に続きから
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

import os, json, time, argparse, sqlite3, base64, random, re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# ─── Paths & Config ────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
IMAGES_DIR  = BASE_DIR / "images" / "cosmic"
DB_PATH     = BASE_DIR / "image_labels.db"
EXPORT_JSON = BASE_DIR / "labeled_images.json"
CHECKPOINT  = BASE_DIR / "cosmic_progress.json"

PROJECT_ID = "spreadsheet-bot-489912"
LOCATION   = "us-central1"
CANDIDATE_COUNT = 4

# 予算
BUDGET_USD     = 100.0          # ¥15,000 ≒ $100
USD_TO_JPY     = 150
IMAGEN_PRICE   = 0.020          # Imagen 3 Fast: $0.02/枚
GEM_IN_PER_M   = 0.15           # Gemini 2.5 Flash input
GEM_OUT_PER_M  = 0.60           # Gemini 2.5 Flash output

# 新ジャンル（カテゴリ）
CATEGORIES_COSMIC = ["cosmic-beauty", "alien-life", "space-worlds"]

# ─── Load environment ───────────────────────────────────────────────────────
load_dotenv(BASE_DIR / "01_SNS運用/spreadsheet_bot/.env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY が .env に見つかりません")

# ─── Clients ────────────────────────────────────────────────────────────────
from google import genai
from google.genai import types

# Vertex AI client（Imagen生成用）
imagen_client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
)

# Gemini API client（詩ラベリング用）
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL  = "gemini-2.5-flash"
IMAGEN_MODEL  = "imagen-3.0-fast-generate-001"

# ─── 30言語リスト ─────────────────────────────────────────────────────────
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

# ─── プロンプト生成（激変バリエーション方式） ────────────────────────────
def _build_prompts():
    """750プロンプト - 美女×エイリアン×宇宙を激しくミックス、スタイルを毎回激変"""

    random.seed(42)  # 再現性のため固定シード

    # ── 美女系被写体 (30種) ──────────────────────────────────────────────
    BEAUTY_SUBJECTS = [
        "a transcendent space goddess with aurora borealis flowing through her luminescent hair",
        "a cyberpunk femme fatale with mercury-silver skin and glowing neural crown implants",
        "a xenobiology researcher whose body has partially merged with bioluminescent alien flora",
        "an ancient star-born deity in human form, galaxies swirling visible through translucent skin",
        "a post-human beauty where flesh and living crystal have grown together over centuries",
        "a void dancer who moves between dimensions, her body leaving trails of captured starlight",
        "a female time archaeologist draped in artifacts from 1000 extinct alien civilizations",
        "a bioluminescent oracle whose prophecies glow as patterns moving beneath her skin",
        "a deep space salvager with mechanical eye implants that perceive dark matter streams",
        "a shapeshifter queen in humanoid form, her true cosmic nature bleeding through her eyes",
        "a psychic navigator whose mind directly interfaces with the living fabric of spacetime",
        "an evolved human from year 5000, her DNA containing sequences written by dying stars",
        "a cosmic sorceress who weaves impossible spells from collapsed stellar remnants",
        "a sentient AI given a perfect goddess body, discovering emotion and beauty for the first time",
        "the last empress of a dead civilization, carrying her entire world's memory as holographic tattoos",
        "a war goddess born in the heart of a supernova, clad in crackling plasma armor",
        "a dream architect who builds entire pocket universes while in deep meditative sleep",
        "a celestial cartographer whose body tattoos are accurate maps of unknown galaxy clusters",
        "a gravity manipulator whose physical form bends spacetime visibly around her",
        "a memory thief who collects and wears the final thoughts of dying stars as jewelry",
        "an alien-human hybrid with iridescent compound eyes and skin that shifts like a nebula",
        "a femme fatale bounty hunter operating in the space between parallel timelines",
        "a genetic artist who sculpts living alien ecosystems using only her hands",
        "a star singer whose voice restructures molecular bonds across vast cosmic distances",
        "a ghost from the heat death of the universe, haunting its own distant past",
        "a cosmic huntress tracking the last dragon in a universe where mythologies are real",
        "an exile princess from a civilization that lived inside a black hole",
        "a biotech surgeon who rebuilds alien bodies using both organic and crystalline components",
        "a chaos mathematician who can predict the future by reading the patterns in nebulae",
        "a stellar medium who channels the personalities of long-dead civilizations through her body",
    ]

    # ── エイリアン系被写体 (30種) ────────────────────────────────────────
    ALIEN_SUBJECTS = [
        "an ancient being made of compressed time, its form shifting between geological eras",
        "a hive-mind empress whose body is a thriving living ecosystem of alien microorganisms",
        "a crystalline entity that feeds on starlight and communicates in gravitational waves",
        "a plasma-based predator that hunts black holes as prey across the cosmic void",
        "a sentient nebula temporarily given solid form through advanced alien compression technology",
        "a multi-dimensional being whose 3D shadow is the only part humans can perceive",
        "a xenomorphic philosopher whose body secretes knowledge as bioluminescent golden fluid",
        "a cosmic symbiote that bonds with dying stars and extends their lifespan by millennia",
        "an alien fertility deity whose mere presence causes new stars to ignite and form",
        "a void leviathan that drifts between galaxy clusters for billions of years in peace",
        "a photonic consciousness made entirely of coherent structured laser light",
        "a silicon-based forest creature that evolved on an airless world of razor crystal spires",
        "an ancient guardian of a dead universe, eternally waiting for something new to protect",
        "a magnetic pole entity living inside the aurora columns of a gas giant's atmosphere",
        "a quantum observer whose act of watching fundamentally changes the object observed",
        "a dimensional rift creature that manifests as impossible non-Euclidean geometry",
        "an apex predator of the cosmic void, shaped by five billion years of ruthless evolution",
        "a living archive of a destroyed civilization, its body physically containing all their art",
        "a star whale the size of a solar system, serenely grazing on stellar nurseries",
        "an alien diplomat made of pure empathy, its face reflecting the emotions of all who see it",
        "a deep time entity that experiences a human lifetime as a single heartbeat",
        "a color-based lifeform that exists as shifting spectra impossible for human eyes to fully process",
        "a gravity well creature that uses curved spacetime as a web to catch cosmic rays",
        "an acoustic being that lives in the sonic atmosphere of a gas giant, made of standing waves",
        "a mirror entity made entirely of reflection, showing what might have been",
        "a death-eater organism that thrives in the remains of supernova explosions",
        "a living equation that moves through the universe solving unsolvable mathematical proofs",
        "a paradox creature that exists in two mutually exclusive states simultaneously",
        "an inter-dimensional archaeologist made of questions rather than matter",
        "a cosmic horror so beautiful that witnessing it causes enlightenment rather than madness",
    ]

    # ── 宇宙絶景被写体 (30種) ────────────────────────────────────────────
    SPACE_SUBJECTS = [
        "the violent collision of two spiral galaxies seen from a surviving inhabited planet",
        "a ringworld the size of Earth's orbit wrapped around a white dwarf in its final era",
        "the blood-and-gold interior of a nebula seen from deep within its glowing heart",
        "a binary pulsar creating a cosmic lighthouse visible from fifty million light-years away",
        "the precise terrible moment a supermassive black hole begins consuming a sun-like star",
        "an alien megacity straddling the eternal day-night border of a tidally locked planet",
        "a quantum storm where parallel universe versions of the same location briefly overlap",
        "Earth's final sunset as the red giant sun begins its slow catastrophic expansion",
        "a wormhole transit station at the gravitational center of a galaxy cluster",
        "a rogue planet wandering between galaxies alone in absolute darkness for billions of years",
        "a Dyson sphere half-constructed, its imprisoned star blazing through the unfinished gap",
        "the absolute void between galaxy filaments, 300 million light-years of pure emptiness",
        "the cosmic web seen at a scale where entire galaxy clusters are mere luminous nodes",
        "a white hole violently pouring matter and energy into an infant virgin universe",
        "an alien world ocean where continent-sized organisms drift serenely like sky jellyfish",
        "the impossible surface of a neutron star, exotic matter forming alien architecture",
        "a pocket universe contained within a single perfect crystal the size of a human fist",
        "the actual moment of cosmic creation, the Big Bang witnessed from inside its singularity",
        "a graveyard of dead civilizations' megastructures slowly orbiting each other in cold space",
        "an intergalactic void storm 10,000 light-years wide, visible as charged particle rivers",
        "a pulsar's lighthouse beam sweeping across a graveyard of frozen terraformed worlds",
        "the last stars in a universe trillions of years old, each burning slower than a heartbeat",
        "an alien cityscape built entirely inside an active volcano on a high-gravity super-Earth",
        "a cosmic web node where 47 galaxy filaments meet, the most densely populated place in existence",
        "the moment of first contact between two civilizations that evolved in the same galaxy",
        "a generation ship 700 years into its journey, all original crew long dead, new civilization inside",
        "a stellar nursery where 10,000 stars are being born simultaneously in a cloud of cosmic fire",
        "the event horizon of a black hole captured in perfect clarity from a safe orbiting observatory",
        "an alien library planet where every piece of information ever created is stored in crystal spires",
        "the heat death of a local universe, the last quantum fluctuation before eternal silence",
    ]

    # ── 環境・背景 (25種) ────────────────────────────────────────────────
    ENVIRONMENTS = [
        "inside a gothic cathedral built from the fused bones of dead stars",
        "at the exact event horizon of a supermassive black hole, time visibly frozen",
        "in an alien garden where flowers bloom once every million years in slow motion",
        "aboard a generation ship 700 years into an intergalactic voyage, generations removed",
        "in the ruins of a Type IV civilization's incomprehensible abandoned experiment",
        "at the geometric center of the Milky Way, oldest stars in attendance",
        "inside a living biological spaceship evolved from deep-space coral organisms",
        "on a world where pure mathematics is the native spoken language of all life",
        "in the quantum foam at the absolute smallest possible scale of physical reality",
        "inside a collapsed stellar remnant repurposed as a thriving underground civilization",
        "at the precise moment two eternal timelines permanently and catastrophically diverge",
        "in a living museum containing every extinct species from across a billion galaxies",
        "on a world made entirely of crystallized frozen moments of time",
        "in an alien ecosystem that evolved entirely in the hard vacuum of deep space itself",
        "inside a neutron star's exotic atmosphere where physics behaves impossibly",
        "at the chaotic confluence of three wormholes creating impossible recursive geometry",
        "on an asteroid that is itself a conscious sleeping entity of immense slow patience",
        "in a dimension where color and sound are not separate phenomena but one",
        "inside the dreaming mind of a cosmic deity whose dreams are the physical universe",
        "at the boundary membrane between matter and pure organized information energy",
        "in the space between thoughts of a being that thinks in geological time",
        "inside a star's corona, surrounded by plasma loops the size of continents",
        "in an alien amphitheater carved into a comet that has traveled for a billion years",
        "at a cosmic crossroads where the laws of physics vary by direction traveled",
        "inside a living planet whose continents are organs and oceans are blood",
    ]

    # ── アートスタイル（激変の核心！34種） ──────────────────────────────
    ART_STYLES = [
        # フォトリアル系
        "ultra-photorealistic 8K portrait photography, Hasselblad medium format quality, perfect 1:1 square",
        "hyperrealistic CGI render, Unreal Engine 5 Lumen ray-tracing, sub-surface scattering, 8K square",
        "NASA Hubble Space Telescope photographic quality, scientific imaging, extreme spectral detail, 1:1",
        "fashion photography by Annie Leibovitz, large format studio, 8K masterwork, square format",
        "National Geographic wildlife photography style applied to alien life, perfect 8K, 1:1",
        # アート絵画系
        "Renaissance oil painting master discovering science fiction, Caravaggio chiaroscuro, 1:1 square",
        "loose expressive watercolor with ink wash details, cosmic colors bleeding beautifully, square",
        "Art Nouveau illustration, Alphonse Mucha-inspired cosmic motifs, flowing organic lines, 1:1",
        "ukiyo-e woodblock print aesthetic applied to space age imagery, Hokusai meets NASA, square",
        "impressionist oil painting, thick impasto technique, cosmic colors blending freely, 1:1",
        "surrealist oil painting, Salvador Dali meets astrophysics, Magritte logic, square",
        "stained glass window cathedral aesthetic, divine light filtering through cosmic imagery, 1:1",
        "baroque oil painting, extreme dramatic chiaroscuro, divine cosmic subject, golden frame, 1:1",
        "pointillist technique where every single dot is a distinct star, Georges Seurat in space, square",
        "fresco painting technique directly on ancient cosmic stone, ancient meets far future, square",
        # デジタルアート系
        "Hollywood concept art by the greatest sci-fi illustrators of the century, 8K digital, 1:1",
        "digital painting, Greg Rutkowski meets cosmic horror beauty, dramatic lighting, 8K square",
        "glitch art aesthetic, corrupted cosmic data streams bleeding through digital cracks, 1:1 square",
        "vaporwave aesthetic, cosmic neon pastels, geometric grid overlays, chromatic aberration, square",
        "maximum cyberpunk neon illustration, hyper-saturated, city lights reflected in rain, 8K 1:1",
        "biopunk organic-technology fusion, living circuits and cosmic biology merged seamlessly, square",
        "datamosh style, digital temporal decay revealing raw cosmic truth underneath, 1:1",
        "retro 1970s NASA space program illustration style, optimistic futurism, gouache, square",
        # アニメ・マンガ系
        "anime theatrical film quality, Makoto Shinkai cosmic beauty and emotional depth, 8K square",
        "Studio Ghibli master background painting quality applied to alien world environments, 1:1",
        "manga ink illustration with heavy brushwork, cosmic scale and dramatic impact, square format",
        "mecha anime aesthetic with cosmic horror undertones, giant scale, mechanical detail, 8K 1:1",
        # 特殊・実験的スタイル
        "extreme long exposure astrophotography, time made physically visible as light trails, 1:1 square",
        "infrared photography aesthetic revealing hidden cosmic heat structures in false color, square",
        "double exposure photography seamlessly merging cosmic and biological forms, 1:1",
        "bioluminescence deep-sea photography aesthetic applied to space, ethereal darkness and glow, square",
        "tilt-shift miniature photography making entire galaxies look like delicate model sets, 1:1",
        "vintage analog film grain, Kodachrome palette, 1970s documentary quality meets cosmic subject, square",
        "microscopy aesthetic at cosmic scales, scanning electron microscope beauty, extreme macro, 1:1",
    ]

    # ── ライティング（20種） ─────────────────────────────────────────────
    LIGHTING = [
        "lit by the catastrophic dying light of a red giant star in final expansion",
        "under a magnetar's aurora painting everything in impossible gamma-ray colors",
        "illuminated by a sweeping pulsar beam, stroboscopic cosmic lighthouse effect",
        "lit from within by trillions of bioluminescent alien microorganisms in the atmosphere",
        "by the eerie blue Cherenkov radiation of a cosmic ray shower impact",
        "under the prismatic scattered light of a planet's ring system catching twin suns",
        "in total absolute darkness except for hawking radiation glow of a black hole",
        "drenched in the harsh ultraviolet blue of a young O-type supergiant star",
        "under the warm amber of an ancient K-type star like a much older version of our Sun",
        "lit by volcanic lightning on a sulfur-moon of a gas giant, hellish and beautiful",
        "under stroboscopic pulsar light, time seeming to skip and freeze",
        "illuminated by neutron star merger kilonova flash, r-process elements raining gold",
        "in the deep shadow of a partially constructed Dyson sphere, dramatic penumbra",
        "lit by quantum vacuum fluctuation radiation, the light of nothing becoming something",
        "under cold cosmic microwave background radiation made physically visible",
        "drenched in the specific orange-red warmth of a dying M-dwarf star's last light",
        "by concentrated and focused starlight through alien prismatic crystal architecture",
        "under the briefest gamma-ray burst afterglow, the most violent light in existence",
        "in the perpetual purple twilight of a tidally locked world's terminator zone",
        "illuminated by the collective bioluminescence of a trillion organisms simultaneously",
    ]

    # ── カラーパレット（15種） ────────────────────────────────────────────
    COLOR_PALETTES = [
        "ultra-vivid cosmic: electric violet, hot magenta, acid green, electric plasma blue",
        "deep monochromatic crimson with pure silver highlights and absolute black shadows",
        "iridescent pastel: pearl white, soft lavender, rose gold, seafoam green",
        "dark and moody: deep midnight navy, obsidian black, cold steel silver, single warm light",
        "bioluminescent: deep black void with cyan, acid chartreuse, and blue-white organism glows",
        "retro 70s sci-fi: burnt orange, harvest gold, avocado green, chocolate brown",
        "hyper-saturated neon: hot pink, electric cyan, lime green, deep royal purple",
        "desaturated near-monochrome with single shocking accent color piercing through",
        "warm spectrum exclusively: amber, scarlet, golden yellow, copper, terracotta",
        "cool spectrum exclusively: glacial blue, arctic white, midnight navy, brushed silver",
        "alien sunset: impossible green sky, deep purple shadows, golden oblique light, crimson horizon",
        "rust and teal high-contrast complementary palette, maximum visual tension",
        "gold and black luxury cosmic, baroque opulence meets deep space void",
        "infrared false-color: the familiar made completely alien through spectrum shift",
        "prismatic rainbow dispersal, white light broken into its infinite components",
    ]

    # ── コンポジション（15種） ────────────────────────────────────────────
    COMPOSITIONS = [
        "extreme close-up portrait filling entire frame, microscopic pore-level skin detail",
        "ultra-wide establishing shot showing pure cosmic scale, subject infinitesimally tiny",
        "dramatic low-angle Dutch tilt composition with vertiginous depth",
        "overhead bird's-eye view from directly above, looking straight down",
        "ground-level worm's-eye view looking up through cosmic atmospheric layers",
        "rule of thirds, subject powerfully off-center, vast empty cosmos as counterweight",
        "perfect bilateral symmetry mirror composition, cosmic Rorschach inkblot",
        "golden ratio spiral composition flowing through cosmic structures organically",
        "frame within frame: alien architectural elements framing a distant cosmic vista",
        "pure silhouette against blazing cosmic backdrop, all detail lost in shadow",
        "split composition: two worlds or two eras divided by a razor-sharp central line",
        "motion blur composition capturing impossible movement through cosmic space",
        "explosive radial composition, everything erupting outward from a central focal point",
        "negative space composition where presence is defined entirely by its beautiful absence",
        "environmental portrait: the subject as a tiny precise detail in an overwhelming cosmos",
    ]

    prompts = []

    # ── タイプ1: 美女 × 宇宙環境 (250プロンプト) ─────────────────────────
    for i in range(250):
        subj  = BEAUTY_SUBJECTS[i % len(BEAUTY_SUBJECTS)]
        env   = ENVIRONMENTS[i % len(ENVIRONMENTS)]
        style = ART_STYLES[i % len(ART_STYLES)]
        light = LIGHTING[(i * 3) % len(LIGHTING)]
        color = COLOR_PALETTES[(i * 7) % len(COLOR_PALETTES)]
        comp  = COMPOSITIONS[(i * 5) % len(COMPOSITIONS)]
        prompts.append((f"{subj}, {env}, {color}, {light}, {comp}, {style}", "cosmic-beauty"))

    # ── タイプ2: エイリアン × 宇宙環境 (200プロンプト) ───────────────────
    for i in range(200):
        subj  = ALIEN_SUBJECTS[i % len(ALIEN_SUBJECTS)]
        env   = ENVIRONMENTS[(i + 5) % len(ENVIRONMENTS)]
        style = ART_STYLES[(i + 5) % len(ART_STYLES)]
        light = LIGHTING[(i * 4) % len(LIGHTING)]
        color = COLOR_PALETTES[(i * 11) % len(COLOR_PALETTES)]
        comp  = COMPOSITIONS[(i * 7) % len(COMPOSITIONS)]
        prompts.append((f"{subj}, {env}, {color}, {light}, {comp}, {style}", "alien-life"))

    # ── タイプ3: 宇宙絶景のみ (150プロンプト) ────────────────────────────
    for i in range(150):
        subj  = SPACE_SUBJECTS[i % len(SPACE_SUBJECTS)]
        style = ART_STYLES[(i + 10) % len(ART_STYLES)]
        light = LIGHTING[(i * 6) % len(LIGHTING)]
        color = COLOR_PALETTES[(i * 3) % len(COLOR_PALETTES)]
        comp  = COMPOSITIONS[(i * 9) % len(COMPOSITIONS)]
        prompts.append((f"{subj}, {color}, {light}, {comp}, {style}", "space-worlds"))

    # ── タイプ4: 美女 × エイリアン × 宇宙 全部ミックス (150プロンプト) ──
    for i in range(150):
        beauty = BEAUTY_SUBJECTS[i % len(BEAUTY_SUBJECTS)]
        alien  = ALIEN_SUBJECTS[(i + 11) % len(ALIEN_SUBJECTS)]
        space  = SPACE_SUBJECTS[(i + 7) % len(SPACE_SUBJECTS)]
        style  = ART_STYLES[(i + 17) % len(ART_STYLES)]
        light  = LIGHTING[(i * 9) % len(LIGHTING)]
        color  = COLOR_PALETTES[(i * 5) % len(COLOR_PALETTES)]
        comp   = COMPOSITIONS[(i * 11) % len(COMPOSITIONS)]
        cat    = ["cosmic-beauty", "alien-life", "space-worlds"][i % 3]
        prompts.append((
            f"{beauty} encountering {alien} against the backdrop of {space}, "
            f"{color}, {light}, {comp}, {style}",
            cat
        ))

    # 多様性を全体に均等分散するためシャッフル
    random.shuffle(prompts)
    return prompts[:750]

ALL_PROMPTS = _build_prompts()  # list of (prompt_text, category)
print(f"[INIT] 生成プロンプト数: {len(ALL_PROMPTS)} (目標: 750)")
assert len(ALL_PROMPTS) == 750, f"プロンプト数が不正: {len(ALL_PROMPTS)}"

# ─── Checkpoint / Progress ─────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"completed_indices": [], "total_images": 0,
            "total_cost_usd": 0.0, "started_at": datetime.now().isoformat()}

def save_checkpoint(cp: dict):
    CHECKPOINT.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")

# ─── Database ──────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS image_labels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filepath TEXT UNIQUE,
        filename TEXT, subfolder TEXT, category TEXT,
        processed_at TEXT, input_tokens INTEGER, output_tokens INTEGER,
        cost_usd REAL, labels_json TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS processing_meta (
        key TEXT PRIMARY KEY, value TEXT)""")
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

# ─── Image generation with retry ──────────────────────────────────────────
def generate_images(prompt_text: str, out_dir: Path, prefix: str,
                    max_retries: int = 5) -> list[Path]:
    """Imagen 3 Fast で4枚生成。失敗時は指数バックオフでリトライ。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    delay = 30  # 初回リトライ待機秒数

    for attempt in range(max_retries):
        try:
            resp = imagen_client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=prompt_text,
                config=types.GenerateImagesConfig(
                    number_of_images=CANDIDATE_COUNT,
                    aspect_ratio="1:1",
                    output_mime_type="image/png",
                    safety_filter_level="BLOCK_ONLY_HIGH",
                    person_generation="ALLOW_ADULT",
                ),
            )
            saved = []
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            for k, img in enumerate(resp.generated_images):
                fname = out_dir / f"{prefix}_{ts}_{k+1:02d}.png"
                fname.write_bytes(img.image.image_bytes)
                saved.append(fname)
            return saved

        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1:
                if "429" in err_str or "quota" in err_str.lower():
                    wait = delay * (2 ** attempt)
                    print(f"    ⚠️  レート制限 (429). {wait}秒後にリトライ ({attempt+1}/{max_retries})...")
                    time.sleep(wait)
                elif "block" in err_str.lower() or "safety" in err_str.lower():
                    print(f"    ⛔ セーフティブロック. スキップ.")
                    return []
                else:
                    print(f"    ❌ エラー: {e}. 30秒後リトライ ({attempt+1}/{max_retries})...")
                    time.sleep(30)
            else:
                print(f"    ❌ {max_retries}回失敗. スキップ: {e}")
                return []
    return []

# ─── Poetry labeling with Gemini ──────────────────────────────────────────
COUNTRIES_BRIEF = "\n".join(
    f'  {c["lang_code"]}: {c["language"]} ({c["native_name"]})' for c in COUNTRIES
)

def label_image_with_poetry(image_path: Path, category: str,
                             source_prompt: str) -> tuple[dict, int, int]:
    """
    Gemini Vision で画像を見て30カ国語の詩タイトル + 詩 + タグを生成。
    Returns (labels_dict, input_tokens, output_tokens)
    """
    img_bytes = image_path.read_bytes()
    img_b64   = base64.b64encode(img_bytes).decode()

    prompt = f"""You are a world-class multilingual poet and creative director specializing in cosmic and sci-fi imagery.

Analyze this image (category: {category}, prompt origin: {source_prompt[:120]}...).

For each of the 30 language codes listed below, create:
1. "title": A poetic, evocative title (5–10 words) in that language
2. "poem": A short poem (2–4 lines) inspired by this image, in that language
3. "tags": Exactly 12 thematic keywords/tags in that language (no hashtags)

Return ONLY a valid JSON object with this exact structure:
{{
  "en-US": {{"title": "...", "poem": "...", "tags": ["tag1", ...]}},
  "ja-JP": {{"title": "...", "poem": "...", "tags": ["tag1", ...]}},
  ...
}}

Language codes to include:
{COUNTRIES_BRIEF}

Rules:
- Write each title/poem naturally in the target language (not translated word-for-word)
- Tags should be evocative single words or short phrases relevant to the image
- If a language uses non-Latin script, use that script
- Return ONLY the JSON object, no markdown, no explanation"""

    for attempt in range(4):
        try:
            resp = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    prompt,
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
            labels = json.loads(m.group())
            in_tok  = resp.usage_metadata.prompt_token_count     if resp.usage_metadata else 500
            out_tok = resp.usage_metadata.candidates_token_count if resp.usage_metadata else 2000
            return labels, in_tok, out_tok

        except Exception as e:
            if attempt < 3:
                wait = 10 * (2 ** attempt)
                print(f"      ⚠️  詩生成エラー: {e}. {wait}秒後リトライ...")
                time.sleep(wait)
            else:
                print(f"      ❌ 詩生成失敗（スキップ）: {e}")
                # フォールバック: 英語タイトルのみ
                fb = {}
                for c in COUNTRIES:
                    fb[c["lang_code"]] = {
                        "title": f"Cosmic {category.replace('-', ' ').title()}",
                        "poem":  f"A vision from the cosmos.",
                        "tags":  ["cosmic", "space", "digital art", "sci-fi",
                                  "futuristic", "beauty", "alien", "universe",
                                  "stellar", "otherworldly", "visionary", "ethereal"],
                    }
                return fb, 500, 200

# ─── JSON export ───────────────────────────────────────────────────────────
def export_json(conn):
    """DB全件を labeled_images.json に書き出す"""
    print("  📤 labeled_images.json 更新中...")
    rows = conn.execute(
        "SELECT filepath, filename, subfolder, category, processed_at, labels_json FROM image_labels"
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
    print(f"  ✅ {len(out)} 件エクスポート完了")

# ─── Cost display ──────────────────────────────────────────────────────────
def fmt_cost(usd: float) -> str:
    return f"${usd:.3f} (¥{usd * USD_TO_JPY:,.0f})"

# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true",
                        help="テストモード: 3プロンプト(12枚)のみ生成して確認を求める")
    args = parser.parse_args()

    cp   = load_checkpoint()
    conn = init_db()
    done = set(cp["completed_indices"])

    # テストモード: 最初の3プロンプトのみ
    prompts_to_run = ALL_PROMPTS[:3] if args.test else ALL_PROMPTS
    indices_to_run = [i for i in range(len(prompts_to_run)) if i not in done]

    total_remaining = len(indices_to_run)
    total_imgs_est  = total_remaining * CANDIDATE_COUNT
    cost_est_usd    = total_imgs_est * IMAGEN_PRICE

    print("=" * 60)
    print("🚀 宇宙テーマ画像生成スクリプト")
    print("=" * 60)
    print(f"  モード     : {'🧪 テスト (12枚)' if args.test else '🌌 本番 (3,000枚)'}")
    print(f"  残りプロンプト: {total_remaining} / {len(prompts_to_run)}")
    print(f"  生成予定枚数: {total_imgs_est} 枚")
    print(f"  推定コスト  : {fmt_cost(cost_est_usd)}")
    print(f"  予算上限    : {fmt_cost(BUDGET_USD)}")
    print(f"  累積コスト  : {fmt_cost(cp['total_cost_usd'])}")
    print("=" * 60)

    if not indices_to_run:
        print("✅ 全プロンプト処理済み！")
        export_json(conn)
        return

    total_images_gen  = cp["total_images"]
    total_cost_usd    = cp["total_cost_usd"]
    session_images    = 0
    session_cost      = 0.0

    for loop_i, prompt_idx in enumerate(indices_to_run):
        prompt_text, category = ALL_PROMPTS[prompt_idx]

        # 予算チェック
        if total_cost_usd >= BUDGET_USD:
            print(f"\n💰 予算上限 {fmt_cost(BUDGET_USD)} に達しました。停止します。")
            break

        # フォルダ設定
        subdir_name = category
        out_dir     = IMAGES_DIR / subdir_name
        prefix      = f"cosmic_{prompt_idx:04d}"

        print(f"\n[{loop_i+1}/{total_remaining}] {category} | idx={prompt_idx}")
        print(f"  プロンプト: {prompt_text[:80]}...")

        # ── 1. 画像生成 ──────────────────────────────────────────────
        gen_start = time.time()
        saved     = generate_images(prompt_text, out_dir, prefix)
        gen_sec   = time.time() - gen_start

        if not saved:
            print(f"  ⛔ 画像生成0枚 → スキップ")
            # チェックポイントには記録しない（次回リトライ）
            time.sleep(5)
            continue

        img_cost  = len(saved) * IMAGEN_PRICE
        total_cost_usd  += img_cost
        session_cost    += img_cost
        total_images_gen += len(saved)
        session_images  += len(saved)
        print(f"  ✅ {len(saved)}枚生成 ({gen_sec:.1f}秒) | コスト: {fmt_cost(img_cost)}")

        # ── 2. 詩ラベリング（各画像） ──────────────────────────────
        for img_path in saved:
            print(f"    🎨 詩生成中: {img_path.name}")
            labels, in_tok, out_tok = label_image_with_poetry(
                img_path, category, prompt_text)

            gem_cost = (in_tok * GEM_IN_PER_M + out_tok * GEM_OUT_PER_M) / 1_000_000
            total_cost_usd += gem_cost
            session_cost   += gem_cost

            # DB保存
            rel_path = img_path.relative_to(BASE_DIR).as_posix()
            save_label(conn, rel_path, img_path.name, f"cosmic/{subdir_name}",
                       category, in_tok, out_tok, IMAGEN_PRICE + gem_cost, labels)

            time.sleep(1.5)  # Gemini レート制限対策

        # ── 3. チェックポイント更新 ────────────────────────────────
        cp["completed_indices"].append(prompt_idx)
        cp["total_images"]   = total_images_gen
        cp["total_cost_usd"] = total_cost_usd
        save_checkpoint(cp)

        # ── 4. 進捗表示 ───────────────────────────────────────────
        pct = (loop_i + 1) / total_remaining * 100
        print(f"  📊 進捗: {pct:.1f}% | 今回: {session_images}枚 ¥{session_cost*USD_TO_JPY:,.0f}"
              f" | 累計: {total_images_gen}枚 {fmt_cost(total_cost_usd)}")

        # ── 5. レート制限対策スリープ ──────────────────────────────
        if (loop_i + 1) % 10 == 0:
            print(f"  💤 10リクエスト完了 → 30秒休憩（API制限対策）")
            time.sleep(30)
        else:
            time.sleep(8)   # 通常インターバル

    # ── 最終エクスポート ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📤 labeled_images.json を更新中...")
    export_json(conn)
    conn.close()

    print("\n🎉 完了！")
    print(f"  生成枚数 : {total_images_gen} 枚")
    print(f"  総コスト : {fmt_cost(total_cost_usd)}")
    print(f"  出力先   : {IMAGES_DIR}")

    if args.test:
        print("\n" + "=" * 60)
        print("🧪 テスト完了！")
        print(f"   生成画像: {IMAGES_DIR}")
        print("   ブラウザで確認: http://localhost:3000/gallery.html")
        print("\n   問題なければ本番実行: python generate_cosmic.py")
        print("=" * 60)

if __name__ == "__main__":
    main()
