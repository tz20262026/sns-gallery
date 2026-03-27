"""
ハリウッド映画級 資産生成スクリプト
Imagen 4.0 (Fast/Standard) + Veo 2.0 使用
実行: python generate_assets.py
"""

import os
import sys
import time
import json
import base64
import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# ============================================================
# ★ 設定（実行前にここを編集してください）
# ============================================================
PROJECT_ID = "spreadsheet-bot-489912"  # Google CloudプロジェクトID
LOCATION   = "us-central1"

BASE_DIR   = Path(r"C:\Users\81808\Desktop\SNS_Project")
IMAGES_DIR = BASE_DIR / "images"
VIDEOS_DIR = BASE_DIR / "videos"

# 生成枚数設定
FAST_REQUESTS     = 70   # Fast枠: 70リクエスト × 4枚 = 280枚
STANDARD_REQUESTS = 70   # Standard枠: 70リクエスト × 4枚 = 280枚
VIDEO_COUNT       = 5    # 動画: 5本
CANDIDATE_COUNT   = 4    # 1リクエストあたりの生成枚数

# ============================================================
# プロンプト定義
# ============================================================

CHILDREN_PROMPTS = [
    # 惑星・宇宙シーン
    "A brave young astronaut child exploring a vibrant alien planet with colorful crystal formations, Pixar 3D animation style, ultra-detailed, cinematic lighting, 8K resolution, anamorphic lens bokeh, HDR, volumetric light rays",
    "Joyful kids riding giant friendly space whales through a neon nebula, Pixar-quality 3D animation, 8K, cinematic composition, rim lighting, vibrant colors",
    "A cheerful robot companion and child discover a hidden waterfall on a purple alien moon, Pixar style, photorealistic 3D, 8K, golden hour cinematic lighting",
    "Young space explorers in colorful suits planting flags on a rainbow-colored asteroid, Pixar animation, 8K, anamorphic widescreen, dramatic sky",
    "A magical space garden on a floating island planet, glowing flowers, butterfly-like aliens, child protagonist, Pixar 3D, 8K, cinematic HDR",
    # アクション・冒険
    "Epic zero-gravity chase scene through a sparkling asteroid field, children heroes, Pixar 3D animation, 8K, motion blur, cinematic action shot",
    "Kids piloting a crystal spaceship through a storm of shooting stars, Pixar style, 8K ultra-detailed, dynamic lighting, widescreen cinematic",
    "A child wizard casting spells to power a starship engine room, magical realism, Pixar 3D, 8K, dramatic rim lighting, vivid colors",
    "Young adventurers discovering an ancient alien temple covered in glowing runes, Pixar animation, 8K, golden cinematic light, volumetric fog",
    "Space battle scene with friendly ships made of candy and crystal, children heroes, Pixar style, 8K, explosive colorful effects",
    # 生き物・キャラクター
    "A cute alien dragon hatching from a cosmic egg, child protagonist watching in awe, Pixar 3D, 8K, warm cinematic lighting",
    "Friendly giant octopus alien playing with kids in an underwater alien ocean, Pixar style, 8K, bioluminescent lighting, cinematic",
    "A team of diverse children riding colorful rocket bikes on Mars, Pixar 3D animation, 8K, sunset cinematic lighting, dust particles",
    "A tiny robot learning to fly with alien birds on a gas giant, Pixar style, 8K, pastel sky, cinematic depth of field",
    "Kids teaching an alien puppy to play fetch in low gravity, Pixar 3D, 8K, playful lighting, warm tones",
    # 感動・ドラマ
    "Child astronaut looking at Earth from the moon for the first time, tears of joy, Pixar 3D, 8K, dramatic earthrise lighting, cinematic",
    "A young girl sharing her lunch with a shy alien, heartwarming moment, Pixar animation, 8K, soft golden light",
    "Children of different planets becoming friends around a cosmic campfire, Pixar 3D, 8K, warm fire light, star-filled sky",
    "A lost baby alien found and comforted by a child, Pixar style, 8K, warm cinematic lighting, emotional close-up",
    "Kids building a bridge between two asteroids to unite alien villages, Pixar 3D, 8K, heroic cinematic lighting",
    # 景色・環境
    "Breathtaking sunrise over a planet with three moons, Pixar 3D landscape, 8K, cinematic HDR, anamorphic lens flare",
    "A bustling alien marketplace on a ring-shaped space station, Pixar style, 8K, vibrant colors, cinematic wide shot",
    "Crystal caves glowing with alien minerals on a distant planet, Pixar 3D, 8K, bioluminescent atmosphere, cinematic",
    "A rainbow highway through a nebula viewed from a spaceship cockpit, Pixar animation, 8K, cinematic framing",
    "Underwater alien city with bubble domes and glowing coral, Pixar 3D, 8K, cinematic blue lighting",
    # 季節・自然
    "Alien autumn forest with silver and gold leaves floating in zero gravity, child running through, Pixar 3D, 8K, warm cinematic light",
    "Snow storm on an ice planet with glowing blue snowflakes, kids playing, Pixar style, 8K, cinematic cold light",
    "Alien spring blooming with giant flowers taller than buildings, child exploring, Pixar 3D, 8K, soft morning light",
    "A meteor shower over an alien village at night, children watching in wonder, Pixar animation, 8K, dramatic night lighting",
    "Tidal waves of stardust on a cosmic beach, kids surfing, Pixar 3D, 8K, golden cinematic lighting",
    # テクノロジー・未来
    "A child inventor building a robot in a zero-gravity workshop, Pixar 3D, 8K, warm workshop lighting, cinematic",
    "Kids hacking a friendly supercomputer to save their planet, Pixar style, 8K, neon cyberpunk lighting",
    "A school for young space pilots with holographic teachers, Pixar animation, 8K, futuristic cinematic lighting",
    "Young engineers fixing a broken star engine together, Pixar 3D, 8K, dramatic technical lighting, teamwork",
    "Kids racing homemade spaceships around Saturn's rings, Pixar style, 8K, cinematic speed blur, vibrant colors",
    # 文化・多様性
    "Intergalactic festival with children from 100 planets celebrating together, Pixar 3D, 8K, festive colorful lighting",
    "Space Olympics with kids competing in zero-gravity sports, Pixar animation, 8K, stadium cinematic lighting",
    "Children sharing traditional foods from different planets, Pixar 3D, 8K, warm communal lighting, diverse characters",
    "A galactic library where books fly and teach by themselves, Pixar style, 8K, magical warm lighting",
    "Kids performing a musical concert that powers the spaceship, Pixar 3D, 8K, concert stage lighting, vibrant",
    # ミステリー・発見
    "Child detective solving a mystery on a cloud planet, Pixar 3D, 8K, noir cinematic lighting with color pops",
    "First contact: a child meeting a shy underwater alien, Pixar style, 8K, bioluminescent dramatic lighting",
    "Kids finding a treasure map drawn by ancient alien civilization, Pixar 3D, 8K, adventure cinematic lighting",
    "A time capsule from the future discovered by children, Pixar animation, 8K, magical glow, cinematic",
    "Young archaeologists uncovering a giant alien fossil, Pixar 3D, 8K, warm excavation lighting, detailed",
    # 家族・絆
    "A family reunion in a space station between Earth and Mars, Pixar 3D, 8K, warm emotional lighting",
    "Grandparent alien telling stories to earth children around a holographic fire, Pixar style, 8K, cozy warm light",
    "Kids building a home on a new planet as a family adventure, Pixar 3D, 8K, hopeful golden hour lighting",
    "A parent and child watching twin sunsets on an alien world, Pixar animation, 8K, breathtaking cinematic light",
    "Children adopting a baby star as their cosmic pet, Pixar 3D, 8K, glowing warm cinematic scene",
    # ヒーロー・勇気
    "A shy child becoming a hero by saving an alien village from a comet, Pixar 3D, 8K, heroic cinematic lighting",
    "Kids forming a superhero squad to protect their galaxy, Pixar style, 8K, dynamic action lighting",
    "A small child standing up to a giant space bully, Pixar 3D, 8K, dramatic confrontation lighting",
    "Young heroes returning home victorious after saving the universe, Pixar animation, 8K, triumphant golden light",
    "A child with a disability becoming the best pilot in the galaxy, Pixar 3D, 8K, inspirational cinematic lighting",
    # 夢・ファンタジー
    "A child's dream coming to life as a living galaxy, Pixar 3D, 8K, surreal dreamlike cinematic lighting",
    "Kids entering a storybook that becomes a real alien world, Pixar style, 8K, magical transition lighting",
    "A wish upon a shooting star transforms a child's backyard into space, Pixar 3D, 8K, magical golden light",
    "Children flying through their imagination as it becomes real space, Pixar animation, 8K, vibrant dream lighting",
    "A cosmic fairy granting a child the ability to speak all alien languages, Pixar 3D, 8K, magical sparkle lighting",
    # ペット・動物
    "A space dog fetching stars and bringing them back to its child owner, Pixar 3D, 8K, playful warm lighting",
    "Kids training alien horses to jump between asteroids, Pixar style, 8K, cinematic action lighting",
    "A luminous space cat leading children through a dark nebula, Pixar 3D, 8K, mysterious glowing light",
    "Children raising a baby space whale that outgrows their spaceship, Pixar animation, 8K, heartwarming light",
    "An alien parrot that can navigate by starlight guiding lost kids home, Pixar 3D, 8K, warm homing light",
    # 科学・学習
    "Kids performing experiments in a zero-gravity science lab, colorful results, Pixar 3D, 8K, bright lab lighting",
    "Young astronomers discovering a new constellation and naming it, Pixar style, 8K, observatory cinematic light",
    "Children learning to grow food on Mars with alien farmers, Pixar 3D, 8K, warm agricultural lighting",
    "A kid teaching robots to feel emotions, Pixar animation, 8K, warm workshop lighting, touching scene",
    "Young scientists curing an alien illness using Earth flowers, Pixar 3D, 8K, hopeful medical lighting",
    # 最終章
    "Grand finale: all planets celebrating peace together, children as ambassadors, Pixar 3D, 8K, epic cinematic lighting",
    "The young heroes waving goodbye as they journey to a new galaxy, Pixar style, 8K, bittersweet golden light",
]

