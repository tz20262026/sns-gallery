'use strict';

// ============================================================
// Vertex AI Imagen 3 — 大量画像生成スクリプト
// 1日560リクエスト / sampleCount:4 → 計2240枚
// ============================================================

const { PredictionServiceClient } = require('@google-cloud/aiplatform').v1;
const { helpers }                  = require('@google-cloud/aiplatform');
const fsp  = require('fs').promises;
const path = require('path');

// ============================================================
// ★ ここだけ環境に合わせて書き換える
// ============================================================
const CONFIG = {
  projectId      : process.env.GOOGLE_CLOUD_PROJECT  || 'spreadsheet-bot-489912',
  location       : process.env.VERTEX_LOCATION       || 'us-central1',
  model          : 'imagen-3.0-generate-001',

  // 出力ディレクトリ（スクリプトを実行した場所の ./images に保存）
  outputDir      : process.env.OUTPUT_DIR || path.join(process.cwd(), 'images'),

  sampleCount    : 4,          // 1リクエストで生成する枚数
  requestDelayMs : 4000,       // リクエスト間隔 ms（≈15 req/min、安全マージン確保）
  maxRetries     : 5,          // APIエラー時の最大リトライ回数
  retryBaseMs    : 10000,      // リトライ初期待機 ms（429時は動的に延長）
  safetyFilter   : 'block_some',
  personGen      : 'allow_adult',
};

// ============================================================
// プロンプト素材 ─ USA (各スタイル 70件 × 4 = 280件)
// ============================================================
const USA = {
  noir: {
    settings: [
      'rain-soaked city street reflecting neon bar signs at midnight',
      'smoky private detective office with venetian blind shadows',
      'foggy waterfront harbor with anchored fishing boats at 3am',
      'dimly lit jazz club, lone saxophone player on stage',
      'dark narrow alley beside a flickering gas lamp',
      'rooftop overlooking rain-slicked downtown streets at 2am',
      'all-night diner, single customer hunched over black coffee',
      'industrial waterfront loading dock under overcast skies',
      'abandoned warehouse district near elevated train tracks',
      'iron fire escape overlooking a rainy back alley',
    ],
    moods: [
      'chiaroscuro lighting, deep black shadows, single harsh overhead spotlight',
      'venetian blind shadow stripes across wall and floor',
      'single streetlamp casting long dramatic shadows on wet pavement',
      'cigarette smoke caught in a narrow beam of light from high window',
      'wet cobblestones reflecting dim neon signs',
      'dense fog diffusing amber streetlight',
      'high-contrast monochrome tones with single deep-red accent',
    ],
    subjects: [
      'hard-boiled detective in fedora and rain-soaked trench coat',
      'mysterious woman in black dress pausing under streetlamp',
      'corrupt officer in uniform counting banknotes in shadow',
      'silhouette of a figure waiting in a recessed doorway',
      'nervous informant glancing over shoulder under streetlight',
    ],
  },

  scifi: {
    settings: [
      'deep-space observation deck overlooking a gas giant',
      'crumbling abandoned colony habitat on rust-red Martian plateau',
      'bioluminescent alien ocean world at first sunrise',
      'generation ship interior corridor stretching to vanishing point',
      'orbital ring station above cloud-wrapped blue Earth',
      'crashed survey spacecraft half-buried in desert sand dunes',
      'pressurized underwater research station on ocean floor',
      'freshly terraformed moon landscape with thin atmosphere haze',
      'colossal derelict alien megastructure drifting in nebula',
      'zero-gravity laboratory with floating crystal samples',
    ],
    moods: [
      'vast cosmic scale, tiny human silhouette for reference',
      'eerie silence conveyed by empty corridors and long shadows',
      'twin alien suns casting double shadows across dusty terrain',
      'soft blue bioluminescent glow from alien plant life',
      'towering colorful nebula filling the viewport',
      'emergency red lighting flickering in smoke-filled corridor',
      'clean sterile white with hard-edged sci-fi shadows',
    ],
    subjects: [
      'lone astronaut in EVA suit standing on alien cliff edge',
      'humanoid android worker performing maintenance on hull',
      'scientist floating weightless at holographic star-map console',
      'crew in jumpsuits gathered around cryo-sleep pods',
      'xenobiologist collecting samples from alien tide pool',
    ],
  },

  cyberpunk: {
    settings: [
      'rain-soaked neon-lit megacity street packed with street vendors',
      'underground black-market bazaar with stacked crates and smuggled tech',
      'massive corporate skyscraper lobby with floor-to-ceiling screens',
      'rooftop drone delivery hub in perpetual amber smog',
      'back-alley cybernetic clinic with glowing surgical equipment',
      'elevated sky-highway with flying vehicles in light-trail blur',
      'night market crammed under holographic advertisement pillars',
      'flooded lower city district with boat taxis between buildings',
      'gutted server-farm data center repurposed as squat dwelling',
      'neo-Tokyo-style narrow alley with tangled cable overhead',
    ],
    moods: [
      'acid rain reflections painting neon colors on black pavement',
      'overwhelming overlapping neon sign glow in multiple languages',
      'swarm of surveillance drones hovering in smoggy night sky',
      'red surveillance camera LEDs dotting every surface',
      'malfunctioning holographic billboard flickering in rain',
      'dense low-hanging smog lit from below by city glow',
      'deep contrast between blinding ad-light and pitch-black shadows',
    ],
    subjects: [
      'street hacker with glowing neural port implants at nape of neck',
      'corpo security officer in black tactical gear scanning crowd',
      'augmented street vendor in weathered poncho under neon sign',
      'courier on electric motorbike weaving through traffic',
      'augmented reality graffiti artist painting on AR canvas',
    ],
  },

  western: {
    settings: [
      'dusty frontier town main street at high noon',
      'vast ochre canyon landscape at golden hour',
      'lone ranch house silhouetted against dramatic sunset',
      'rugged mountain pass with gathering storm clouds',
      'endless desert stagecoach trail vanishing at horizon',
      'creaking wooden saloon interior with players at card table',
      'cattle drive crossing wide open golden grassland plain',
      'shallow river ford at misty dawn',
      'abandoned silver-mining camp in dry arroyo',
      'telegraph-pole road stretching across alkali flats',
    ],
    moods: [
      'epic ultra-wide angle composition dwarfing human figures',
      'amber dust haze suspended in late-afternoon light shafts',
      'dramatic thunderhead storm approaching over flat mesa',
      'long golden-hour shadows reaching across the trail',
      'heat shimmer rising from sunbaked desert road',
      'deep blue pre-dawn sky over dark silhouetted mountains',
      'warm sepia-toned light recalling early 20th-century photography',
    ],
    subjects: [
      'lone gunslinger at dusty crossroads, hand near holster',
      'weathered sheriff on horseback surveying from ridge',
      'pioneer family on covered wagon crossing the plains',
      'outlaw band silhouetted on a rocky ridge at sunset',
      'Native American scout reading sign on canyon trail',
    ],
  },
};

