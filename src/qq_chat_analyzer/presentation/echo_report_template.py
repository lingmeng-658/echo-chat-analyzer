"""Static templates for the self-contained Echo Report HTML output."""

from __future__ import annotations


ECHO_REPORT_HTML_SKELETON = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>余音 Echo · 聊天记忆报告</title>
  __ECHO_FAVICON_TAG__
  <style>
__ECHO_CSS__
  </style>
</head>
<body>
  <main class="report" aria-label="余音 Echo 聊天记忆报告">
    <section class="page cover" id="cover" aria-labelledby="cover-title">
      <div class="staff-lines" aria-hidden="true"></div>
      <header class="cover-brand">
        __ECHO_LOGO_TAG__
        <span class="edition">REPORT · 001</span>
      </header>

      <div class="cover-center">
        <p class="overline">聊天记忆报告</p>
        <h1 id="cover-title"></h1>
        <p class="cover-range" id="cover-range"></p>
        <p class="cover-note">重新阅读一段交流留下的痕迹。</p>
      </div>

      <footer class="cover-footer">
        <span>本地生成</span>
        <a href="#contents">开始阅读 <span aria-hidden="true">↓</span></a>
      </footer>
    </section>

    <section class="page contents" id="contents" aria-labelledby="contents-title">
      <header class="page-header">
        <p class="folio">CONTENTS</p>
        <h2 id="contents-title">目录</h2>
        <p>沿着时间与成员，重新看见这段交流。</p>
      </header>

      <nav class="toc" aria-label="报告目录">
        <a class="toc-row" href="#overview">
          <span class="toc-number">01</span>
          <span class="toc-copy"><strong>会话概览</strong><small>这段交流的基本轮廓</small></span>
          <span class="toc-leader" aria-hidden="true"></span>
          <span class="toc-page">03</span>
        </a>
        <a class="toc-row" href="#rhythm">
          <span class="toc-number">02</span>
          <span class="toc-copy"><strong>节奏：活跃轨迹</strong><small>消息在时间中的落点</small></span>
          <span class="toc-leader" aria-hidden="true"></span>
          <span class="toc-page">04</span>
        </a>
        <a class="toc-row" href="#voices">
          <span class="toc-number">03</span>
          <span class="toc-copy"><strong>声音：成员画像</strong><small>每位成员留下的表达痕迹</small></span>
          <span class="toc-leader" aria-hidden="true"></span>
          <span class="toc-page">05</span>
        </a>
        <div class="toc-row is-future">
          <span class="toc-number">04</span>
          <span class="toc-copy"><strong>表达文化</strong><small>未来章节</small></span>
          <span class="toc-leader" aria-hidden="true"></span>
          <span class="toc-page">—</span>
        </div>
        <div class="toc-row is-future">
          <span class="toc-number">05</span>
          <span class="toc-copy"><strong>互动关系</strong><small>未来章节</small></span>
          <span class="toc-leader" aria-hidden="true"></span>
          <span class="toc-page">—</span>
        </div>
        <div class="toc-row is-future">
          <span class="toc-number">06</span>
          <span class="toc-copy"><strong>AI 尾声</strong><small>未来章节</small></span>
          <span class="toc-leader" aria-hidden="true"></span>
          <span class="toc-page">—</span>
        </div>
      </nav>
      <span class="page-number">02</span>
    </section>

    <section class="page chapter" id="overview" aria-labelledby="overview-title">
      <header class="chapter-header">
        <span class="chapter-number">01</span>
        <div><p class="folio">OVERVIEW</p><h2 id="overview-title">会话概览</h2></div>
      </header>
      <p class="chapter-intro" id="overview-intro">一段交流的轮廓，从时间、消息与参与者开始。</p>

      <div class="overview-ledger">
        <div class="primary-figure">
          <span class="field-label">消息数量</span>
          <strong id="overview-message-count"></strong>
          <span class="field-unit">条消息</span>
        </div>
        <dl class="archive-fields">
          <div><dt>时间跨度</dt><dd id="overview-time-span"></dd><small>报告覆盖的时间范围</small></div>
          <div><dt>参与人数</dt><dd id="overview-participants"></dd><small>在这段会话中留下消息</small></div>
          <div class="wide"><dt>最活跃时间</dt><dd id="busiest-hour"></dd><small>一天中消息最集中的时段</small></div>
        </dl>
      </div>
      <span class="page-number">03</span>
    </section>

    <section class="page chapter" id="rhythm" aria-labelledby="rhythm-title">
      <header class="chapter-header">
        <span class="chapter-number">02</span>
        <div><p class="folio">RHYTHM</p><h2 id="rhythm-title">节奏</h2></div>
      </header>
      <p class="chapter-intro">消息在一天与一周中的分布，形成这段交流的时间纹理。</p>

      <figure class="figure-block">
        <figcaption><h3>一天中的活跃轨迹</h3><p>每一格代表一个小时，深浅仅表示消息数量。</p></figcaption>
        <div class="hourly-track" role="img" aria-label="全天二十四小时活跃分布">
          <div class="staff-grid" aria-hidden="true"></div>
          <div class="hour-bars" id="hour-bars" aria-hidden="true"></div>
          <div class="hour-labels"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>
        </div>
      </figure>

      <figure class="figure-block weekday-figure">
        <figcaption><h3>一周中的活跃轨迹</h3><p>星期顺序保持不变，便于阅读时间节奏。</p></figcaption>
        <div class="weekday-tracks" id="weekday-tracks" role="img" aria-label="星期一到星期日活跃分布"></div>
      </figure>
      <span class="page-number">04</span>
    </section>

    <section class="page chapter" id="voices" aria-labelledby="voices-title">
      <header class="chapter-header">
        <span class="chapter-number">03</span>
        <div><p class="folio">VOICES</p><h2 id="voices-title">声音</h2></div>
      </header>
      <p class="chapter-intro">每个人以不同的频率与时间参与其中，留下各自的表达痕迹。</p>

      <div class="member-list" id="member-list"></div>
      <span class="page-number">05</span>
    </section>

    <section class="page future" id="future" aria-labelledby="future-title">
      <header class="page-header"><p class="folio">UNWRITTEN</p><h2 id="future-title">尚未展开的部分</h2><p>有些痕迹，将在之后的章节中继续被看见。</p></header>
      <div class="future-list">
        <div><span>04</span><h3>表达文化</h3><p>群体中逐渐形成的共同表达。</p></div>
        <div><span>05</span><h3>互动关系</h3><p>交流方向与回应方式。</p></div>
        <div><span>06</span><h3>AI 尾声</h3><p>基于报告内容形成的回望。</p></div>
      </div>
      <footer class="end-mark"><a href="#cover">回到封面 ↑</a><span>余音 Echo · <b data-current-year>2026</b></span></footer>
      <span class="page-number">06</span>
    </section>
  </main>
  <script>
