/**
 * subscription.js
 * Client-side subscription & download limit management
 */
(function() {
  'use strict';

  const FREE_LIMIT  = 10;
  const FREE_DAYS   = 30;
  const PRICE_JPY   = 1000;

  // ── Session persistence ───────────────────────────────────────────────────
  function loadState() {
    try {
      const raw = localStorage.getItem('sns_gallery_sub');
      if (raw) return JSON.parse(raw);
    } catch (_) {}
    return {
      sessionId:   crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2),
      firstVisit:  Date.now(),
      downloaded:  0,
      subscribed:  false,
      expiresAt:   null
    };
  }

  function saveState(state) {
    try { localStorage.setItem('sns_gallery_sub', JSON.stringify(state)); } catch (_) {}
  }

  const state = loadState();
  saveState(state); // ensure firstVisit is persisted immediately

  // Check URL for Stripe success callback
  if (new URLSearchParams(location.search).get('subscribed') === 'true') {
    state.subscribed = true;
    state.expiresAt  = Date.now() + 30 * 86400000; // 30 days
    saveState(state);
    history.replaceState({}, '', location.pathname); // clean URL
  }

  // ── Computed helpers ──────────────────────────────────────────────────────
  function isSubscribed() {
    return state.subscribed && state.expiresAt && Date.now() < state.expiresAt;
  }

  function daysSinceFirst() {
    return (Date.now() - state.firstVisit) / 86400000;
  }

  function remainingFree() {
    if (isSubscribed()) return Infinity;
    return Math.max(0, FREE_LIMIT - state.downloaded);
  }

  function trialExpired() {
    return !isSubscribed() && daysSinceFirst() > FREE_DAYS;
  }

  function canDownload() {
    return isSubscribed() || (!trialExpired() && state.downloaded < FREE_LIMIT);
  }

  // ── Download handler ──────────────────────────────────────────────────────
  async function requestDownload(imagePath, filename) {
    if (!canDownload()) {
      showPaywall(trialExpired() ? 'trial_expired' : 'download_limit');
      return;
    }

    try {
      const resp = await fetch('/api/download', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ imagePath, sessionId: state.sessionId })
      });
      const data = await resp.json();

      if (!data.allowed) {
        showPaywall(data.reason || 'download_limit');
        return;
      }

      // Update local state
      state.downloaded = data.downloaded || state.downloaded + 1;
      saveState(state);

      // Trigger actual download
      const a = document.createElement('a');
      a.href     = '/' + imagePath;
      a.download = filename || imagePath.split('/').pop();
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);

      // Show remaining count toast
      if (!isSubscribed()) {
        const rem = FREE_LIMIT - state.downloaded;
        showToast(
          rem > 0
            ? `✅ ダウンロード完了 (残り無料枠: ${rem}枚)`
            : '⚠️ 無料枠を使い切りました。プレミアムにアップグレードしてください。',
          rem > 0 ? 'success' : 'warning'
        );
      }
    } catch (err) {
      console.error('Download error:', err);
      showToast('❌ ダウンロードに失敗しました', 'error');
    }
  }

  // ── Paywall modal ─────────────────────────────────────────────────────────
  function showPaywall(reason) {
    const modal = document.getElementById('paywall-modal');
    if (!modal) return;

    const msgEl = modal.querySelector('#paywall-msg');
    if (msgEl) {
      if (reason === 'trial_expired') {
        msgEl.textContent = '30日間の無料トライアル期間が終了しました。';
      } else {
        msgEl.textContent = `無料ダウンロード枠（${FREE_LIMIT}枚）を使い切りました。`;
      }
    }

    modal.classList.add('active');
  }

  // ── Stripe checkout ───────────────────────────────────────────────────────
  async function startCheckout(currency) {
    const btn = document.getElementById('checkout-btn');
    if (btn) { btn.disabled = true; btn.textContent = '処理中...'; }

    try {
      const resp = await fetch('/api/stripe/create-session', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ sessionId: state.sessionId, currency: currency || 'JPY' })
      });
      const data = await resp.json();

      if (data.placeholder) {
        // Stripe not yet configured – show info
        showToast('💳 Stripe APIキーを設定するとお支払いが有効になります。', 'info', 5000);
        if (btn) { btn.disabled = false; btn.textContent = '🔑 APIキーを設定してください'; }
        return;
      }

      if (data.url) {
        location.href = data.url;
      }
    } catch (err) {
      console.error('Checkout error:', err);
      if (btn) { btn.disabled = false; btn.textContent = 'サブスクリプションを開始'; }
      showToast('エラーが発生しました', 'error');
    }
  }

  // ── Toast notification ────────────────────────────────────────────────────
  function showToast(message, type, duration) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className   = 'toast active toast-' + (type || 'success');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('active'), duration || 3000);
  }

  // ── Status bar update ─────────────────────────────────────────────────────
  function updateStatusBar() {
    const bar = document.getElementById('sub-status-bar');
    if (!bar) return;

    if (isSubscribed()) {
      bar.innerHTML = '✨ <b>プレミアム会員</b> – 無制限ダウンロード';
      bar.className = 'sub-bar sub-premium';
      return;
    }

    const rem  = remainingFree();
    const days = Math.max(0, FREE_DAYS - Math.floor(daysSinceFirst()));

    if (trialExpired() || rem === 0) {
      bar.innerHTML = `⚠️ 無料枠終了 – <a href="#" id="upgrade-link">プレミアムにアップグレード ¥${PRICE_JPY.toLocaleString()}/月</a>`;
      bar.className = 'sub-bar sub-warn';
      const link = document.getElementById('upgrade-link');
      if (link) link.addEventListener('click', e => { e.preventDefault(); showPaywall('download_limit'); });
    } else {
      bar.innerHTML = `🆓 無料プラン – 残り <b>${rem}</b>枚 / 残り <b>${days}</b>日`;
      bar.className = 'sub-bar sub-free';
    }
  }

  // ── Public API ────────────────────────────────────────────────────────────
  window.SNSSub = {
    canDownload,
    isSubscribed,
    remainingFree,
    requestDownload,
    showPaywall,
    startCheckout,
    showToast,
    updateStatusBar,
    state
  };

  // Auto-update status bar when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', updateStatusBar);
  } else {
    updateStatusBar();
  }
})();