// ============================================================
// プロンプト素材 ─ JAPAN (各テーマ 70件 × 4 = 280件)
// ============================================================
const JAPAN = {
  danchi: {
    settings: [
      '昭和団地の給水塔と快晴の青空、コンクリートの質感',
      '団地の外廊下と夕焼けのシルエット、洗濯物が揺れる',
      '雨の日の団地駐輪場、自転車と水たまりの反射',
      '団地のベランダに干された布団と梅雨の曇り空',
      '団地の子供用砂場と錆びたブランコ、無人の夕暮れ',
      '集会所へ続く古びたコンクリート階段と苔',
      '団地の廊下に並ぶ植木鉢と古い玄関ドア',
      '昭和の集合住宅エントランス、郵便受けと掲示板',
      '団地の屋上から見下ろす街と遠くの山並み',
      '団地の共用廊下と空になったガスボンベ、電線の影',
    ],
    moods: [
      '柔らかな午後の斜光がコンクリートに影を作る',
      '夕焼けのオレンジが古い外壁を温かく染める',
      '曇天の均一な灰色光、無彩色のリアリズム',
      '梅雨の雨上がり、濡れた路面と緑の鮮やかさ',
      '夏の強烈な日差しと濃い影のコントラスト',
      '冬の朝、薄霜とひんやりとした青白い光',
      '春の桜吹雪が舞い込む廊下の柔らかい光',
    ],
  },

  shoutengai: {
    settings: [
      '雨の昭和商店街アーケード、濡れた石畳と点滅する蛍光灯',
      'シャッターの降りた商店街、夕暮れの橙色の逆光',
      '八百屋の店先に積まれた野菜と手書きの値札',
      '古い金魚屋の外に並んだ大小の金魚鉢、水面の反射',
      '昭和の床屋サインポールが回る路地の角',
      '昔ながらの駄菓子屋の棚にぎっしり並んだ菓子',
      '洋食屋の古いメニュー看板と外壁のつたの葉',
      '古本屋の均一台、雨除けビニール越しの光',
      'せんべい屋の炭火から立ち上る白い煙',
      '路地裏の小さな居酒屋の暖簾と提灯の灯り',
    ],
    moods: [
      '夕方のつり橙色の光が商店街全体を暖かく包む',
      '雨上がりのアーケード、濡れた路面に蛍光灯が映る',
      '昭和レトロな色褪せた看板と色鮮やかな商品のコントラスト',
      '人影まばらな静かな時間帯、足音が響く',
      '昼間の白い直射日光と深いひさしの影',
      '夕暮れから夜への移り変わり、電灯が点灯し始める',
      '活気ある朝の市場、光と影が交差する',
    ],
  },

  shinya: {
    settings: [
      '深夜の古い缶コーヒー自販機、蛍光灯が唯一の光源',
      '深夜のコンビニ駐車場、ガラスに映る照明と誰もいない店内',
      '夜の無人ホームに停車する普通列車と白い蛍光灯',
      '深夜の高速道路サービスエリア、疎らな駐車車両と自販機',
      '終電後の繁華街の路地、散乱するチラシと湯気',
      '深夜の中華料理店の窓明かり、店主が一人で片付け',
      '夜の公園の街灯と水たまりに映るオレンジ色の反射',
      '深夜のラーメン屋台、湯気と照明と孤独な客',
      '夜明け前の魚市場、発泡スチロールと水飛沫と白い光',
      '深夜の工場地帯、オレンジ色の炎と煙突の煙',
    ],
    moods: [
      '深夜の静寂を際立たせる蛍光灯のブーンという音が聞こえそうな白い光',
      '蛍光灯の均一な白色光とその外の真っ暗な闇の境界',
      '雨の夜、光源の反射が何倍にも広がる湿った路面',
      '薄い夜霧が街灯の光を拡散し全体がぼんやりする',
      'オレンジナトリウム灯が醸す昭和的な夜の色調',
      '水蒸気と夜気が混ざり合う白い湯気と逆光',
      '夜明け前の藍色の空と人工光のオレンジのコントラスト',
    ],
  },

  furusato: {
    settings: [
      '実家の古い台所、朝の柔らかい光と煮炊きの湯気',
      '昭和の銭湯の番台と木製ロッカーの脱衣所',
      '木造の古い駅舎のホーム、ツバメの巣と錆びたホーロー看板',
      '祖父母の家の縁側、庭の柿の木と縁側で眠る猫',
      '田舎の踏切と菜の花畑、遠くの山と薄曇り',
      '古い神社の苔むした石段と根上がりの大杉',
      '里山の棚田と朝霧、遠景に茅葺きの農家',
      '廃校になった木造校舎の廊下と割れた窓ガラス',
      '漁港の古い木造漁師小屋と干された網と海の青',
      '昭和の小さな郵便局と赤い電話ボックス',
    ],
    moods: [
      '懐かしい昭和の空気感、色褪せたがどこか温かい色調',
      '朝もやの静けさ、霞の中に浮かぶシルエット',
      '夏の盛りの熱気、蝉の声が聞こえてきそうな照りつける光',
      '秋の澄んだ空気、透明感のある斜光と影の長さ',
      '冬の侘び寂び、モノクロに近い世界に一点の赤',
      '春の温かい光、柔らかいパステルトーンの霞',
      '雨上がりの新鮮な空気感、濃い緑と光る雫',
    ],
  },
};

