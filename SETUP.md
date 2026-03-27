# 実行手順書 — 17:00ミッション開始ガイド

## ステップ1: 事前準備（16:00までに完了させること）

### 1-1. Python環境確認
```bash
python --version   # 3.9以上であること
```

### 1-2. 必要ライブラリのインストール
```bash
pip install google-genai google-cloud-aiplatform
```

### 1-3. Google Cloud 認証
```bash
# gcloud CLIをインストール済みの場合
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```
※ブラウザが開くのでGoogleアカウントでログイン

### 1-4. ProjectIDの設定
`generate_assets.py` を開き、冒頭の以下の行を編集：
```python
PROJECT_ID = "YOUR_PROJECT_ID"  # ← ここを実際のIDに変更
```
**Google CloudプロジェクトIDの確認場所:**
→ https://console.cloud.google.com/ のプロジェクト選択ドロップダウン

---

## ステップ2: 17:00に実行

### コマンドプロンプトを開いて以下を実行
```bash
cd C:\Users\81808\Desktop\SNS_Project
python generate_assets.py
```

### 実行中の表示例
```
============================================================
ハリウッド映画級 資産生成ミッション 開始
開始時刻: 2026-03-12 17:00:00
============================================================
✓ フォルダ準備完了

[FAST] 画像生成開始 ...
  [FAST] children 01/35 → 4枚保存 (累計4枚)
  [FAST] children 02/35 → 4枚保存 (累計8枚)
  ...
```

---

## 保存先フォルダ構成

```
SNS_Project/
├── generate_assets.py    ← メインスクリプト
├── images/
│   ├── children/         ← こども向け銀河冒険（Pixarスタイル）
│   └── showa/            ← 昭和・シネマティック
├── videos/               ← Veo動画5本
└── manuscript/           ← 原稿用（手動で使用）
```

---

## 所要時間の目安

| フェーズ | リクエスト数 | 画像枚数 | 目安時間 |
|---------|------------|--------|--------|
| Fast生成 | 70 | 280枚 | 約20〜40分 |
| Standard生成 | 70 | 280枚 | 約40〜60分 |
| 動画生成 (Veo) | 5 | 5本 | 約30〜60分 |
| **合計** | **145** | **560枚+5本** | **約2〜3時間** |

---

## エラー発生時の対処

### `quota exceeded` エラー
→ しばらく待ってから再実行。17:00リセット直後が最も空いている。

### `model not found` エラー
→ Imagen 4.0 の利用申請が必要な場合あり:
https://cloud.google.com/vertex-ai/generative-ai/docs/image/overview

### 認証エラー
```bash
gcloud auth application-default login
```
を再実行。

---

## Google Cloudプロジェクト確認事項

実行前に以下のAPIが有効化されているか確認：
- Vertex AI API
- Cloud Storage API (動画保存に使用)

確認先: https://console.cloud.google.com/apis/dashboard