SHOWA_PROMPTS = [
    # 夕暮れ・黄昏
    "Tokyo 1960s at golden hour dusk, Shimbashi station street scene, salary men in suits, neon signs flickering on, cinematic 35mm film grain, anamorphic lens, Academy Award cinematography, 8K HDR, volumetric fog, nostalgia",
    "Rainy evening in 1965 Ginza, reflections of neon on wet cobblestones, woman in kimono under paper umbrella, cinematic film photography, 8K, dramatic Rembrandt lighting, shallow depth of field",
    "Sunset over Tokyo Bay 1964 Olympics era, workers watching the skyline change, photorealistic cinematic, 8K, golden hour HDR, anamorphic lens flare",
    "1960s Shinjuku alley at twilight, yakitori smoke rising, salarymen drinking, cinematic composition, 8K, warm amber light, film grain, nostalgic atmosphere",
    "Tokyo Tower under construction at dusk 1958, workers silhouetted against orange sky, cinematic 8K, dramatic backlighting, historical drama quality",
    # 雨・情景
    "Rainy night in 1962 Asakusa, paper lanterns reflected in puddles, elderly couple sharing umbrella, Oscar-winning cinematography style, 8K, deep shadow dramatic lighting",
    "1968 Tokyo rainstorm, children running home from school, steam rising from manholes, cinematic 8K, cool blue dramatic lighting, film grain",
    "A traditional sento bathhouse in 1963 rain, warm yellow light spilling onto wet street, neighborhood life, cinematic 8K, intimate dramatic lighting",
    "1965 Yanaka neighborhood after rain, narrow alley, tile roofs glistening, old man walking cat, cinematic 8K, melancholic soft light",
    "Rain on a 1960s bullet train window, countryside passing, lonely businessman, cinematic 8K, reflective moody lighting, Ozu style",
    # 家族・日常
    "A 1961 Tokyo family gathered around a new black-and-white television, wonder on their faces, cinematic 8K, warm domestic lamplight, period authentic",
    "Mother cooking in a 1963 Japanese kitchen, wooden house, morning light through shoji screen, cinematic 8K, soft warm beam lighting",
    "Children playing in a 1960s Tokyo shotgun house neighborhood, futon airing on balconies, cinematic 8K, afternoon golden light",
    "A 1964 family picnic under cherry blossoms with Fuji in background, bento boxes, cinematic 8K, spring soft light, Technicolor inspired",
    "Grandmother and grandchild making mochi in a 1962 kitchen, steam rising, cinematic 8K, warm morning light, intimacy",
    # 市場・商店街
    "Tsukiji fish market at dawn 1965, lantern light before sunrise, workers hauling tuna, cinematic 8K, dramatic low-key lighting, authentic period",
    "A 1963 shotengai shopping street in full evening activity, paper signs, wooden shops, cinematic 8K, warm commerce lighting",
    "Street vendor selling sweet potatoes in 1960 winter Tokyo, breath mist, coat-clad customers, cinematic 8K, cold night warm vendor light",
    "A 1966 sake brewery in rural Japan, cedar ball hanging, autumn light filtering through wooden lattice, cinematic 8K, golden amber tones",
    "Afternoon at a 1964 kissaten coffee shop, jazz playing, intellectuals debating, cinematic 8K, smoky atmospheric lighting",
    # 交通・移動
    "Tokyo streetcar final days 1967, passengers packed inside, city reflected in windows, cinematic 8K, melancholic farewell lighting",
    "Steam locomotive at a 1961 rural station, tearful farewells, platform steam, cinematic 8K, dramatic nostalgic lighting",
    "The first Shinkansen bullet train 1964, crowds watching, pride and wonder, cinematic 8K, heroic lighting, historical epic",
    "A bicycle delivery boy weaving through 1963 Tokyo traffic, newspaper bundle, cinematic 8K, dynamic motion lighting",
    "Ferryboat crossing Tokyo Bay at dusk 1962, workers heading home, silhouettes, cinematic 8K, spectacular sunset lighting",
    # 祭り・文化
    "Bon Odori festival in a 1963 Tokyo neighborhood, paper lanterns, yukata, dancing, cinematic 8K, warm festival lighting, cultural richness",
    "Sumo tournament day 1965, Kokugikan arena, packed crowd, cinematic 8K, dramatic arena lighting, ceremony",
    "A 1964 Tokyo Olympics opening ceremony moment, Japanese athletes marching, pride, cinematic 8K, stadium epic lighting",
    "New Year shrine visit 1963, kimono crowds, incense smoke, bell ringing, cinematic 8K, sacred atmospheric lighting",
    "Hanami cherry blossom party 1966, salarymen drinking sake, petals falling, cinematic 8K, dream-like pink light",
    # 職人・仕事
    "Master swordsmith at work in a 1960s forge, sparks flying, thousand-year craft, cinematic 8K, forge dramatic lighting, NHK documentary quality",
    "A 1963 Nishijin textile weaver, complex loom, silk threads, afternoon light, cinematic 8K, artisan warm lighting",
    "Kabuki actor applying makeup backstage 1965, mirror reflection, ceremony, cinematic 8K, theatrical dramatic lighting",
    "A 1962 Tsukiji tuna auctioneer mid-call, frozen breath, dramatic pose, cinematic 8K, predawn blue lighting",
    "Traditional tatami maker in 1964, geometric patterns, afternoon workshop light, cinematic 8K, artisan golden tones",
    # 自然・四季
    "Mount Fuji at dawn from a 1963 Tokaido train window, perfect reflection in rice paddy, cinematic 8K, spiritual morning light",
    "Autumn momiji leaves falling on a 1965 Kyoto temple pond, elderly monk raking, cinematic 8K, contemplative amber light",
    "Winter snow on a 1962 Tohoku mountain village, wood smoke rising, isolation, cinematic 8K, cold blue with warm hearth light",
    "Spring flooding of rice paddies 1964, rural Japan, planting season, cinematic 8K, overcast dramatic light, mud and hope",
    "Summer cicada song in a 1963 Tokyo park, old men playing shogi under trees, cinematic 8K, dappled sunlight, peace",
    # ドラマ・感情
    "Young man seeing off his parents at 1963 Tokyo Station, first time living alone, cinematic 8K, emotional parting lighting",
    "A letter from overseas being read by candlelight in 1961, tears forming, cinematic 8K, intimate warm single light source",
    "Two childhood friends reuniting at 1965 Ueno Park, time having changed both, cinematic 8K, bittersweet afternoon light",
    "An elderly couple watching their old neighborhood being demolished for 1964 Olympics, cinematic 8K, melancholic twilight",
    "A widow maintaining her husband's 1962 barbershop alone, dignity and grief, cinematic 8K, morning ritual lighting",
    # 子ども・学校
    "Children walking to school in 1963 Tokyo, randoseru backpacks, narrow lanes, cinematic 8K, morning golden light",
    "A 1965 school graduation ceremony in gymnasium, pride and tears, cinematic 8K, institutional warm lighting",
    "Boys playing baseball in a 1962 vacant lot, makeshift equipment, pure joy, cinematic 8K, afternoon long shadow light",
    "A young girl practicing piano in 1964, shoji window, cherry blossoms outside, cinematic 8K, delicate spring light",
    "Children catching fireflies in a 1963 summer evening field, jars glowing, cinematic 8K, magical dusk lighting",
    # 飲食・グルメ
    "Ramen shop at midnight 1967, steam rising, lone businessman eating, red lantern, cinematic 8K, dramatic warm-cold contrast",
    "Morning tofu delivery by bicycle 1963, wooden bucket, neighborhood awakening, cinematic 8K, misty dawn light",
    "A 1965 sukiyaki dinner party, family gathered, cast iron pot bubbling, cinematic 8K, warm intimate gathering light",
    "Street yakitori grill in 1964 summer evening, smoke and laughter, cinematic 8K, charcoal red glow on faces",
    "A coffee shop owner brewing pour-over in 1966 Koenji, jazz record cover on wall, cinematic 8K, intimate amber lighting",
    # 近代化・変化
    "New highway construction through old Tokyo neighborhood 1963, displacement and progress, cinematic 8K, documentary dramatic lighting",
    "The first McDonald's opening in Japan 1970, queues stretching, cultural shift, cinematic 8K, neon modern lighting contrasting old",
    "A 1965 electronics store window displaying the first color TVs, crowds amazed, cinematic 8K, futuristic screen glow",
    "Demolition of old Marunouchi buildings for new skyscrapers 1968, foreman watching, cinematic 8K, dust and light",
    "Last day of a neighborhood onsen bathhouse before closing 1969, regulars gathered, cinematic 8K, steam and memory lighting",
    # 記憶・回想
    "An elderly man in 2024 holding a 1960s photograph of his youth, split-screen memory, cinematic 8K, dual era lighting",
    "A deserted 1965 schoolyard at sunset, swings moving in wind, memory and absence, cinematic 8K, golden melancholic light",
    "Old neighborhood map versus modern satellite image, 1963 Tokyo overlaid, cinematic 8K, documentary blend lighting",
    "Faded family portraits from 1961 on a modern wall, connection across time, cinematic 8K, archival warm light",
    "The last wooden house in a modern city block, 1963 survivor, cinematic 8K, dramatic isolation lighting",
    # 友情・コミュニティ
    "Neighborhood fire brigade volunteers in 1964 winter, breath visible, unity, cinematic 8K, cold night warm community light",
    "A 1963 neighborhood association meeting, elderly residents, civic pride, cinematic 8K, meeting hall warm light",
    "Old friends from the war years reuniting in 1965, silent understanding, cinematic 8K, moving afternoon light",
    "A 1964 school teacher staying late to help a struggling student, dedication, cinematic 8K, evening classroom light",
    "Neighbors helping rebuild a 1962 house after fire, solidarity, cinematic 8K, community warm light, documentary quality",
    # 最終章・遺産
    "The last steam locomotive journey in 1972, crowd farewell at station, cinematic 8K, end of era lighting",
    "Elderly craftsman passing his tools to grandson in 1968, legacy, cinematic 8K, emotional workshop lighting",
    "Dawn of the new age: Tokyo 1964 Olympics stadium, hope and modernity, cinematic 8K, epic historical lighting",
]