window.ECHO_DATA = __ECHO_DATA__;
  </script>
  <script>
__ECHO_APP_JS__
  </script>
</body>
</html>

"""


ECHO_REPORT_CSS = r"""
:root {
  --paper: #f3efe6;
  --paper-light: #faf7f0;
  --canvas: #d8d2c8;
  --ink: #292720;
  --muted: #716b61;
  --faint: #aaa398;
  --rule: #d2cabd;
  --accent: #9b5b45;
  --accent-soft: #dfc6b8;
  --viewer: #527066;
  --viewer-soft: #e2ebe5;
  --serif: "Noto Serif SC", "Source Han Serif SC", "Songti SC", SimSun, serif;
  --sans: "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; color: var(--ink); background: var(--canvas); font-family: var(--sans); }
a { color: inherit; text-decoration: none; }

.report { width: min(100% - 32px, 1040px); margin: 32px auto 80px; }
.page { position: relative; min-height: 980px; margin-bottom: 28px; padding: clamp(48px, 8vw, 92px); overflow: hidden; background: var(--paper); box-shadow: 0 14px 44px rgb(53 45 36 / 10%); }
.page-number { position: absolute; right: 42px; bottom: 32px; color: var(--faint); font: 12px/1 var(--serif); letter-spacing: .16em; }
.folio, .overline { margin: 0 0 12px; color: var(--accent); font: 600 11px/1.4 var(--sans); letter-spacing: .2em; text-transform: uppercase; }
h1, h2, h3, dd, strong { font-family: var(--serif); }
h1, h2, h3, p { margin-top: 0; }

.cover { display: flex; min-height: calc(100vh - 64px); flex-direction: column; justify-content: space-between; background: var(--paper-light); }
.cover-brand, .cover-footer { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; color: var(--muted); font-size: 12px; letter-spacing: .12em; }
.brand-logo { display: block; height: 34px; width: auto; }
.brand-name { color: var(--ink); font-family: var(--serif); font-size: 17px; letter-spacing: .08em; }
.cover-center { position: relative; z-index: 1; width: min(100%, 700px); margin: auto 0; padding: 10vh 0 7vh; }
.cover h1 { max-width: 780px; margin: 18px 0 22px; font-size: clamp(46px, 8vw, 86px); font-weight: 500; line-height: 1.14; letter-spacing: -.035em; }
.cover-range { color: var(--muted); font: 14px/1.7 var(--serif); letter-spacing: .1em; }
.cover-note { max-width: 360px; margin-top: 58px; color: var(--muted); font: 18px/1.9 var(--serif); }
.cover-footer a { padding-bottom: 5px; border-bottom: 1px solid var(--accent); color: var(--accent); }
.staff-lines { position: absolute; top: 38%; right: -12%; width: 76%; height: 92px; opacity: .62; background: repeating-linear-gradient(to bottom, transparent 0 17px, var(--rule) 17px 18px); transform: rotate(-2deg); }

.page-header { max-width: 620px; padding-bottom: 34px; border-bottom: 1px solid var(--rule); }
.page-header h2, .chapter-header h2 { margin: 0; font-size: clamp(36px, 6vw, 60px); font-weight: 500; line-height: 1.2; }
.page-header > p:last-child { margin: 22px 0 0; color: var(--muted); line-height: 1.8; }
.toc { margin-top: 64px; }
.toc-row { display: grid; grid-template-columns: 44px minmax(180px, auto) 1fr 30px; gap: 18px; align-items: end; padding: 18px 0; border-bottom: 1px solid rgb(210 202 189 / 55%); }
.toc-number { color: var(--accent); font: 15px/1 var(--serif); }
.toc-copy { display: flex; flex-direction: column; gap: 6px; }
.toc-copy strong { font-size: 20px; font-weight: 500; }
.toc-copy small { color: var(--muted); font-size: 12px; }
.toc-leader { height: 1px; margin-bottom: 5px; background-image: radial-gradient(circle, var(--faint) 1px, transparent 1px); background-position: bottom; background-size: 6px 2px; background-repeat: repeat-x; }
.toc-page { color: var(--muted); font: 12px/1 var(--serif); text-align: right; }
.is-future { color: var(--faint); }
.is-future .toc-number, .is-future .toc-copy small { color: var(--faint); }

.chapter-header { display: flex; gap: 26px; align-items: flex-start; padding-bottom: 24px; border-bottom: 1px solid var(--rule); }
.chapter-number { padding-top: 9px; color: var(--accent); font: 16px/1 var(--serif); letter-spacing: .08em; }
.chapter-intro { max-width: 540px; margin: 32px 0 62px; color: var(--muted); font: 17px/2 var(--serif); }
.overview-ledger { border-top: 1px solid var(--ink); border-bottom: 1px solid var(--ink); }
.primary-figure { display: grid; grid-template-columns: 1fr auto; align-items: end; min-height: 250px; padding: 42px 0; border-bottom: 1px solid var(--rule); }
.primary-figure strong { font-size: clamp(72px, 13vw, 132px); font-weight: 400; line-height: .9; letter-spacing: -.06em; }
.field-label, .field-unit { color: var(--muted); font-size: 13px; letter-spacing: .08em; }
.field-unit { grid-column: 2; margin-top: 14px; text-align: right; }
.archive-fields { display: grid; grid-template-columns: 1fr 1fr; margin: 0; }
.archive-fields div { min-height: 150px; padding: 28px 0; }
.archive-fields div:nth-child(odd) { padding-right: 34px; border-right: 1px solid var(--rule); }
.archive-fields div:nth-child(even) { padding-left: 34px; }
.archive-fields .wide { grid-column: 1 / -1; padding-right: 0; border-top: 1px solid var(--rule); border-right: 0; }
.archive-fields dt, .member-entry dt { color: var(--muted); font-size: 12px; letter-spacing: .08em; }
.archive-fields dd { margin: 18px 0 7px; font-size: 29px; }
.archive-fields small { color: var(--faint); }

.figure-block { margin: 0 0 72px; }
.figure-block figcaption { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
.figure-block h3 { margin: 0; font-size: 21px; font-weight: 500; }
.figure-block figcaption p { margin: 0; color: var(--muted); font-size: 12px; }
.hourly-track { position: relative; height: 230px; padding: 24px 0 28px; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
.staff-grid { position: absolute; inset: 28px 0 40px; background: repeating-linear-gradient(to bottom, transparent 0 31px, rgb(210 202 189 / 72%) 31px 32px); }
.hour-bars { position: absolute; inset: 30px 0 41px; display: grid; grid-template-columns: repeat(24, 1fr); gap: clamp(3px, .8vw, 8px); align-items: end; }
.hour-bars i { height: calc(var(--v) * 1%); min-height: 3px; background: var(--accent-soft); border-radius: 1px 1px 0 0; }
.hour-bars i.peak { background: var(--accent); }
.hour-labels { position: absolute; right: 0; bottom: 11px; left: 0; display: flex; justify-content: space-between; color: var(--muted); font: 10px/1 var(--sans); }
.weekday-tracks { padding: 6px 0; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
.weekday-tracks > div { display: grid; grid-template-columns: 48px 1fr 36px; gap: 18px; align-items: center; min-height: 46px; border-bottom: 1px solid rgb(210 202 189 / 55%); }
.weekday-tracks > div:last-child { border-bottom: 0; }
.weekday-tracks span, .weekday-tracks em { color: var(--muted); font-size: 12px; font-style: normal; }
.weekday-tracks em { text-align: right; }
.weekday-tracks b { position: relative; height: 5px; background: #e5ded2; }
.weekday-tracks i { position: absolute; inset: 0 auto 0 0; width: var(--v); background: var(--accent); }

.member-list { border-top: 1px solid var(--ink); }
.member-entry { position: relative; padding: 34px 0 38px; border-bottom: 1px solid var(--rule); }
.member-entry.is-viewer { margin: 0 -22px; padding-right: 22px; padding-left: 22px; background: linear-gradient(90deg, var(--viewer-soft) 0 5px, rgb(226 235 229 / 42%) 5px, transparent 70%); }
.member-entry header { display: flex; align-items: flex-start; gap: 18px; }
.member-entry h3 { margin: 0 0 6px; font-size: 25px; font-weight: 500; }
.member-entry header p { margin: 0; color: var(--faint); font-size: 11px; }
.member-index { color: var(--accent); font: 13px/1.8 var(--serif); }
.viewer-mark { margin-left: auto; padding: 5px 10px; color: var(--viewer); border: 1px solid #adc0b7; border-radius: 99px; font-size: 11px; }
.member-entry dl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 28px; margin: 30px 0 26px 40px; }
.member-entry dd { margin: 10px 0 0; font-size: 20px; }
.member-rhythm { position: relative; height: 20px; margin-left: 40px; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); background: repeating-linear-gradient(90deg, transparent 0 calc(4.166% - 1px), rgb(210 202 189 / 45%) calc(4.166% - 1px) 4.166%); }
.member-rhythm i { position: absolute; top: 5px; left: var(--start); width: var(--width); height: 8px; background: var(--accent-soft); }
.is-viewer .member-rhythm i { background: var(--viewer); }

.future { display: flex; flex-direction: column; }
.future-list { margin-top: 64px; border-top: 1px solid var(--rule); }
.future-list > div { display: grid; grid-template-columns: 54px 180px 1fr; gap: 24px; align-items: baseline; padding: 28px 0; color: var(--faint); border-bottom: 1px solid var(--rule); }
.future-list span { font: 14px/1 var(--serif); }
.future-list h3 { margin: 0; color: var(--muted); font-size: 20px; font-weight: 500; }
.future-list p { margin: 0; font-size: 13px; }
.end-mark { display: flex; justify-content: space-between; margin-top: auto; padding-top: 80px; color: var(--muted); font-size: 12px; }
.end-mark::before { position: absolute; right: 0; bottom: 112px; left: 0; height: 1px; content: ""; background: linear-gradient(90deg, var(--accent), transparent 76%); }
.end-mark b { font-weight: 400; }

@media (max-width: 720px) {
  .report { width: 100%; margin: 0; }
  .page { min-height: auto; margin: 0; padding: 48px 22px 72px; box-shadow: none; }
  .cover { min-height: 100vh; }
  .toc-row { grid-template-columns: 34px minmax(0, 1fr) 22px; }
  .toc-leader { display: none; }
  .figure-block figcaption { display: block; }
  .figure-block figcaption p { margin-top: 9px; }
  .primary-figure { display: block; }
  .primary-figure strong { display: block; margin-top: 50px; }
  .field-unit { display: block; text-align: left; }
  .archive-fields { grid-template-columns: 1fr; }
  .archive-fields div, .archive-fields div:nth-child(odd), .archive-fields div:nth-child(even) { padding: 24px 0; border-right: 0; border-bottom: 1px solid var(--rule); }
  .archive-fields .wide { grid-column: auto; }
  .member-entry dl { grid-template-columns: 1fr 1fr; margin-left: 0; }
  .member-rhythm { margin-left: 0; }
  .future-list > div { grid-template-columns: 34px 1fr; }
  .future-list p { grid-column: 2; }
  .page-number { right: 22px; }
}

@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }

@media print {
  body { background: #fff; }
  .report { width: auto; margin: 0; }
  .page { min-height: 100vh; margin: 0; box-shadow: none; break-after: page; }
  .cover-footer a, .end-mark a { display: none; }
}

"""


ECHO_REPORT_APP_JS = r"""
"use strict";

document.documentElement.classList.add("js-ready");

(function () {
  "use strict";

  var data = window.ECHO_DATA || null;
  var overview = data && data.overview ? data.overview : null;
  var conversation = data && data.conversation ? data.conversation : null;
  var hasData = Boolean(overview && overview.has_data);
  var emptyDescription =
    overview && overview.empty_description ? overview.empty_description : "";

  function setText(id, value) {
    var node = document.getElementById(id);
    if (node) {
      node.textContent = value;
    }
  }

  function formatCount(value) {
    return String(Number(value) || 0).replace(
      /\B(?=(\d{3})+(?!\d))/g,
      ","
    );
  }

  function formatPercent(value) {
    return (Number(value) || 0).toFixed(1) + "%";
  }

  function formatAverage(value) {
    return (Number(value) || 0).toFixed(1);
  }

  document.querySelectorAll("[data-current-year]").forEach(function (element) {
    element.textContent = String(new Date().getFullYear());
  });

  var title =
    (data && data.title) ||
    (conversation && conversation.name) ||
    "余音 Echo · 聊天记忆报告";
  setText("cover-title", title);
  if (data && data.title) {
    document.title = data.title + " · 余音 Echo";
  }

  var timeSpan =
    conversation && conversation.time_span ? conversation.time_span : "";
  var coverRange = document.getElementById("cover-range");
  if (coverRange) {
    coverRange.textContent = timeSpan ? timeSpan : "本地生成";
    coverRange.hidden = !timeSpan;
  }

  if (overview) {
    setText(
      "overview-message-count",
      hasData ? formatCount(overview.total_message_count) : "—"
    );
    setText("overview-time-span", timeSpan ? timeSpan : "—");
    setText(
      "overview-participants",
      hasData ? formatCount(overview.participant_count) + " 人" : "—"
    );
    if (!hasData && emptyDescription) {
      setText("overview-intro", emptyDescription);
    }
  }

  var hourly = (data && data.activity && data.activity.hourly) || [];
  var busiestBlock = document.getElementById("busiest-hour");
  if (busiestBlock) {
    var peak = null;
    hourly.forEach(function (point) {
      if (!peak || Number(point.value) > Number(peak.value)) {
        peak = point;
      }
    });
    if (hasData && peak && peak.label) {
      busiestBlock.textContent = peak.label;
      busiestBlock.hidden = false;
    } else {
      busiestBlock.hidden = true;
    }
  }

  var hourBars = document.getElementById("hour-bars");
  if (hourBars) {
    hourBars.textContent = "";
    if (hasData && hourly.length) {
      var maxHour = 0;
      hourly.forEach(function (point) {
        maxHour = Math.max(maxHour, Number(point.value) || 0);
      });
      hourly.forEach(function (point) {
        var value = Number(point.value) || 0;
        var bar = document.createElement("i");
        bar.style.setProperty(
          "--v",
          String(maxHour > 0 ? Math.round((value / maxHour) * 100) : 0)
        );
        if (maxHour > 0 && value === maxHour) {
          bar.className = "peak";
        }
        hourBars.appendChild(bar);
      });
    }
  }

  var weekdayTracks = document.getElementById("weekday-tracks");
  var weekday = (data && data.activity && data.activity.weekday) || [];
  if (weekdayTracks) {
    weekdayTracks.textContent = "";
    if (hasData && weekday.length) {
      var maxWeekday = 0;
      weekday.forEach(function (point) {
        maxWeekday = Math.max(maxWeekday, Number(point.value) || 0);
      });
      weekday.forEach(function (point) {
        var value = Number(point.value) || 0;
        var row = document.createElement("div");
        var label = document.createElement("span");
        label.textContent = point.label;
        var track = document.createElement("b");
        var fill = document.createElement("i");
        fill.style.setProperty(
          "--v",
          String(maxWeekday > 0 ? Math.round((value / maxWeekday) * 100) : 0) + "%"
        );
        track.appendChild(fill);
        var count = document.createElement("em");
        count.textContent = formatCount(value);
        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(count);
        weekdayTracks.appendChild(row);
      });
    }
  }

  var memberList = document.getElementById("member-list");
  var members = (data && data.members) || [];
  if (memberList) {
    memberList.textContent = "";
    members.forEach(function (member, index) {
      var article = document.createElement("article");
      article.className =
        "member-entry" + (member.is_viewer ? " is-viewer" : "");

      var header = document.createElement("header");
      var number = document.createElement("span");
      number.className = "member-index";
      number.textContent =
        index < 9 ? "0" + String(index + 1) : String(index + 1);
      var nameBlock = document.createElement("div");
      var name = document.createElement("h3");
      name.textContent = member.display_name || "成员";
      var subtitle = document.createElement("p");
      subtitle.textContent = member.speaker_key || "成员标识";
      nameBlock.appendChild(name);
      nameBlock.appendChild(subtitle);
      header.appendChild(number);
      header.appendChild(nameBlock);
      if (member.is_viewer) {
        var mark = document.createElement("span");
        mark.className = "viewer-mark";
        mark.textContent = "这是你";
        header.appendChild(mark);
      }
      article.appendChild(header);

      var dl = document.createElement("dl");
      var fields = [
        ["消息数量", formatCount(member.message_count)],
        ["占比", formatPercent(member.message_share_percent)],
        ["平均长度", formatAverage(member.average_length)],
        ["活跃时间", member.active_period || "—"]
      ];
      fields.forEach(function (field) {
        var div = document.createElement("div");
        var dt = document.createElement("dt");
        dt.textContent = field[0];
        var dd = document.createElement("dd");
        dd.textContent = field[1];
        div.appendChild(dt);
        div.appendChild(dd);
        dl.appendChild(div);
      });
      article.appendChild(dl);

      var rhythm = document.createElement("div");
      rhythm.className = "member-rhythm";
      var memberHourly = (member.activity && member.activity.hourly) || [];
      var activeIndexes = [];
      memberHourly.forEach(function (point, pointIndex) {
        if (Number(point.value) > 0) {
          activeIndexes.push(pointIndex);
        }
      });
      if (activeIndexes.length && memberHourly.length === 24) {
        var startIndex = activeIndexes[0];
        var endIndex = activeIndexes[activeIndexes.length - 1];
        var segment = document.createElement("i");
        segment.style.setProperty(
          "--start",
          ((startIndex / 24) * 100).toFixed(1) + "%"
        );
        segment.style.setProperty(
          "--width",
          (((endIndex - startIndex + 1) / 24) * 100).toFixed(1) + "%"
        );
        rhythm.appendChild(segment);
      }
      article.appendChild(rhythm);

      memberList.appendChild(article);
    });

    if (hasData && !members.length) {
      var note = document.createElement("p");
      note.className = "chapter-intro";
      note.textContent =
        emptyDescription || "没有可展示的成员数据。";
      memberList.appendChild(note);
    }
  }
})();

"""