// ============================================================
// プロンプト文を組み立てる
// ============================================================
const QUALITY_EN = 'stock photo, professional photography, 8K resolution, award-winning composition, sharp focus, natural lighting';
const QUALITY_JA = 'ストックフォト、プロ写真、8K、受賞レベル構図、シャープな描写、自然光';

function buildUSAPrompt(style, setting, mood, subject, variant) {
  const templates = [
    `Cinematic ${style} film photograph: ${setting}. ${subject} in frame. ${mood}. Shot on 35mm film with anamorphic lens. ${QUALITY_EN}.`,
    `${style.toUpperCase()} movie still: ${setting}. ${mood}. Professional Hollywood cinematography, dramatic atmosphere. ${QUALITY_EN}.`,
    `Dramatic ${style} scene: ${subject} — ${setting}. ${mood}. Photorealistic, cinematic color grade. ${QUALITY_EN}.`,
    `${style} aesthetic: ${setting}, bathed in ${mood}. ${subject} barely visible. Deep focus, wide establishing shot. ${QUALITY_EN}.`,
  ];
  return templates[variant % templates.length];
}

function buildJAPANPrompt(theme, setting, mood, variant) {
  const themeLabel = { danchi: '団地', shoutengai: '商店街', shinya: '深夜', furusato: 'ふるさと' }[theme];
  const templates = [
    `日本の${themeLabel}の情景：${setting}。${mood}。ストックフォトグラフィー、プロのライティング、日本の日常美、${QUALITY_JA}。`,
    `Japanese ${themeLabel} scene: ${setting}. ${mood}. Documentary photography style, subtle color palette, nostalgic atmosphere. ${QUALITY_EN}.`,
    `${setting}。${mood}。フィルム写真風の粒子感、日本のストリートフォトグラフィー、${QUALITY_JA}。`,
    `Everyday Japan — ${themeLabel}: ${setting}. ${mood}. Wabi-sabi aesthetic, muted tones, melancholic beauty. ${QUALITY_EN}.`,
  ];
  return templates[variant % templates.length];
}

