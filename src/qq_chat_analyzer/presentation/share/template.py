"""Self-contained HTML/CSS template for the Echo share card."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .builder import ShareCardData


SHARE_IMAGE_WIDTH = 1200
SHARE_IMAGE_HEIGHT = 2000


SHARE_CARD_HTML_SKELETON = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="color-scheme" content="light">
  <title>Echo · 聊天回声纪念卡</title>
  <style>__SHARE_CSS__</style>
</head>
<body>
  <main class="card" aria-label="Echo 聊天回声纪念卡">
    <section class="header">
      <div class="brand-row">
        <span class="brand">ECHO</span>
        <span class="edition">MEMORY CARD · 01</span>
      </div>
      <h1 class="subtitle" id="share-subtitle">这段聊天的回声</h1>
      <div class="conversation">
        <span class="conversation-label" id="conversation-label">这段聊天</span>
        <h2 class="conversation-name" id="conversation-name">一起留下的聊天</h2>
      </div>
    </section>

    <div id="sections">
      <section class="section hero">
        <p class="folio">01 · TOGETHER</p>
        <h2 class="section-title">共同留下</h2>
        <div class="hero-figure">
          <span class="hero-number" id="message-count">0</span>
          <span class="hero-unit">条消息</span>
        </div>
        <p class="hero-span">跨越 <strong id="time-span">刚刚开始</strong></p>
      </section>

      <section class="section" id="sessions">
        <p class="folio">02 · SESSIONS</p>
        <h2 class="section-title">聊天轮次</h2>
        <p class="headline" id="session-headline"></p>
        <div class="facts">
          <div class="fact">
            <span class="fact-label" id="session-average-label">平均每轮</span>
            <span class="fact-value" id="session-average"></span>
          </div>
          <div class="fact">
            <span class="fact-label" id="session-longest-label">最长的一轮</span>
            <span class="fact-value" id="session-longest"></span>
          </div>
        </div>
      </section>

      <section class="section" id="rhythm">
        <p class="folio">03 · RHYTHM</p>
        <h2 class="section-title">聊天节奏</h2>
        <div class="rhythm-rows">
          <div class="rhythm-row">
            <span class="rhythm-label" id="rhythm-hour-label">一天中最热闹的时候</span>
            <span class="rhythm-value" id="rhythm-hour-value"></span>
          </div>
          <div class="rhythm-row">
            <span class="rhythm-label" id="rhythm-weekday-label">你们最常聊天的一天</span>
            <span class="rhythm-value" id="rhythm-weekday-value"></span>
          </div>
        </div>
      </section>

      <section class="section" id="language">
        <p class="folio">04 · VOICES</p>
        <h2 class="section-title" id="language-heading">语言印记</h2>
        <p class="fallback" id="language-fallback" hidden></p>
        <div class="word-cloud" id="language-words" hidden></div>
        <div class="private-voices" id="language-private" hidden>
          <div class="voice">
            <h3 id="self-heading"></h3>
            <div class="voice-words" id="self-words"></div>
          </div>
          <div class="voice">
            <h3 id="peer-heading"></h3>
            <div class="voice-words" id="peer-words"></div>
          </div>
        </div>
      </section>

      <section class="section" id="expressions">
        <p class="folio">05 · EXPRESSIONS</p>
        <h2 class="section-title" id="expression-heading">表达文化</h2>
        <p class="fallback" id="expression-fallback" hidden></p>
        <div class="combo-list" id="expression-combos" hidden></div>
      </section>
    </div>

    <section class="empty-state" id="empty-state" hidden>
      <p class="empty-line" id="empty-message"></p>
    </section>

    <footer class="footer">
      <p class="footer-line" id="footer-line">每一句聊天，都会留下余音。</p>
      <p class="footer-brand" id="footer-brand">Echo · 本地生成</p>
    </footer>
  </main>

  <script>
window.__SHARE_DATA__ = __SHARE_DATA__;
  </script>
  <script>__SHARE_APP_JS__</script>
</body>
</html>
"""


