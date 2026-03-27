/**
 * language_detector.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Multilingual Stock Photo Gallery - Browser Language Detection & Label Loader
 *
 * Usage:
 *   const detector = new LanguageDetector(labeledImages);
 *   const lang = detector.detectLanguage();
 *   const label = detector.getLabel(imageObj, lang);
 *   console.log(label.title);  // localized title
 *   console.log(label.tags);   // localized tags array (15 items)
 * ─────────────────────────────────────────────────────────────────────────────
 */

class LanguageDetector {
  /**
   * @param {Array} labeledImages - Array of image objects from labeled_images.json
   *   Each object: { src, filename, subfolder, category, labels: { "en-US": {title, tags}, ... } }
   */
  constructor(labeledImages = []) {
    this._images = labeledImages;
    this._langCache = null;

    // Fallback priority chain: if detected lang not available, try these in order
    this._fallbackChain = ["en-US", "en-GB", "en-AU"];

    // BCP-47 to lang_code mapping (normalize browser variants to our 30 codes)
    this._normalizationMap = {
      // English variants
      "en":    "en-US", "en-us": "en-US", "en-gb": "en-GB",
      "en-au": "en-AU", "en-ca": "en-CA",
      // Chinese
      "zh":    "zh-CN", "zh-cn": "zh-CN", "zh-tw": "zh-TW",
      "zh-hk": "zh-TW", "zh-sg": "zh-CN",
      // Spanish
      "es":    "es-ES", "es-es": "es-ES", "es-mx": "es-MX",
      "es-ar": "es-AR", "es-419": "es-MX",
      // Portuguese
      "pt":    "pt-BR", "pt-br": "pt-BR", "pt-pt": "pt-PT",
      // French
      "fr":    "fr-FR", "fr-fr": "fr-FR", "fr-ca": "fr-CA",
      "fr-be": "fr-FR", "fr-ch": "fr-FR",
      // German
      "de":    "de-DE", "de-de": "de-DE", "de-at": "de-DE", "de-ch": "de-DE",
      // Japanese
      "ja":    "ja-JP", "ja-jp": "ja-JP",
      // Korean
      "ko":    "ko-KR", "ko-kr": "ko-KR",
      // Italian
      "it":    "it-IT", "it-it": "it-IT",
      // Russian
      "ru":    "ru-RU", "ru-ru": "ru-RU", "uk": "uk-UA",
      // Dutch
      "nl":    "nl-NL", "nl-nl": "nl-NL", "nl-be": "nl-NL",
      // Polish
      "pl":    "pl-PL", "pl-pl": "pl-PL",
      // Turkish
      "tr":    "tr-TR", "tr-tr": "tr-TR",
      // Indonesian
      "id":    "id-ID", "id-id": "id-ID",
      // Thai
      "th":    "th-TH", "th-th": "th-TH",
      // Swedish
      "sv":    "sv-SE", "sv-se": "sv-SE",
      // Arabic
      "ar":    "ar-SA", "ar-sa": "ar-SA", "ar-ae": "ar-SA",
      "ar-eg": "ar-SA",
      // Hindi
      "hi":    "hi-IN", "hi-in": "hi-IN",
      // Vietnamese
      "vi":    "vi-VN", "vi-vn": "vi-VN",
      // Czech
      "cs":    "cs-CZ", "cs-cz": "cs-CZ",
      // Hungarian
      "hu":    "hu-HU", "hu-hu": "hu-HU",
      // Romanian
      "ro":    "ro-RO", "ro-ro": "ro-RO",
      // Ukrainian
      "uk":    "uk-UA", "uk-ua": "uk-UA",
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Language Detection
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Detect the best matching language from the browser environment.
   * Checks navigator.languages, navigator.language, and URL ?lang= param.
   * @returns {string} BCP-47 lang code (e.g. "ja-JP")
   */
  detectLanguage() {
    if (this._langCache) return this._langCache;

    // 1. Check URL parameter: ?lang=ja-JP
    const urlLang = this._getUrlLangParam();
    if (urlLang) {
      const normalized = this._normalize(urlLang);
      if (normalized) { this._langCache = normalized; return normalized; }
    }

    // 2. Check localStorage override
    const stored = this._getStoredLang();
    if (stored) {
      const normalized = this._normalize(stored);
      if (normalized) { this._langCache = normalized; return normalized; }
    }

    // 3. navigator.languages (ordered preference list)
    const browserLangs = this._getBrowserLanguages();
    for (const lang of browserLangs) {
      const normalized = this._normalize(lang);
      if (normalized) { this._langCache = normalized; return normalized; }
    }

    // 4. Fallback to English
    this._langCache = "en-US";
    return "en-US";
  }

  /**
   * Override the detected language (saves to localStorage).
   * @param {string} langCode - BCP-47 language code
   */
  setLanguage(langCode) {
    const normalized = this._normalize(langCode) || langCode;
    this._langCache = normalized;
    try { localStorage.setItem("gallery_lang", normalized); } catch (_) {}
  }

  /**
   * Get available language codes from the first image with labels.
   * @returns {string[]} Array of available lang_codes
   */
  getAvailableLanguages() {
    for (const img of this._images) {
      if (img.labels && typeof img.labels === "object") {
        return Object.keys(img.labels);
      }
    }
    return ["en-US"];
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Label Retrieval
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Get the localized label for an image object.
   * Falls back through fallback chain if the target language is unavailable.
   *
   * @param {Object} imageObj - Image object from labeled_images array
   * @param {string} [lang] - BCP-47 lang code (defaults to detectLanguage())
   * @returns {{ title: string, tags: string[], lang: string }}
   */
  getLabel(imageObj, lang = null) {
    const targetLang = lang || this.detectLanguage();
    const labels = imageObj.labels || {};

    // Try target language
    if (labels[targetLang]) {
      return { ...labels[targetLang], lang: targetLang };
    }

    // Try fallback chain
    for (const fb of this._fallbackChain) {
      if (labels[fb]) return { ...labels[fb], lang: fb };
    }

    // Try any available language
    const anyLang = Object.keys(labels)[0];
    if (anyLang) return { ...labels[anyLang], lang: anyLang };

    // Ultimate fallback
    return {
      title: imageObj.filename || "Untitled",
      tags: [],
      lang: "en-US"
    };
  }

  /**
   * Get all labels for an image (all 30 languages).
   * @param {Object} imageObj
   * @returns {Object} { "en-US": {title, tags}, "ja-JP": {title, tags}, ... }
   */
  getAllLabels(imageObj) {
    return imageObj.labels || {};
  }

  /**
   * Filter images by category.
   * @param {string} category - One of the 15 categories
   * @returns {Array} Filtered image array
   */
  filterByCategory(category) {
    if (!category || category === "all") return this._images;
    return this._images.filter(img => img.category === category);
  }

  /**
   * Search images by tag or title in the current language.
   * @param {string} query - Search query
   * @param {string} [lang] - Language to search in (defaults to detected)
   * @returns {Array} Matching images
   */
  search(query, lang = null) {
    const targetLang = lang || this.detectLanguage();
    const q = query.toLowerCase().trim();
    if (!q) return this._images;

    return this._images.filter(img => {
      const label = this.getLabel(img, targetLang);
      const inTitle = label.title.toLowerCase().includes(q);
      const inTags = label.tags.some(tag => tag.toLowerCase().includes(q));
      const inCategory = (img.category || "").toLowerCase().includes(q);
      return inTitle || inTags || inCategory;
    });
  }

  /**
   * Get a summary of all 30 available language options for a language switcher UI.
   * @returns {Array} [{lang_code, language, country, native_name}, ...]
   */
  getLanguageOptions() {
    const available = this.getAvailableLanguages();
    // Standard metadata for the 30 selected countries
    const ALL_LANGS = [
      { lang_code: "en-US",  language: "English",    country: "United States",  native_name: "English"        },
      { lang_code: "ja-JP",  language: "Japanese",   country: "Japan",          native_name: "日本語"          },
      { lang_code: "zh-CN",  language: "Chinese",    country: "China",          native_name: "中文（简体）"    },
      { lang_code: "zh-TW",  language: "Chinese",    country: "Taiwan",         native_name: "中文（繁體）"    },
      { lang_code: "de-DE",  language: "German",     country: "Germany",        native_name: "Deutsch"        },
      { lang_code: "fr-FR",  language: "French",     country: "France",         native_name: "Français"       },
      { lang_code: "es-ES",  language: "Spanish",    country: "Spain",          native_name: "Español"        },
      { lang_code: "pt-BR",  language: "Portuguese", country: "Brazil",         native_name: "Português (BR)" },
      { lang_code: "it-IT",  language: "Italian",    country: "Italy",          native_name: "Italiano"       },
      { lang_code: "ko-KR",  language: "Korean",     country: "South Korea",    native_name: "한국어"          },
      { lang_code: "ru-RU",  language: "Russian",    country: "Russia",         native_name: "Русский"        },
      { lang_code: "hi-IN",  language: "Hindi",      country: "India",          native_name: "हिन्दी"          },
      { lang_code: "es-MX",  language: "Spanish",    country: "Mexico",         native_name: "Español (MX)"   },
      { lang_code: "nl-NL",  language: "Dutch",      country: "Netherlands",    native_name: "Nederlands"     },
      { lang_code: "pl-PL",  language: "Polish",     country: "Poland",         native_name: "Polski"         },
      { lang_code: "tr-TR",  language: "Turkish",    country: "Turkey",         native_name: "Türkçe"         },
      { lang_code: "id-ID",  language: "Indonesian", country: "Indonesia",      native_name: "Bahasa Indonesia"},
      { lang_code: "th-TH",  language: "Thai",       country: "Thailand",       native_name: "ภาษาไทย"        },
      { lang_code: "sv-SE",  language: "Swedish",    country: "Sweden",         native_name: "Svenska"        },
      { lang_code: "en-AU",  language: "English",    country: "Australia",      native_name: "English (AU)"   },
      { lang_code: "fr-CA",  language: "French",     country: "Canada",         native_name: "Français (CA)"  },
      { lang_code: "ar-SA",  language: "Arabic",     country: "Saudi Arabia",   native_name: "العربية"        },
      { lang_code: "cs-CZ",  language: "Czech",      country: "Czech Republic", native_name: "Čeština"        },
      { lang_code: "hu-HU",  language: "Hungarian",  country: "Hungary",        native_name: "Magyar"         },
      { lang_code: "ro-RO",  language: "Romanian",   country: "Romania",        native_name: "Română"         },
      { lang_code: "vi-VN",  language: "Vietnamese", country: "Vietnam",        native_name: "Tiếng Việt"     },
      { lang_code: "uk-UA",  language: "Ukrainian",  country: "Ukraine",        native_name: "Українська"     },
      { lang_code: "pt-PT",  language: "Portuguese", country: "Portugal",       native_name: "Português (PT)" },
      { lang_code: "es-AR",  language: "Spanish",    country: "Argentina",      native_name: "Español (AR)"   },
      { lang_code: "en-GB",  language: "English",    country: "United Kingdom", native_name: "English (UK)"   },
    ];
    return ALL_LANGS.filter(l => available.includes(l.lang_code));
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Private Helpers
  // ─────────────────────────────────────────────────────────────────────────

  _normalize(lang) {
    if (!lang) return null;
    const lower = lang.toLowerCase().replace("_", "-");
    // Exact match
    if (this._normalizationMap[lower]) return this._normalizationMap[lower];
    // Try just the primary subtag (e.g. "en" from "en-AU")
    const primary = lower.split("-")[0];
    if (this._normalizationMap[primary]) return this._normalizationMap[primary];
    // Try capitalizing region: "en-us" → "en-US"
    const parts = lower.split("-");
    if (parts.length === 2) {
      const reconstructed = `${parts[0]}-${parts[1].toUpperCase()}`;
      const available = this.getAvailableLanguages();
      if (available.includes(reconstructed)) return reconstructed;
    }
    return null;
  }

  _getUrlLangParam() {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get("lang");
    } catch (_) { return null; }
  }

  _getStoredLang() {
    try { return localStorage.getItem("gallery_lang"); } catch (_) { return null; }
  }

  _getBrowserLanguages() {
    try {
      if (navigator.languages && navigator.languages.length > 0) {
        return Array.from(navigator.languages);
      }
      if (navigator.language) return [navigator.language];
    } catch (_) {}
    return [];
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Gallery Initializer
// Automatically initialize when labeled_images.json is loaded
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Load labeled_images.json and initialize the LanguageDetector.
 * @param {string} [jsonPath="./labeled_images.json"]
 * @returns {Promise<{ detector: LanguageDetector, images: Array, lang: string }>}
 */
async function initMultilingualGallery(jsonPath = "./labeled_images.json") {
  const response = await fetch(jsonPath);
  if (!response.ok) throw new Error(`Failed to load ${jsonPath}: ${response.status}`);
  const images = await response.json();

  const detector = new LanguageDetector(images);
  const lang = detector.detectLanguage();

  console.log(`[LanguageDetector] Loaded ${images.length} images, language: ${lang}`);
  return { detector, images, lang };
}

// ─────────────────────────────────────────────────────────────────────────────
// Export (works in both browser and Node.js)
// ─────────────────────────────────────────────────────────────────────────────
if (typeof module !== "undefined" && module.exports) {
  module.exports = { LanguageDetector, initMultilingualGallery };
}