// ============================================================
// タグ生成（日英）
// ============================================================
function makeUSATags(style, setting, subject) {
  const styleJA = { noir: 'ノワール', scifi: 'SF・宇宙', cyberpunk: 'サイバーパンク', western: 'ウエスタン' };
  return {
    en: [style, 'cinematic', 'dramatic', 'USA', 'hollywood', 'film-still', 'stock-photo',
         ...setting.split(' ').slice(0, 4), ...subject.split(' ').slice(0, 3)],
    ja: [styleJA[style], '映画的', 'ドラマチック', 'アメリカ', 'ストックフォト', '高解像度', '商用利用可'],
  };
}

function makeJAPANTags(theme, setting) {
  const themeEN = { danchi: 'apartment-complex', shoutengai: 'shopping-street', shinya: 'midnight', furusato: 'nostalgic-japan' };
  const themeJA = { danchi: '団地', shoutengai: '商店街', shinya: '深夜', furusato: 'ふるさと' };
  const settingWords = setting.replace(/[、。：]/g, ' ').split(/\s+/).slice(0, 5);
  return {
    en: [themeEN[theme], 'japan', 'everyday-life', 'documentary', 'stock-photo', 'niche-japan',
         'street-photography', ...settingWords],
    ja: [themeJA[theme], '日本', '日常', 'ドキュメンタリー', 'ストックフォト', '日本の原風景',
         '商用利用可', ...settingWords],
  };
}

// ============================================================
// リクエストキューを構築（560件）
// ============================================================
const ASPECT_RATIOS = ['16:9', '9:16', '3:4'];
const SIZE_LABELS   = ['16-9', '9-16', '3-4'];

function buildRequestQueue() {
  const queue = [];

  // --- USA 280件（各スタイル70件 → 各サイズ約23〜24件）---
  const usaStyles = ['noir', 'scifi', 'cyberpunk', 'western'];
  usaStyles.forEach(style => {
    const data = USA[style];
    for (let i = 0; i < 70; i++) {
      const setting = data.settings[i % data.settings.length];
      const mood    = data.moods[i % data.moods.length];
      const subject = data.subjects[i % data.subjects.length];
      const prompt  = buildUSAPrompt(style, setting, mood, subject, i);
      const tags    = makeUSATags(style, setting, subject);
      const arIdx   = i % ASPECT_RATIOS.length;
      queue.push({
        region: 'USA', style, aspectRatio: ASPECT_RATIOS[arIdx],
        sizeLabel: SIZE_LABELS[arIdx], prompt, tags,
      });
    }
  });

  // --- JAPAN 280件（各テーマ70件 → 各サイズ約23〜24件）---
  const japanThemes = ['danchi', 'shoutengai', 'shinya', 'furusato'];
  japanThemes.forEach(theme => {
    const data = JAPAN[theme];
    for (let i = 0; i < 70; i++) {
      const setting = data.settings[i % data.settings.length];
      const mood    = data.moods[i % data.moods.length];
      const prompt  = buildJAPANPrompt(theme, setting, mood, i);
      const tags    = makeJAPANTags(theme, setting);
      const arIdx   = i % ASPECT_RATIOS.length;
      queue.push({
        region: 'JAPAN', style: theme, aspectRatio: ASPECT_RATIOS[arIdx],
        sizeLabel: SIZE_LABELS[arIdx], prompt, tags,
      });
    }
  });

  // Fisher-Yates シャッフル（リージョン/サイズが偏らないよう）
  for (let i = queue.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [queue[i], queue[j]] = [queue[j], queue[i]];
  }

  return queue;
}

