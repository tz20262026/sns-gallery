/**
 * multilingual_gallery_integration.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Integrates LanguageDetector with the existing gallery.html UI.
 * Include AFTER language_detector.js in gallery.html.
 *
 * Features:
 *   - Auto-detects browser language on page load
 *   - Language switcher dropdown in header
 *   - Multilingual search (title + tags)
 *   - Category filter with localized names
 *   - RTL support for Arabic
 *   - Copies localized tags to clipboard on click
 * ─────────────────────────────────────────────────────────────────────────────
 */

(async function () {
  // ── Constants ────────────────────────────────────────────────────────────
  const CATEGORIES = [
    "all", "animals", "architecture", "backgrounds", "business",
    "education", "family", "food", "logos", "nature", "plants-flowers",
    "sports", "technology", "travel", "wallpapers"
  ];

  const CATEGORY_ICONS = {
    all: "🌐", animals: "🐾", architecture: "🏛️", backgrounds: "🖼️",
    business: "💼", education: "📚", family: "👨‍👩‍👧", food: "🍽️",
    logos: "🎨", nature: "🌿", "plants-flowers": "🌸", sports: "⚽",
    technology: "💻", travel: "✈️", wallpapers: "🌅"
  };

  const RTL_LANGS = ["ar-SA"];

  // ── State ─────────────────────────────────────────────────────────────────
  let detector = null;
  let allImages = [];
  let currentLang = "en-US";
  let currentCategory = "all";
  let currentQuery = "";

  // ── Initialization ────────────────────────────────────────────────────────
  async function init() {
    try {
      const result = await initMultilingualGallery("./labeled_images.json");
      detector = result.detector;
      allImages = result.images;
      currentLang = result.lang;

      buildLanguageSwitcher();
      buildCategoryFilters();
      applyRtl(currentLang);
      renderGallery();
      bindSearchInput();

      console.log("[Gallery] Multilingual gallery initialized.");
    } catch (err) {
      console.warn("[Gallery] labeled_images.json not found, using legacy mode.", err.message);
      // Fall through to existing gallery.html behavior
    }
  }

  // ── Language Switcher ─────────────────────────────────────────────────────
  function buildLanguageSwitcher() {
    const options = detector.getLanguageOptions();
    if (options.length === 0) return;

    const container = document.getElementById("lang-switcher-container");
    if (!container) return;

    const select = document.createElement("select");
    select.id = "lang-switcher";
    select.setAttribute("aria-label", "Language");
    select.style.cssText = `
      background: #2a2a2a; color: #e8c97a; border: 1px solid #e8c97a;
      padding: 4px 10px; border-radius: 6px; font-size: 13px; cursor: pointer;
    `;

    options.forEach(opt => {
      const el = document.createElement("option");
      el.value = opt.lang_code;
      el.textContent = `${opt.native_name} (${opt.country})`;
      if (opt.lang_code === currentLang) el.selected = true;
      select.appendChild(el);
    });

    select.addEventListener("change", () => {
      currentLang = select.value;
      detector.setLanguage(currentLang);
      applyRtl(currentLang);
      renderGallery();
    });

    container.appendChild(select);
  }

  // ── Category Filters ──────────────────────────────────────────────────────
  function buildCategoryFilters() {
    const bar = document.getElementById("category-filter-bar");
    if (!bar) return;

    CATEGORIES.forEach(cat => {
      const btn = document.createElement("button");
      btn.textContent = `${CATEGORY_ICONS[cat] || ""} ${cat}`;
      btn.dataset.category = cat;
      btn.className = "cat-filter-btn";
      btn.style.cssText = `
        background: ${cat === "all" ? "#e8c97a" : "#2a2a2a"};
        color: ${cat === "all" ? "#1a1a1a" : "#ccc"};
        border: 1px solid #444; padding: 5px 12px; border-radius: 20px;
        font-size: 12px; cursor: pointer; margin: 3px; transition: all 0.2s;
      `;
      btn.addEventListener("click", () => {
        currentCategory = cat;
        document.querySelectorAll(".cat-filter-btn").forEach(b => {
          b.style.background = "#2a2a2a";
          b.style.color = "#ccc";
        });
        btn.style.background = "#e8c97a";
        btn.style.color = "#1a1a1a";
        renderGallery();
      });
      bar.appendChild(btn);
    });
  }

  // ── RTL Support ───────────────────────────────────────────────────────────
  function applyRtl(lang) {
    document.documentElement.dir = RTL_LANGS.includes(lang) ? "rtl" : "ltr";
  }

  // ── Search Binding ────────────────────────────────────────────────────────
  function bindSearchInput() {
    const input = document.getElementById("search-input");
    if (!input) return;
    let debounceTimer;
    input.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentQuery = input.value;
        renderGallery();
      }, 250);
    });
  }

  // ── Gallery Renderer ──────────────────────────────────────────────────────
  function renderGallery() {
    const container = document.getElementById("gallery-container");
    if (!container || !detector) return;

    // Filter & search
    let filtered = detector.filterByCategory(currentCategory);
    if (currentQuery.trim()) {
      filtered = detector.search(currentQuery, currentLang);
      if (currentCategory !== "all") {
        filtered = filtered.filter(img => img.category === currentCategory);
      }
    }

    // Update count
    const countEl = document.getElementById("image-count");
    if (countEl) countEl.textContent = `${filtered.length.toLocaleString()} images`;

    // Render cards
    container.innerHTML = "";
    filtered.forEach(img => {
      const label = detector.getLabel(img, currentLang);
      const card = createCard(img, label);
      container.appendChild(card);
    });
  }

  // ── Card Creator ──────────────────────────────────────────────────────────
  function createCard(img, label) {
    const card = document.createElement("div");
    card.className = "gallery-card";
    card.style.cssText = `
      background: #1e1e1e; border: 1px solid #333; border-radius: 10px;
      overflow: hidden; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
      position: relative;
    `;

    card.innerHTML = `
      <div style="position:relative; overflow:hidden; aspect-ratio:16/9; background:#111;">
        <img src="${escapeHtml(img.src)}" alt="${escapeHtml(label.title)}"
             loading="lazy"
             style="width:100%; height:100%; object-fit:cover; display:block; transition:transform 0.3s;"
             onerror="this.style.display='none'">
        <span style="
          position:absolute; top:6px; left:6px;
          background:rgba(0,0,0,0.7); color:#e8c97a;
          font-size:10px; padding:2px 7px; border-radius:10px;
          text-transform:uppercase; letter-spacing:0.5px;
        ">${escapeHtml(img.category || "")}</span>
      </div>
      <div style="padding:10px 12px;">
        <p style="margin:0 0 8px; font-size:13px; color:#e0e0e0; line-height:1.4;
                  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
                  overflow:hidden;" title="${escapeHtml(label.title)}">
          ${escapeHtml(label.title)}
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
          ${label.tags.slice(0, 5).map(tag => `
            <span class="tag-chip" data-tag="${escapeHtml(tag)}" style="
              background:#2a2a2a; color:#aaa; font-size:10px;
              padding:2px 7px; border-radius:10px; border:1px solid #444;
              cursor:pointer; transition:all 0.15s;
            ">${escapeHtml(tag)}</span>
          `).join("")}
          ${label.tags.length > 5 ? `<span style="color:#666; font-size:10px;">+${label.tags.length - 5}</span>` : ""}
        </div>
        <button class="copy-tags-btn" style="
          background:transparent; border:1px solid #444; color:#888;
          font-size:10px; padding:3px 9px; border-radius:6px; cursor:pointer;
          width:100%; transition:all 0.15s;
        ">📋 Copy all tags</button>
      </div>
    `;

    // Hover effects
    card.addEventListener("mouseenter", () => {
      card.style.transform = "translateY(-3px)";
      card.style.boxShadow = "0 8px 24px rgba(232,201,122,0.15)";
      const imgEl = card.querySelector("img");
      if (imgEl) imgEl.style.transform = "scale(1.05)";
    });
    card.addEventListener("mouseleave", () => {
      card.style.transform = "";
      card.style.boxShadow = "";
      const imgEl = card.querySelector("img");
      if (imgEl) imgEl.style.transform = "";
    });

    // Tag chip hover
    card.querySelectorAll(".tag-chip").forEach(chip => {
      chip.addEventListener("mouseenter", () => {
        chip.style.background = "#e8c97a";
        chip.style.color = "#1a1a1a";
        chip.style.borderColor = "#e8c97a";
      });
      chip.addEventListener("mouseleave", () => {
        chip.style.background = "#2a2a2a";
        chip.style.color = "#aaa";
        chip.style.borderColor = "#444";
      });
      chip.addEventListener("click", e => {
        e.stopPropagation();
        document.getElementById("search-input").value = chip.dataset.tag;
        currentQuery = chip.dataset.tag;
        renderGallery();
      });
    });

    // Copy all tags button
    const copyBtn = card.querySelector(".copy-tags-btn");
    const label_ref = { tags: [...(label.tags || [])] };
    copyBtn.addEventListener("click", e => {
      e.stopPropagation();
      const allLabels = detector.getAllLabels(img);
      const langLabel = allLabels[currentLang] || label_ref;
      const tagsText = (langLabel.tags || []).join(", ");
      navigator.clipboard.writeText(tagsText).then(() => {
        copyBtn.textContent = "✓ Copied!";
        copyBtn.style.color = "#e8c97a";
        setTimeout(() => {
          copyBtn.textContent = "📋 Copy all tags";
          copyBtn.style.color = "#888";
        }, 2000);
      }).catch(() => {
        // Fallback for non-HTTPS
        const el = document.createElement("textarea");
        el.value = tagsText;
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => { copyBtn.textContent = "📋 Copy all tags"; }, 2000);
      });
    });

    return card;
  }

  // ── Utility ───────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── Auto-inject required DOM elements if missing ──────────────────────────
  function ensureDomElements() {
    // Language switcher container
    if (!document.getElementById("lang-switcher-container")) {
      const header = document.querySelector("header, .header, nav") ||
                     document.querySelector("body > *:first-child");
      if (header) {
        const div = document.createElement("div");
        div.id = "lang-switcher-container";
        div.style.cssText = "display:inline-flex; align-items:center; gap:8px;";
        header.appendChild(div);
      }
    }
    // Category filter bar
    if (!document.getElementById("category-filter-bar")) {
      const main = document.querySelector("main, #main, .main, #gallery-container");
      if (main) {
        const bar = document.createElement("div");
        bar.id = "category-filter-bar";
        bar.style.cssText = "padding:12px 0; display:flex; flex-wrap:wrap; gap:4px;";
        main.parentNode.insertBefore(bar, main);
      }
    }
    // Gallery container
    if (!document.getElementById("gallery-container")) {
      const existing = document.querySelector(".gallery, #gallery, .images");
      if (existing) existing.id = "gallery-container";
    }
    // Image count badge
    if (!document.getElementById("image-count")) {
      const h = document.querySelector("h1, h2");
      if (h) {
        const span = document.createElement("span");
        span.id = "image-count";
        span.style.cssText = "font-size:14px; color:#888; margin-left:12px;";
        h.appendChild(span);
      }
    }
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { ensureDomElements(); init(); });
  } else {
    ensureDomElements();
    init();
  }
})();
