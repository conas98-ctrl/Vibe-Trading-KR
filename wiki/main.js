import { initTheme } from "./theme.js";

const REPO = "pinehill99/Vibe-Trading-KR";
const API = `https://api.github.com/repos/${REPO}`;
const STARS_CACHE_KEY = "vibetrading-github-stars";
const STARS_TTL_MS = 12 * 60 * 60 * 1000;

function formatStarCount(n) {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return "--";
  if (n < 1000) return String(Math.round(n));
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(1)}m`;
}

function readStarsCache() {
  try {
    const raw = localStorage.getItem(STARS_CACHE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (typeof value.count !== "number" || typeof value.at !== "number") return null;
    return value;
  } catch {
    return null;
  }
}

function writeStarsCache(count) {
  try {
    localStorage.setItem(STARS_CACHE_KEY, JSON.stringify({ count, at: Date.now() }));
  } catch {
    /* private mode */
  }
}

function initStars() {
  const el = document.getElementById("star-count");
  if (!el) return;
  const cached = readStarsCache();
  if (cached) el.textContent = formatStarCount(cached.count);
  if (cached && Date.now() - cached.at < STARS_TTL_MS) return;

  fetch(API, { headers: { Accept: "application/vnd.github+json" } })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((data) => {
      if (typeof data.stargazers_count !== "number") return;
      writeStarsCache(data.stargazers_count);
      el.textContent = formatStarCount(data.stargazers_count);
    })
    .catch(() => {
      if (!cached) el.textContent = "--";
    });
}

function initInstallTabs() {
  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  if (!tabs.length) return;

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      const key = tab.getAttribute("data-tab");
      for (const item of tabs) {
        const selected = item === tab;
        item.setAttribute("aria-selected", String(selected));
        const panelId = item.getAttribute("aria-controls");
        if (panelId) {
          const panel = document.getElementById(panelId);
          if (panel) panel.hidden = !selected;
        }
      }
      if (key) {
        try {
          localStorage.setItem("vibetrading-install-tab", key);
        } catch {
          /* ignore */
        }
      }
    });
  }

  try {
    const saved = localStorage.getItem("vibetrading-install-tab");
    const selected = tabs.find((tab) => tab.getAttribute("data-tab") === saved);
    if (selected) selected.click();
  } catch {
    /* ignore */
  }
}

const LANG_KEY = "vibetrading-lang";
const SUPPORTED_LANGS = ["en", "ko"];

function getLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (SUPPORTED_LANGS.includes(saved)) return saved;
  } catch {
    /* ignore */
  }
  return (navigator.language || "en").toLowerCase().startsWith("ko") ? "ko" : "en";
}

function setLang(lang) {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* ignore */
  }
}

async function applyLocale(lang = getLang()) {
  document.documentElement.lang = lang;
  try {
    const response = await fetch(new URL(`locales/${lang}.json`, import.meta.url));
    if (!response.ok) return;
    const messages = await response.json();
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (key && messages[key] != null) el.textContent = messages[key];
    });
    document.querySelectorAll("[data-i18n-html]").forEach((el) => {
      const key = el.getAttribute("data-i18n-html");
      if (key && messages[key] != null) el.innerHTML = messages[key];
    });
    const toggle = document.getElementById("lang-toggle");
    if (toggle && messages["lang.toggle"] != null) toggle.textContent = messages["lang.toggle"];
  } catch {
    /* static fallback text is already in the HTML */
  }
}

function initLangToggle() {
  const actions = document.querySelector(".site-actions");
  if (!actions || document.getElementById("lang-toggle")) return;
  const btn = document.createElement("button");
  btn.id = "lang-toggle";
  btn.type = "button";
  btn.className = "lang-toggle";
  btn.setAttribute("aria-label", "Toggle language / 언어 전환");
  btn.textContent = getLang() === "ko" ? "English" : "한국어";
  btn.addEventListener("click", () => {
    const next = getLang() === "ko" ? "en" : "ko";
    setLang(next);
    applyLocale(next);
  });
  actions.insertBefore(btn, actions.firstChild);
}

function initHeaderScroll() {
  const header = document.getElementById("site-header");
  if (!header) return;
  const sync = () => header.classList.toggle("is-scrolled", window.scrollY > 10);
  sync();
  window.addEventListener("scroll", sync, { passive: true });
}

function formatTrafficCount(n) {
  n = Number(n) || 0;
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}`.replace(/\.0$/, "") + "K";
}

// Render the footer traffic counter from /api/stats (agent vs human visitors to
// this site, counted server-side by the Pages middleware, plus PyPI installs).
// The block stays hidden until real data arrives, so it never shows dashes.
function initTraffic() {
  const block = document.getElementById("footer-traffic");
  if (!block) return;
  fetch("/api/stats")
    .then((r) => (r.ok ? r.json() : null))
    .then((stats) => {
      if (!stats) return;
      const set = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
      };
      if (stats.web) {
        set("vt-agents", formatTrafficCount(stats.web.agent));
        set("vt-humans", formatTrafficCount(stats.web.human));
      }
      if (stats.pypi) set("vt-installs", formatTrafficCount(stats.pypi.last_month));
      block.hidden = false;
    })
    .catch(() => {
      /* stats unavailable — leave the block hidden */
    });
}

initTheme();
initStars();
initInstallTabs();
initHeaderScroll();
initLangToggle();
applyLocale();
initTraffic();
