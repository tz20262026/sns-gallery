'use strict';

// ============================================================
// テスト用スクリプト — 3リクエスト（16:9 / 9:16 / 3:4 各1枚）
// ============================================================

const { PredictionServiceClient } = require('@google-cloud/aiplatform').v1;
const { helpers }                  = require('@google-cloud/aiplatform');
const fsp  = require('fs').promises;
const path = require('path');

const CONFIG = {
  projectId : process.env.GOOGLE_CLOUD_PROJECT || 'spreadsheet-bot-489912',
  location  : 'us-central1',
  model     : 'imagen-3.0-generate-001',
  outputDir : process.env.OUTPUT_DIR || path.join(process.cwd(), 'images'),
  sampleCount: 1,  // テストなので1枚ずつ
};

// テスト用の3リクエスト（サイズ違い）
const TEST_REQUESTS = [
  {
    region: 'USA', style: 'noir', aspectRatio: '16:9', sizeLabel: '16-9',
    prompt: 'Cinematic noir film photograph: rain-soaked city street reflecting neon bar signs at midnight. Hard-boiled detective in fedora and trench coat. Chiaroscuro lighting, deep black shadows. Shot on 35mm film. Stock photo, professional photography, 8K resolution, award-winning composition.',
    tags: {
      en: ['noir', 'cinematic', 'rain', 'city', 'USA', 'stock-photo', 'detective'],
      ja: ['ノワール', '映画的', '雨', '都市', 'アメリカ', 'ストックフォト', '探偵'],
    },
  },
  {
    region: 'JAPAN', style: 'shinya', aspectRatio: '9:16', sizeLabel: '9-16',
    prompt: '深夜の古い缶コーヒー自販機、蛍光灯が唯一の光源。深夜の静寂を際立たせる蛍光灯の白い光とその外の真っ暗な闇の境界。ストックフォト、プロ写真、8K、自然光。Stock photo, professional photography, 8K resolution, midnight Japan, vending machine, nostalgic.',
    tags: {
      en: ['midnight', 'vending-machine', 'japan', 'stock-photo', 'niche-japan', 'street-photography'],
      ja: ['深夜', '自販機', '日本', 'ストックフォト', '日本の原風景', '夜'],
    },
  },
  {
    region: 'JAPAN', style: 'danchi', aspectRatio: '3:4', sizeLabel: '3-4',
    prompt: '昭和団地の給水塔と快晴の青空、コンクリートの質感。柔らかな午後の斜光がコンクリートに影を作る。ストックフォト、プロ写真、8K、受賞レベル構図。Stock photo, professional photography, 8K resolution, Japanese housing complex, Showa era retro.',
    tags: {
      en: ['danchi', 'apartment-complex', 'japan', 'showa', 'stock-photo', 'water-tower'],
      ja: ['団地', '給水塔', '昭和', 'ストックフォト', '日本の団地', 'コンクリート'],
    },
  },
];

// ============================================================

async function ensureDir(p) {
  await fsp.mkdir(p, { recursive: true });
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function callImagen(client, prompt, aspectRatio) {
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
      safetyFilterLevel: 'block_some',
      personGeneration : 'allow_adult',
    }),
  });
  return response.predictions || [];
}

async function main() {
  console.log('='.repeat(55));
  console.log(' Imagen 3 テスト実行 (3リクエスト / 各サイズ1枚)');
  console.log('='.repeat(55));
  console.log(`Project : ${CONFIG.projectId}`);
  console.log(`出力先  : ${CONFIG.outputDir}`);
  console.log('');

  const client  = new PredictionServiceClient({
    apiEndpoint: `${CONFIG.location}-aiplatform.googleapis.com`,
  });

  const dateStr    = new Date().toISOString().slice(0, 10);
  let savedTotal   = 0;
  let failedTotal  = 0;

  for (let i = 0; i < TEST_REQUESTS.length; i++) {
    const item = TEST_REQUESTS[i];
    console.log(`[${i + 1}/3] ${item.region} / ${item.sizeLabel} / ${item.style}`);
    console.log(`  Prompt: ${item.prompt.slice(0, 80)}...`);
    process.stdout.write('  実行中... ');

    try {
      const predictions = await callImagen(client, item.prompt, item.aspectRatio);
      const outDir = path.join(CONFIG.outputDir, dateStr, item.region, item.sizeLabel);
      await ensureDir(outDir);

      for (let j = 0; j < predictions.length; j++) {
        const pred   = helpers.fromValue(predictions[j]);
        const base64 = pred.bytesBase64Encoded || pred.image?.bytesBase64Encoded;
        if (!base64) { console.warn('\n  ⚠ base64データが空 — スキップ'); continue; }

        const base     = `test_req${i + 1}_img${j + 1}`;
        const imgFile  = path.join(outDir, `${base}.png`);
        const metaFile = path.join(outDir, `${base}.json`);

        await fsp.writeFile(imgFile, Buffer.from(base64, 'base64'));
        await fsp.writeFile(metaFile, JSON.stringify({
          generated_at : new Date().toISOString(),
          region       : item.region,
          style        : item.style,
          aspect_ratio : item.aspectRatio,
          size_label   : item.sizeLabel,
          prompt       : item.prompt,
          model        : CONFIG.model,
          tags         : item.tags,
          file_path    : imgFile,
        }, null, 2), 'utf-8');

        savedTotal++;
        console.log(`✓`);
        console.log(`  保存先: ${imgFile}`);
      }
    } catch (err) {
      failedTotal++;
      console.error(`✗ エラー`);
      console.error(`  メッセージ: ${err.message}`);

      if (err.message.includes('PERMISSION_DENIED')) {
        console.error('  → IAMロール "roles/aiplatform.user" が付与されているか確認してください');
        console.error('  → または "gcloud auth application-default login" を実行してください');
      } else if (err.message.includes('NOT_FOUND') || err.message.includes('not found')) {
        console.error('  → Vertex AI API が有効化されているか確認してください');
        console.error('  → モデル名: imagen-3.0-generate-001');
      } else if (err.message.includes('QUOTA_EXCEEDED')) {
        console.error('  → Quota超過。しばらく待ってから再実行してください');
      }
    }

    if (i < TEST_REQUESTS.length - 1) {
      console.log('  (30秒待機...)');
      await sleep(30000);
    }
    console.log('');
  }

  console.log('='.repeat(55));
  if (failedTotal === 0) {
    console.log(` ✓ テスト成功 — ${savedTotal}枚 保存完了`);
    console.log(` 出力フォルダ: ${path.join(CONFIG.outputDir, dateStr)}`);
    console.log('');
    console.log(' 本番実行する場合:');
    console.log('   node generate-images.js');
  } else {
    console.log(` ✗ テスト失敗 (${failedTotal}件エラー / ${savedTotal}件成功)`);
    console.log(' 上記のエラーメッセージを確認して問題を解決してください');
  }
  console.log('='.repeat(55));
}

main().catch(err => {
  console.error('\nFATAL:', err.message);
  process.exit(1);
});
