/**
 * SNS Gallery Server
 * Express API + static file server for multilingual image gallery
 */
const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const app = express();
app.use(express.json());
app.use(express.static(__dirname));

// ─── Load image data at startup ──────────────────────────────────────────────
console.log('📦 Loading labeled_images.json...');
const DATA_FILE = path.join(__dirname, 'labeled_images.json');
let IMAGES = [];

try {
  const raw = fs.readFileSync(DATA_FILE, 'utf-8');
  IMAGES = JSON.parse(raw).filter(img => img.category !== 'logos');
  console.log(`✅ Loaded ${IMAGES.length} images (logos excluded)`);
} catch (e) {
  console.error('❌ Could not load labeled_images.json:', e.message);
  process.exit(1);
}

// R2 CDN base URL for image delivery
const R2_BASE_URL = process.env.R2_BASE_URL || 'https://pub-1b2e148e5cac4d9fb1930c69576c4a4c.r2.dev';

// Normalize image path to a full R2 CDN URL
const BASE_DIR = __dirname.replace(/\\/g, '/');
function normalizePath(src) {
  const p = (src || '').replace(/\\/g, '/');
  // Extract the "images/..." portion from absolute or relative paths
  const match = p.match(/(images\/.+)$/);
  const relative = match ? match[1] : p;
  return `${R2_BASE_URL}/${relative}`;
}

// Pre-build category index for performance
const CATEGORY_COUNTS = {};
IMAGES.forEach(img => {
  const cat = img.category || 'backgrounds';
  CATEGORY_COUNTS[cat] = (CATEGORY_COUNTS[cat] || 0) + 1;
});

// ─── In-memory session store (resets on restart; use DB for production) ───────
const SESSIONS = {}; // sessionId -> { count, firstVisit, subscribed }

function getSession(sessionId) {
  if (!SESSIONS[sessionId]) {
    SESSIONS[sessionId] = {
      count: 0,
      firstVisit: Date.now(),
      subscribed: false,
      expiresAt: null
    };
  }
  return SESSIONS[sessionId];
}

// ─── API: Images (paginated) ──────────────────────────────────────────────────
app.get('/api/images', (req, res) => {
  const {
    category = 'all',
    lang = 'en-US',
    page = '1',
    limit = '50',
    q = ''
  } = req.query;

  const pageNum  = Math.max(1, parseInt(page)  || 1);
  const limitNum = Math.min(100, parseInt(limit) || 50);

  let filtered = IMAGES;

  if (category !== 'all') {
    filtered = filtered.filter(img => img.category === category);
  }

  if (q) {
    const lq = q.toLowerCase();
    filtered = filtered.filter(img => {
      const lbl = (img.labels && (img.labels[lang] || img.labels['en-US'])) || {};
      const title = (lbl.title || '').toLowerCase();
      const tags  = ((lbl.tags || []).join(' ')).toLowerCase();
      return title.includes(lq) || tags.includes(lq) || img.filename.toLowerCase().includes(lq);
    });
  }

  const total  = filtered.length;
  const start  = (pageNum - 1) * limitNum;
  const slice  = filtered.slice(start, start + limitNum);
  const pages  = Math.ceil(total / limitNum);

  const images = slice.map((img, i) => {
    const lbl  = (img.labels && (img.labels[lang] || img.labels['en-US'])) || {};
    const path = normalizePath(img.src || img.filepath || '');
    return {
      id:       start + i,
      path,
      filename: img.filename,
      category: img.category || 'backgrounds',
      title:    lbl.title || img.filename,
      tags:     (lbl.tags || []).slice(0, 8)
    };
  });

  res.json({ images, total, page: pageNum, limit: limitNum, pages });
});

// ─── API: Categories ──────────────────────────────────────────────────────────
app.get('/api/categories', (req, res) => {
  const cats = Object.entries(CATEGORY_COUNTS)
    .sort((a, b) => b[1] - a[1])
    .map(([category, count]) => ({ category, count }));
  res.json([{ category: 'all', count: IMAGES.length }, ...cats]);
});

// ─── API: Full labels for one image ──────────────────────────────────────────
app.get('/api/image-labels', (req, res) => {
  const imgPath = req.query.path;
  const img = IMAGES.find(i =>
    (i.src || i.filepath || '').replace(/\\/g, '/') === imgPath ||
    i.filename === imgPath
  );
  if (!img) return res.status(404).json({ error: 'Not found' });
  res.json(img.labels || {});
});