SHARE_CARD_CSS = r"""
:root {
  --paper: #f3efe6;
  --paper-light: #faf7f0;
  --ink: #292720;
  --muted: #716b61;
  --faint: #aaa398;
  --rule: #d2cabd;
  --accent: #9b5b45;
  --accent-soft: #dfc6b8;
  --viewer: #527066;
  --serif: "Noto Serif SC", "Source Han Serif SC", "Songti SC", SimSun, serif;
  --sans: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
  --emoji: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif;
}

* { box-sizing: border-box; }
html, body { width: 1200px; height: 2000px; margin: 0; }
body {
  color: var(--ink);
  background: var(--paper);
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased;
}

.card {
  width: 1200px;
  height: 2000px;
  padding: 78px 92px 66px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background:
    linear-gradient(rgb(83 71 58 / 3%) 1px, transparent 1px) 0 0 / 100% 64px,
    var(--paper);
}

.brand-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--rule);
}
.brand {
  color: var(--accent);
  font: 600 17px/1 var(--sans);
  letter-spacing: .44em;
}
.edition {
  color: var(--faint);
  font: 500 11px/1 var(--sans);
  letter-spacing: .22em;
}

.subtitle {
  margin: 64px 0 0;
  font: 500 58px/1.18 var(--serif);
  letter-spacing: .02em;
}
.conversation {
  display: flex;
  align-items: baseline;
  gap: 26px;
  margin-top: 44px;
}
.conversation-label {
  color: var(--accent);
  font: 600 13px/1 var(--sans);
  letter-spacing: .28em;
}
.conversation-name {
  margin: 0;
  font: 400 38px/1.2 var(--serif);
  color: var(--ink);
}

#sections { display: flex; flex: 1; flex-direction: column; margin-top: 34px; }
.section { margin-top: 52px; }
.folio {
  margin: 0 0 14px;
  color: var(--accent);
  font: 600 12px/1 var(--sans);
  letter-spacing: .28em;
}
.section-title {
  margin: 0;
  font: 500 40px/1.2 var(--serif);
  letter-spacing: .01em;
}

.hero-figure {
  display: flex;
  align-items: baseline;
  gap: 26px;
  margin-top: 34px;
  border-top: 1px solid var(--ink);
}
.hero-number {
  margin-top: 18px;
  font: 300 148px/1 var(--serif);
  letter-spacing: -.01em;
  color: var(--ink);
}
.hero-unit {
  color: var(--muted);
  font: 500 18px/1 var(--sans);
  letter-spacing: .12em;
}
.hero-span {
  margin: 30px 0 0;
  color: var(--muted);
  font: 18px/1.7 var(--serif);
}
.hero-span strong {
  color: var(--ink);
  font-weight: 500;
  font-family: var(--serif);
}

.headline {
  margin: 34px 0 0;
  font: 400 30px/1.5 var(--serif);
}
.facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 72px;
  margin-top: 36px;
  border-top: 1px solid var(--rule);
}
.fact {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 24px;
}
.fact-label {
  color: var(--muted);
  font: 600 12px/1 var(--sans);
  letter-spacing: .2em;
}
.fact-value {
  color: var(--ink);
  font: 400 30px/1.3 var(--serif);
}

.rhythm-rows {
  margin-top: 34px;
  border-top: 1px solid var(--rule);
}
.rhythm-row {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  align-items: baseline;
  gap: 48px;
  padding: 26px 0;
  border-bottom: 1px solid var(--rule);
}
.rhythm-label {
  color: var(--muted);
  font: 600 13px/1.4 var(--sans);
  letter-spacing: .16em;
}
.rhythm-value {
  color: var(--ink);
  font: 400 34px/1.2 var(--serif);
}

.fallback {
  margin: 28px 0 0;
  color: var(--muted);
  font: 17px/1.9 var(--serif);
}
.word-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 34px;
}
.word-chip {
  padding: 15px 26px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  color: var(--ink);
  background: var(--paper-light);
  font: 400 24px/1.2 var(--serif);
}

.private-voices {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 64px;
  margin-top: 34px;
}
.voice { border-top: 1px solid var(--ink); padding-top: 22px; }
.voice h3 {
  margin: 0;
  color: var(--viewer);
  font: 600 14px/1.4 var(--sans);
  letter-spacing: .18em;
}
.voice-words {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 20px;
}
.voice-words .word-chip {
  padding: 12px 20px;
  font-size: 21px;
}

.combo-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
  margin-top: 34px;
}
.combo-row {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 18px 0;
  border-top: 1px solid var(--rule);
  font-family: var(--serif);
}
.combo-part {
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  color: var(--ink);
  font: 400 28px/1.2 var(--serif);
}
.combo-part img {
  width: 42px;
  height: 42px;
  object-fit: contain;
}
.combo-plus {
  color: var(--accent);
  font: 300 26px/1 var(--serif);
}
.combo-count {
  margin-left: auto;
  color: var(--faint);
  font: 500 12px/1 var(--sans);
  letter-spacing: .1em;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.empty-line {
  max-width: 560px;
  margin: 0;
  color: var(--muted);
  font: 400 28px/1.8 var(--serif);
  text-align: center;
}

.footer {
  margin-top: 34px;
  padding-top: 38px;
  border-top: 1px solid var(--rule);
  text-align: center;
}
.footer-line {
  margin: 0;
  color: var(--ink);
  font: 400 24px/1.6 var(--serif);
}
.footer-brand {
  margin: 18px 0 0;
  color: var(--faint);
  font: 600 11px/1 var(--sans);
  letter-spacing: .34em;
}
"""