// ============================================================
// フォルダ作成
// ============================================================
async function ensureDir(dirPath) {
  await fsp.mkdir(dirPath, { recursive: true });
}

// ============================================================
// Vertex AI — API呼び出し（指数バックオフ付きリトライ）
// ============================================================
function createClient() {
  return new PredictionServiceClient({
    apiEndpoint: `${CONFIG.location}-aiplatform.googleapis.com`,
  });
}

async function callImagenAPI(client, prompt, aspectRatio) {
  const endpoint = [
    `projects/${CONFIG.projectId}`,
    `locations/${CONFIG.location}`,
    `publishers/google`,
    `models/${CONFIG.model}`,
  ].join('/');

  const [response] = await client.predict({
    endpoint,
    instances  : [helpers.toValue({ prompt })],
    parameters : helpers.toValue({
      sampleCount      : CONFIG.sampleCount,
      aspectRatio,
      safetyFilterLevel: CONFIG.safetyFilter,
      personGeneration : CONFIG.personGen,
    }),
  });

  return response.predictions || [];
}

// 429 (Too Many Requests / RESOURCE_EXHAUSTED) かどうかを判定
function isRateLimitError(err) {
  return (
    err.code === 8 ||                              // gRPC RESOURCE_EXHAUSTED
    err.code === 429 ||
    (err.message && (
      err.message.includes('RESOURCE_EXHAUSTED') ||
      err.message.includes('429') ||
      err.message.includes('Quota exceeded') ||
      err.message.includes('Too Many Requests')
    ))
  );
}

async function callWithRetry(client, prompt, aspectRatio, reqIndex) {
  for (let attempt = 1; attempt <= CONFIG.maxRetries; attempt++) {
    try {
      return await callImagenAPI(client, prompt, aspectRatio);
    } catch (err) {
      const isLast     = attempt === CONFIG.maxRetries;
      const isRateLimit = isRateLimitError(err);

      // 429 の場合は待機を長めに取る（通常バックオフの2倍 + 固定30秒）
      const waitMs = isRateLimit
        ? CONFIG.retryBaseMs * Math.pow(2, attempt - 1) + 30000
        : CONFIG.retryBaseMs * Math.pow(2, attempt - 1);

      const label = isRateLimit ? '⚠ Rate limit' : '✗ Error';
      console.error(`\n  [req ${reqIndex}] ${label} (attempt ${attempt}/${CONFIG.maxRetries}): ${err.message.split('\n')[0]}`);
      if (isLast) throw err;
      console.log(`  ↺ ${waitMs / 1000}秒後にリトライ...`);
      await sleep(waitMs);
    }
  }
}

// ============================================================
// 画像とメタデータJSONを保存
// ============================================================
async function saveImages(predictions, item, dateStr, reqIndex) {
  const outDir = path.join(CONFIG.outputDir, dateStr, item.region, item.sizeLabel);
  await ensureDir(outDir);

  const saved = [];
  for (let i = 0; i < predictions.length; i++) {
    const pred   = helpers.fromValue(predictions[i]);
    const base64 = pred.bytesBase64Encoded || pred.image?.bytesBase64Encoded;
    if (!base64) {
      console.warn(`  [req ${reqIndex}-${i}] bytesBase64Encoded が空です。スキップ。`);
      continue;
    }

    const imgBase  = `req${String(reqIndex).padStart(4, '0')}_img${i + 1}`;
    const imgFile  = path.join(outDir, `${imgBase}.png`);
    const metaFile = path.join(outDir, `${imgBase}.json`);

    await fsp.writeFile(imgFile, Buffer.from(base64, 'base64'));
    await fsp.writeFile(metaFile, JSON.stringify({
      generated_at : new Date().toISOString(),
      request_index: reqIndex,
      image_index  : i + 1,
      region       : item.region,
      style        : item.style,
      aspect_ratio : item.aspectRatio,
      size_label   : item.sizeLabel,
      prompt       : item.prompt,
      model        : CONFIG.model,
      tags         : item.tags,
      file_path    : imgFile,
    }, null, 2), 'utf-8');

    saved.push(imgFile);
  }
  return saved;
}