// ─── API: Proxy-download (streams R2 file as same-origin attachment) ─────────
// Required for iOS Safari: cross-origin <a download> is blocked; same-origin works.
app.get('/api/proxy-download', async (req, res) => {
  const imagePath = req.query.path || '';

  // Build full R2 URL, accept both full URLs and relative paths
  const fullUrl = imagePath.startsWith('http')
    ? imagePath
    : `${R2_BASE_URL}/${imagePath.replace(/^\/+/, '')}`;

  // Security: only proxy requests to our own R2 bucket
  if (!fullUrl.startsWith(R2_BASE_URL)) {
    return res.status(403).json({ error: 'Forbidden' });
  }

  try {
    const r = await fetch(fullUrl);
    if (!r.ok) return res.status(r.status).json({ error: 'Upstream error' });

    const filename = fullUrl.split('/').pop().split('?')[0] || 'image.jpg';
    res.setHeader('Content-Type', r.headers.get('content-type') || 'image/jpeg');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.setHeader('Cache-Control', 'no-store');

    // Stream response body to client (Node 18+ fetch returns a Web ReadableStream)
    const { Readable } = require('stream');
    Readable.fromWeb(r.body).pipe(res);
  } catch (err) {
    console.error('proxy-download error:', err.message);
    res.status(500).json({ error: 'Download failed' });
  }
});

// ─── API: Download (checks limits) ───────────────────────────────────────────
app.post('/api/download', (req, res) => {
  const { imagePath, sessionId } = req.body;
  if (!sessionId) return res.status(400).json({ error: 'sessionId required' });

  const FREE_MAX_DOWNLOADS = 10;
  const FREE_DAYS          = 30;

  const sess = getSession(sessionId);
  const daysSince = (Date.now() - sess.firstVisit) / 86400000;

  // Already subscribed?
  if (sess.subscribed && sess.expiresAt && Date.now() < sess.expiresAt) {
    return res.json({ allowed: true, path: imagePath, remaining: Infinity });
  }

  // Free quota exceeded?
  if (sess.count >= FREE_MAX_DOWNLOADS) {
    return res.json({ allowed: false, reason: 'download_limit', downloaded: sess.count });
  }
  if (daysSince > FREE_DAYS) {
    return res.json({ allowed: false, reason: 'trial_expired', days: Math.floor(daysSince) });
  }

  sess.count++;
  const remaining = FREE_MAX_DOWNLOADS - sess.count;
  res.json({ allowed: true, path: imagePath, remaining, downloaded: sess.count });
});

// ─── API: Stripe checkout session (placeholder) ───────────────────────────────
app.post('/api/stripe/create-session', async (req, res) => {
  const STRIPE_KEY = process.env.STRIPE_SECRET_KEY || 'sk_test_PLACEHOLDER';

  if (STRIPE_KEY.includes('PLACEHOLDER')) {
    // Placeholder mode – Stripe not yet configured
    return res.json({
      placeholder: true,
      message: 'Stripe is not configured yet. Set STRIPE_SECRET_KEY in environment variables.',
      priceJPY: 1000,
      pricePlans: [
        { currency: 'JPY', amount: 1000, label: '月額 ¥1,000' },
        { currency: 'USD', amount: 7,    label: '$7/month' },
        { currency: 'EUR', amount: 6,    label: '€6/month' },
        { currency: 'GBP', amount: 5,    label: '£5/month' }
      ]
    });
  }

  try {
    const stripe  = require('stripe')(STRIPE_KEY);
    const origin  = `${req.protocol}://${req.get('host')}`;
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      mode: 'subscription',
      line_items: [{
        price_data: {
          currency: 'jpy',
          product_data: {
            name:        'SNS Gallery Premium',
            description: '無制限ダウンロード / Unlimited Downloads'
          },
          unit_amount: 1000,
          recurring: { interval: 'month' }
        },
        quantity: 1
      }],
      success_url: `${origin}/gallery.html?subscribed=true&session_id={CHECKOUT_SESSION_ID}`,
      cancel_url:  `${origin}/gallery.html`
    });
    res.json({ url: session.url });
  } catch (err) {
    console.error('Stripe error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

// ─── Stripe webhook (placeholder) ────────────────────────────────────────────
app.post('/api/stripe/webhook', express.raw({ type: 'application/json' }), (req, res) => {
  // TODO: verify webhook signature and update session subscription status
  res.json({ received: true });
});

// ─── Start server ─────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`\n🚀 Gallery server → http://localhost:${PORT}/gallery.html\n`);
});