SHARE_CARD_APP_JS = r"""
(function () {
  var payload = window.__SHARE_DATA__ || {};
  var data = payload.data || {};
  var assets = payload.assets || {};

  function setText(id, text) {
    var node = document.getElementById(id);
    if (node) node.textContent = text == null ? "" : String(text);
  }
  function setHidden(id, hidden) {
    var node = document.getElementById(id);
    if (node) node.hidden = Boolean(hidden);
  }

  setText("share-subtitle", data.subtitle);
  setText("conversation-label", data.conversation_label);
  setText("conversation-name", data.conversation_name);
  setText("message-count", data.message_count_display);
  setText("time-span", data.time_span_display);
  setText("footer-line", data.footer);
  setText("footer-brand", data.footer_brand);

  if (!data.has_data) {
    setText("empty-message", data.empty_message);
    setHidden("empty-state", false);
    setHidden("sections", true);
    return;
  }
  setHidden("empty-state", true);
  setHidden("sections", false);

  var sessions = data.sessions;
  if (sessions && sessions.available) {
    setHidden("sessions", false);
    setText("session-headline", sessions.headline);
    setText("session-average", sessions.average_value);
    setText("session-longest", sessions.longest_value);
    setHidden("session-average", !sessions.average_value);
    setHidden("session-longest", !sessions.longest_value);
  } else {
    setHidden("sessions", true);
  }

  var rhythm = data.rhythm;
  if (rhythm && rhythm.available) {
    setHidden("rhythm", false);
    setText("rhythm-hour-value", rhythm.hour_value);
    setText("rhythm-weekday-value", rhythm.weekday_value);
    setHidden("rhythm-hour-value", !rhythm.hour_value);
    setHidden("rhythm-weekday-value", !rhythm.weekday_value);
  } else {
    setHidden("rhythm", true);
  }

  var language = data.language;
  if (language && language.available) {
    setHidden("language", false);
    setHidden("language-fallback", true);
    if (language.self_heading) {
      setHidden("language-words", true);
      setHidden("language-private", false);
      setText("self-heading", language.self_heading);
      setText("peer-heading", language.peer_heading);
      renderWords("self-words", language.self_words);
      renderWords("peer-words", language.peer_words);
    } else {
      setHidden("language-words", false);
      setHidden("language-private", true);
      renderWords("language-words", language.words);
    }
  } else {
    setHidden("language", false);
    setText("language-fallback", language ? language.fallback : "");
    setHidden("language-fallback", false);
    setHidden("language-words", true);
    setHidden("language-private", true);
  }

  var expressions = data.expressions;
  if (expressions && expressions.available) {
    setHidden("expressions", false);
    setHidden("expression-fallback", true);
    renderCombos(expressions.combos);
  } else {
    setHidden("expressions", false);
    setText("expression-fallback", expressions ? expressions.fallback : "");
    setHidden("expression-fallback", false);
    setHidden("expression-combos", true);
  }

  function renderWords(containerId, words) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.textContent = "";
    (words || []).forEach(function (word) {
      var chip = document.createElement("span");
      chip.className = "word-chip";
      chip.textContent = word;
      container.appendChild(chip);
    });
  }

  function comboPart(combo, slot) {
    var span = document.createElement("span");
    span.className = "combo-part";
    var key = slot === "primary" ? combo.primary_asset_key : combo.secondary_asset_key;
    var text = slot === "primary" ? combo.primary_text : combo.secondary_text;
    if (key && assets[key]) {
      var img = document.createElement("img");
      img.src = assets[key];
      img.alt = "";
      span.appendChild(img);
    } else if (text) {
      span.textContent = text;
    }
    return span;
  }

  function renderCombos(combos) {
    var list = document.getElementById("expression-combos");
    if (!list) return;
    list.textContent = "";
    setHidden("expression-combos", false);
    (combos || []).forEach(function (combo) {
      var row = document.createElement("div");
      row.className = "combo-row";
      row.appendChild(comboPart(combo, "primary"));
      var hasSecondary =
        (combo.secondary_text) ||
        (combo.secondary_asset_key && assets[combo.secondary_asset_key]);
      if (hasSecondary) {
        var plus = document.createElement("span");
        plus.className = "combo-plus";
        plus.textContent = "+";
        row.appendChild(plus);
        row.appendChild(comboPart(combo, "secondary"));
      }
      if (combo.count != null) {
        var count = document.createElement("span");
        count.className = "combo-count";
        count.textContent = formatCount(combo.count) + " 次";
        row.appendChild(count);
      }
      list.appendChild(row);
    });
  }

  function formatCount(value) {
    var number = Number(value || 0);
    return number.toLocaleString("zh-CN");
  }
})();
"""


def build_share_card_html(
    data: ShareCardData,
    assets: dict[str, str] | None = None,
) -> str:
    """Return a self-contained share-card HTML document for screenshotting."""
    payload = json.dumps(
        {
            "data": asdict(data),
            "assets": assets or {},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    encoded_payload = (
        payload.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return (
        SHARE_CARD_HTML_SKELETON.replace("__SHARE_CSS__", SHARE_CARD_CSS)
        .replace("__SHARE_DATA__", encoded_payload)
        .replace("__SHARE_APP_JS__", SHARE_CARD_APP_JS)
    )


__all__ = [
    "SHARE_CARD_APP_JS",
    "SHARE_CARD_CSS",
    "SHARE_CARD_HTML_SKELETON",
    "SHARE_IMAGE_HEIGHT",
    "SHARE_IMAGE_WIDTH",
    "build_share_card_html",
]