# ============================================================
# メイン処理
# ============================================================

def setup_directories():
    for d in [IMAGES_DIR / "children", IMAGES_DIR / "showa", VIDEOS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print("✓ フォルダ準備完了")


def generate_images_fast(client, types_module):
    """Imagen 4.0 Fast で 70リクエスト（こども35 + 昭和35）"""
    print("\n[FAST] 画像生成開始 ...")
    count = 0

    for theme, prompts, subdir in [
        ("children", CHILDREN_PROMPTS[:35], IMAGES_DIR / "children"),
        ("showa",    SHOWA_PROMPTS[:35],    IMAGES_DIR / "showa"),
    ]:
        for i, prompt in enumerate(prompts):
            try:
                response = client.models.generate_images(
                    model="imagen-4.0-fast-generate-001",
                    prompt=prompt,
                    config=types_module.GenerateImagesConfig(
                        number_of_images=CANDIDATE_COUNT,
                        aspect_ratio="16:9",
                        output_mime_type="image/png",
                    ),
                )
                for j, img in enumerate(response.generated_images):
                    ts = datetime.datetime.now().strftime("%H%M%S")
                    fname = subdir / f"fast_{theme}_{i+1:02d}_{j+1}_{ts}.png"
                    fname.write_bytes(img.image.image_bytes)
                    count += 1

                print(f"  [FAST] {theme} {i+1:02d}/35 → {len(response.generated_images)}枚保存 (累計{count}枚)")
                time.sleep(10)  # レート制限対策

            except Exception as e:
                print(f"  [FAST] {theme} {i+1} エラー: {e}")
                time.sleep(2)

    print(f"[FAST] 完了: {count}枚")
    return count


def generate_images_standard(client, types_module):
    """Imagen 4.0 Standard で 70リクエスト（こども35 + 昭和35）"""
    print("\n[STANDARD] 画像生成開始 ...")
    count = 0

    for theme, prompts, subdir in [
        ("children", CHILDREN_PROMPTS[35:], IMAGES_DIR / "children"),
        ("showa",    SHOWA_PROMPTS[35:],    IMAGES_DIR / "showa"),
    ]:
        for i, prompt in enumerate(prompts):
            try:
                response = client.models.generate_images(
                    model="imagen-4.0-generate-001",
                    prompt=prompt,
                    config=types_module.GenerateImagesConfig(
                        number_of_images=CANDIDATE_COUNT,
                        aspect_ratio="16:9",
                        output_mime_type="image/png",
                    ),
                )
                for j, img in enumerate(response.generated_images):
                    ts = datetime.datetime.now().strftime("%H%M%S")
                    fname = subdir / f"std_{theme}_{i+1:02d}_{j+1}_{ts}.png"
                    fname.write_bytes(img.image.image_bytes)
                    count += 1

                print(f"  [STD] {theme} {i+1:02d}/35 → {len(response.generated_images)}枚保存 (累計{count}枚)")
                time.sleep(10)  # Standardは少し待機

            except Exception as e:
                print(f"  [STD] {theme} {i+1} エラー: {e}")
                time.sleep(3)

    print(f"[STANDARD] 完了: {count}枚")
    return count


def generate_videos(client, types_module):
    """Veo 2.0 で上位5枚を動画化"""
    print("\n[VIDEO] 動画生成開始 ...")

    # 最もドラマチックなプロンプト5本を厳選
    video_prompts = [
        # こども向け: 最高潮シーン
        "Epic cinematic shot: brave child astronaut standing on alien cliff overlooking a gas giant, three moons rising, Pixar quality 3D animation, 8K, anamorphic lens, volumetric god rays, sweeping orchestral moment, camera slowly pulling back to reveal the scale",
        # 昭和向け: 最高潮シーン
        "Cinematic slow motion: Tokyo 1964 at sunset, bullet train passing historic wooden neighborhood, steam and modernity colliding, elderly woman watching from window, tears in eyes, Academy Award cinematography, 8K, anamorphic lens flare, Morricone-esque atmosphere",
        # こども向け: アクション
        "Dynamic Pixar-quality action sequence: children riding cosmic dolphins through a supernova explosion, colorful shockwave, zero gravity hair, 8K cinematic, soaring musical moment, camera spiraling outward",
        # 昭和向け: 情緒
        "Ultra-cinematic rain scene: 1963 Tokyo alley, paper lanterns swaying, couple parting under umbrella, reflections in puddles, slow zoom out to reveal the entire glowing neighborhood, 8K, film grain, nostalgic orchestral swell",
        # 合作: 壮大なフィナーレ
        "Breathtaking dual-era montage: 1964 Tokyo construction and 2064 space colony both glowing with human achievement, generations connected, 8K HDR, IMAX cinematography, epic Hans Zimmer-style climax",
    ]

    completed = []
    for i, prompt in enumerate(video_prompts):
        try:
            print(f"  [VIDEO] 動画 {i+1}/5 生成中... (数分かかります)")
            operation = client.models.generate_videos(
                model="veo-2.0-generate-001",
                prompt=prompt,
                config=types_module.GenerateVideosConfig(
                    aspect_ratio="16:9",
                    duration_seconds=5,
                    output_gcs_uri=None,  # ローカル保存
                ),
            )

            # ポーリングで完了待ち（最大10分）
            for attempt in range(60):
                time.sleep(10)
                operation = client.operations.get(operation)
                if operation.done:
                    break
                print(f"    待機中... ({attempt+1}/60)")

            if operation.done and operation.response:
                for j, video in enumerate(operation.response.generated_videos):
                    fname = VIDEOS_DIR / f"video_{i+1:02d}_{j+1}.mp4"
                    if hasattr(video.video, 'video_bytes'):
                        fname.write_bytes(video.video.video_bytes)
                    elif hasattr(video.video, 'uri'):
                        # GCS URIの場合はダウンロード
                        fname.write_text(f"GCS_URI: {video.video.uri}")
                    completed.append(str(fname))
                    print(f"  [VIDEO] 動画 {i+1} 保存: {fname.name}")
            else:
                print(f"  [VIDEO] 動画 {i+1} タイムアウトまたはエラー")

        except Exception as e:
            print(f"  [VIDEO] 動画 {i+1} エラー: {e}")

    print(f"[VIDEO] 完了: {len(completed)}本")
    return completed


def main():
    if PROJECT_ID == "YOUR_PROJECT_ID":
        print("=" * 60)
        print("エラー: PROJECT_ID を設定してください！")
        print("スクリプト上部の PROJECT_ID = 'YOUR_PROJECT_ID' を")
        print("実際のGoogle CloudプロジェクトIDに変更してください。")
        print("=" * 60)
        return

    # SDK インポート
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("エラー: google-genai がインストールされていません。")
        print("実行: pip install google-genai")
        return

    print("=" * 60)
    print("ハリウッド映画級 資産生成ミッション 開始")
    print(f"開始時刻: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"プロジェクト: {PROJECT_ID}")
    print("=" * 60)

    setup_directories()

    # クライアント初期化
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    # 画像生成
    fast_count     = generate_images_fast(client, types)
    standard_count = generate_images_standard(client, types)

    # 動画生成
    videos = generate_videos(client, types)

    # サマリー
    print("\n" + "=" * 60)
    print("ミッション完了サマリー")
    print(f"  Fast 画像:     {fast_count} 枚")
    print(f"  Standard 画像: {standard_count} 枚")
    print(f"  合計画像:      {fast_count + standard_count} 枚")
    print(f"  動画:          {len(videos)} 本")
    print(f"  保存先: {BASE_DIR}")
    print(f"終了時刻: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