// ============================================================
// ユーティリティ
// ============================================================
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function formatETA(doneCount, totalCount, elapsedMs) {
  if (doneCount === 0) return '--';
  const msPerReq  = elapsedMs / doneCount;
  const remaining = (totalCount - doneCount) * msPerReq;
  const min = Math.floor(remaining / 60000);
  const sec = Math.floor((remaining % 60000) / 1000);
  return `${min}m ${sec}s`;
}

async function writeProgressSummary(dateStr, summary) {
  const summaryPath = path.join(CONFIG.outputDir, dateStr, 'summary.json');
  await ensureDir(path.dirname(summaryPath));
  await fsp.writeFile(summaryPath, JSON.stringify(summary, null, 2), 'utf-8');
}

// ============================================================
// メイン
// ============================================================
async function main() {
  console.log('='.repeat(60));
  console.log(' Vertex AI Imagen 3 — 一括生成スクリプト開始');
  console.log('='.repeat(60));
  console.log(`Project  : ${CONFIG.projectId}`);
  console.log(`Location : ${CONFIG.location}`);
  console.log(`出力先   : ${CONFIG.outputDir}`);
  console.log('');

  const dateStr = new Date().toISOString().slice(0, 10);
  const queue   = buildRequestQueue();
  const client  = createClient();

  const summary = {
    date                 : dateStr,
    total_requests       : queue.length,
    total_images_expected: queue.length * CONFIG.sampleCount,
    total_images_saved   : 0,
    failed_requests      : [],
    started_at           : new Date().toISOString(),
    finished_at          : null,
  };

  console.log(`キュー構築完了: ${queue.length} リクエスト`);
  console.log(`想定生成枚数  : ${queue.length * CONFIG.sampleCount} 枚`);
  console.log(`推定所要時間  : ≈ ${Math.ceil(queue.length * CONFIG.requestDelayMs / 60000)} 分`);
  console.log('');

  const startTime = Date.now();

  for (let idx = 0; idx < queue.length; idx++) {
    const item   = queue[idx];
    const reqNum = idx + 1;
    const eta    = formatETA(idx, queue.length, Date.now() - startTime);

    process.stdout.write(
      `[${String(reqNum).padStart(3)}/${queue.length}] ` +
      `${item.region.padEnd(6)} ${item.sizeLabel.padEnd(5)} ${item.style.padEnd(12)} ` +
      `ETA:${eta} ... `
    );

    try {
      const predictions = await callWithRetry(client, item.prompt, item.aspectRatio, reqNum);
      const saved       = await saveImages(predictions, item, dateStr, reqNum);
      summary.total_images_saved += saved.length;
      console.log(`✓ ${saved.length}枚保存`);
    } catch (err) {
      console.error(`✗ FAILED — ${err.message}`);
      summary.failed_requests.push({ index: reqNum, prompt: item.prompt, error: err.message });
    }

    // 50件ごとに進捗サマリをコンソール表示 & JSONに書き込み
    if (reqNum % 50 === 0 || reqNum === queue.length) {
      const elapsed    = Date.now() - startTime;
      const pct        = ((reqNum / queue.length) * 100).toFixed(1);
      const etaDisplay = formatETA(reqNum, queue.length, elapsed);
      console.log('');
      console.log('─'.repeat(60));
      console.log(
        ` 📊 進捗: ${reqNum}/${queue.length} リクエスト完了 (${pct}%)` +
        ` | 保存済み: ${summary.total_images_saved}枚` +
        ` | 失敗: ${summary.failed_requests.length}件` +
        ` | 残り時間: ${etaDisplay}`
      );
      console.log('─'.repeat(60));
      console.log('');
      await writeProgressSummary(dateStr, summary).catch(() => {});
    }

    if (idx < queue.length - 1) await sleep(CONFIG.requestDelayMs);
  }

  summary.finished_at = new Date().toISOString();
  await writeProgressSummary(dateStr, summary);

  const totalMs  = Date.now() - startTime;
  console.log('');
  console.log('='.repeat(60));
  console.log(' 完了レポート');
  console.log('='.repeat(60));
  console.log(`所要時間     : ${Math.floor(totalMs / 60000)}m ${Math.floor((totalMs % 60000) / 1000)}s`);
  console.log(`保存枚数     : ${summary.total_images_saved} 枚`);
  console.log(`失敗リクエスト: ${summary.failed_requests.length} 件`);
  console.log(`サマリJSON   : ${path.join(CONFIG.outputDir, dateStr, 'summary.json')}`);
  console.log('='.repeat(60));
}

main().catch(err => {
  console.error('\nFATAL ERROR:', err);
  process.exit(1);
});
