/**
 * trends.js — 흐름 페이지. data/index.json 하나로 모든 차트를 그린다 (라이브러리 없음).
 *  - 기간(30/90/180/365일) × 직전 같은 길이 기간 비교
 *  - 주간 수집량(누적 막대), 섹션별 주제 비중(%p 변화), 주체 랭킹·타임라인, 출처, 헤드라인 연표
 */
(function () {
  'use strict';

  var ROOT = (window.DI && window.DI.ROOT) || '';
  var esc  = (window.DI && window.DI.escapeHtml) || function (s) { return String(s); };
  var SECS = ['edu', 'paper', 'tech'];
  var SEC_SHORT = { edu: '교육', paper: '논문', tech: '기술' };
  var SEC_LABEL = { edu: '교육 뉴스', paper: '연구 논문', tech: '기술 뉴스' };

  var index = null;
  var rangeDays = 90;

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.tr-range').forEach(function (b) {
      b.addEventListener('click', function () {
        rangeDays = parseInt(b.getAttribute('data-days'), 10) || 90;
        document.querySelectorAll('.tr-range').forEach(function (x) { x.classList.toggle('active', x === b); });
        if (index) renderAll();
      });
    });
    fetch(ROOT + 'data/index.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (data) { index = data; renderAll(); })
      .catch(function (err) {
        console.warn('[trends] index.json 로드 실패:', err);
        var v = document.getElementById('tr-volume');
        if (v) v.innerHTML = '<p class="page-loading">집계 데이터를 불러오지 못했습니다.</p>';
      });
  });

  /* ── 날짜 유틸 ─────────────────────────────── */
  function toDate(s) { var p = s.split('-'); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function addDays(s, n) { var d = toDate(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); }
  function fmt(s) { var p = s.split('-'); return parseInt(p[1], 10) + '/' + parseInt(p[2], 10); }
  function fmtLong(s) { var p = s.split('-'); return p[0] + '.' + p[1] + '.' + p[2]; }
  function weekKey(s) { // 월요일 시작 주의 첫날
    var d = toDate(s); var wd = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - wd); return iso(d);
  }

  function windowDays(days, end, n) {
    var start = addDays(end, -(n - 1));
    return days.filter(function (e) { return e.d >= start && e.d <= end; });
  }

  /* ── 렌더 진입 ─────────────────────────────── */
  function renderAll() {
    var days = (index.days || []).slice().sort(function (a, b) { return a.d < b.d ? -1 : 1; });
    if (!days.length) return;
    var latest = index.latest || days[days.length - 1].d;
    var cur = windowDays(days, latest, rangeDays);
    var prevEnd = addDays(latest, -rangeDays);
    var prev = windowDays(days, prevEnd, rangeDays);
    var start = cur.length ? cur[0].d : latest;

    var period = document.getElementById('tr-period');
    if (period) period.textContent = fmtLong(start) + ' ~ ' + fmtLong(latest) + ' · ' + cur.length + '일 (비교: ' + prev.length + '일)';

    renderStats(cur, prev);
    renderVolume(cur);
    renderShare(cur, prev);
    renderEntities(cur, prev);
    renderTimeline(cur);
    renderSources(cur);
    renderHeads(cur);
  }

  function sumN(e) { return (e.n.edu || 0) + (e.n.paper || 0) + (e.n.tech || 0); }
  function total(list) { return list.reduce(function (s, e) { return s + sumN(e); }, 0); }

  /* ── 상단 통계 ─────────────────────────────── */
  function renderStats(cur, prev) {
    var host = document.getElementById('tr-stats');
    if (!host) return;
    var t = total(cur), tp = total(prev);
    var ai = cur.reduce(function (s, e) { return s + (e.ai || 0); }, 0);
    var op = cur.reduce(function (s, e) { return s + ((e.kinds || {}).opinion || 0); }, 0);
    var edu = cur.reduce(function (s, e) { return s + (e.n.edu || 0); }, 0);
    host.innerHTML =
      stat(t.toLocaleString('ko-KR') + '건', '소식 ' + delta(t, tp, '건')) +
      stat((t ? Math.round(ai * 100 / t) : 0) + '%', 'AI 한국어 요약') +
      stat((edu ? Math.round(op * 100 / edu) : 0) + '%', '교육 뉴스 중 칼럼');
  }
  function stat(n, k) { return '<div class="stat"><span class="stat-n">' + n + '</span><span class="stat-k">' + k + '</span></div>'; }
  function delta(a, b, unit) {
    if (!b) return '';
    var d = a - b;
    return '<span class="delta ' + (d > 0 ? 'up' : d < 0 ? 'down' : 'flat') + '">' + (d > 0 ? '▲' : d < 0 ? '▼' : '') + Math.abs(d) + (unit || '') + '</span>';
  }

  /* ── 주간 수집량 ───────────────────────────── */
  function renderVolume(cur) {
    var host = document.getElementById('tr-volume');
    if (!host) return;
    var weeks = {}; var order = [];
    cur.forEach(function (e) {
      var k = weekKey(e.d);
      if (!weeks[k]) { weeks[k] = { edu: 0, paper: 0, tech: 0, days: 0 }; order.push(k); }
      SECS.forEach(function (s) { weeks[k][s] += e.n[s] || 0; });
      weeks[k].days++;
    });
    if (!order.length) { host.innerHTML = '<p class="tr-empty">데이터 없음</p>'; return; }
    var max = Math.max.apply(null, order.map(function (k) { return weeks[k].edu + weeks[k].paper + weeks[k].tech; })) || 1;
    var cols = order.map(function (k) {
      var w = weeks[k]; var tot = w.edu + w.paper + w.tech;
      var title = fmt(k) + ' 주 · ' + tot + '건 (교육 ' + w.edu + ' · 논문 ' + w.paper + ' · 기술 ' + w.tech + ', ' + w.days + '일)';
      return '<div class="vol-col" title="' + title + '" style="height:' + Math.round(tot * 100 / max) + '%">' +
        SECS.map(function (s) { return w[s] ? '<i class="b-' + s + '" style="flex:' + w[s] + '"></i>' : ''; }).join('') + '</div>';
    }).join('');
    var axis = '<div class="vol-axis"><span>' + fmt(order[0]) + '</span>' +
      (order.length > 2 ? '<span>' + fmt(order[Math.floor(order.length / 2)]) + '</span>' : '') +
      '<span>' + fmt(order[order.length - 1]) + '</span></div>';
    var legend = '<div class="legend">' + SECS.map(function (s) { return '<span><i class="dot dot-' + s + '"></i>' + SEC_LABEL[s] + '</span>'; }).join('') +
      '<span>최대 주 ' + max + '건 · 총 ' + order.length + '주</span></div>';
    host.innerHTML = '<div class="vol-chart" role="img" aria-label="주간 수집량 누적 막대">' + cols + '</div>' + axis + legend;
  }

  /* ── 주제 비중 ─────────────────────────────── */
  function topicCounts(list, sec) {
    var c = {}; var t = 0;
    list.forEach(function (e) {
      var tp = (e.topics || {})[sec] || {};
      Object.keys(tp).forEach(function (k) { c[k] = (c[k] || 0) + tp[k]; t += tp[k]; });
    });
    return { counts: c, total: t };
  }

  function renderShare(cur, prev) {
    var host = document.getElementById('tr-share');
    if (!host) return;
    var labels = index.topic_labels || {};
    var html = SECS.map(function (s) {
      var a = topicCounts(cur, s), b = topicCounts(prev, s);
      if (!a.total) return '';
      var rows = Object.keys(a.counts).map(function (k) {
        var pa = a.counts[k] * 100 / a.total;
        var pb = b.total ? (b.counts[k] || 0) * 100 / b.total : null;
        return { id: k, label: (labels[s] || {})[k] || k, n: a.counts[k], p: pa, d: pb === null ? null : pa - pb };
      }).sort(function (x, y) { return y.n - x.n; });
      var bar = rows.map(function (r, i) { return '<i class="seg-' + Math.min(i, 5) + '" style="flex:' + r.n + '" title="' + esc(r.label) + ' ' + r.n + '건 (' + r.p.toFixed(0) + '%)"></i>'; }).join('');
      var legend = rows.slice(0, 6).map(function (r, i) {
        var d = r.d === null ? '' : '<span class="delta ' + (r.d > 0.5 ? 'up' : r.d < -0.5 ? 'down' : 'flat') + '">' + (r.d > 0 ? '+' : '') + r.d.toFixed(0) + 'p</span>';
        return '<span class="topic-chip seg-' + Math.min(i, 5) + '">' + esc(r.label) + '<b>' + r.p.toFixed(0) + '%</b>' + d + '</span>';
      }).join('');
      return '<div class="share-row" data-cat="' + s + '"><div class="share-head"><span>' + SEC_LABEL[s] + '</span><small>' + a.total + '건</small></div>' +
        '<div class="share-bar" role="img" aria-label="' + SEC_LABEL[s] + ' 주제 비중">' + bar + '</div><div class="share-legend">' + legend + '</div></div>';
    }).join('');
    host.innerHTML = html || '<p class="tr-empty">데이터 없음</p>';
  }

  /* ── 주체 ──────────────────────────────────── */
  function entCounts(list) {
    var c = {};
    list.forEach(function (e) { var en = e.ents || {}; Object.keys(en).forEach(function (k) { c[k] = (c[k] || 0) + en[k]; }); });
    return c;
  }

  function renderEntities(cur, prev) {
    var host = document.getElementById('tr-ents');
    if (!host) return;
    var a = entCounts(cur), b = entCounts(prev);
    var rows = Object.keys(a).map(function (k) { return { name: k, n: a[k], d: a[k] - (b[k] || 0), isNew: !b[k] }; })
      .sort(function (x, y) { return y.n - x.n; }).slice(0, 15);
    if (!rows.length) { host.innerHTML = '<li class="tr-empty">데이터 없음</li>'; return; }
    var max = rows[0].n || 1;
    host.innerHTML = rows.map(function (r, i) {
      var d = r.isNew && prev.length ? '<span class="delta up">new</span>' : delta(r.n, r.n - r.d, '');
      return '<li><span class="rank-i">' + (i + 1) + '</span><a class="rank-name" href="entity.html?e=' + encodeURIComponent(r.name) + '">' + esc(r.name) + '</a>' +
        '<span class="rank-bar"><i style="width:' + Math.round(r.n * 100 / max) + '%"></i></span>' +
        '<span class="rank-n">' + r.n + '</span><span class="rank-d">' + d + '</span></li>';
    }).join('');
  }

  function renderTimeline(cur) {
    var host = document.getElementById('tr-timeline');
    if (!host) return;
    var totals = entCounts(cur);
    var top = Object.keys(totals).sort(function (x, y) { return totals[y] - totals[x]; }).slice(0, 8);
    if (!top.length) { host.innerHTML = '<li class="tr-empty">데이터 없음</li>'; return; }
    var weeks = {}; var order = [];
    cur.forEach(function (e) {
      var k = weekKey(e.d);
      if (!weeks[k]) { weeks[k] = {}; order.push(k); }
      var en = e.ents || {};
      top.forEach(function (name) { weeks[k][name] = (weeks[k][name] || 0) + (en[name] || 0); });
    });
    var max = 1;
    order.forEach(function (k) { top.forEach(function (n) { if (weeks[k][n] > max) max = weeks[k][n]; }); });
    host.innerHTML = top.map(function (name) {
      var bars = order.map(function (k) {
        var v = weeks[k][name] || 0;
        return '<i style="height:' + (v ? Math.max(8, Math.round(v * 100 / max)) : 3) + '%" title="' + fmt(k) + ' 주 ' + v + '건"></i>';
      }).join('');
      return '<li><a class="tl-name" href="entity.html?e=' + encodeURIComponent(name) + '">' + esc(name) + '</a><span class="spark spark-lg" role="img" aria-label="' + esc(name) + ' 주간 언급">' + bars + '</span><b class="spark-total">' + totals[name] + '</b></li>';
    }).join('');
  }

  /* ── 출처 ──────────────────────────────────── */
  function renderSources(cur) {
    var host = document.getElementById('tr-sources');
    if (!host) return;
    var c = {};
    cur.forEach(function (e) { var s = e.srcs || {}; Object.keys(s).forEach(function (k) { c[k] = (c[k] || 0) + s[k]; }); });
    var rows = Object.keys(c).map(function (k) { var i = k.indexOf(':'); return { sec: k.slice(0, i), name: k.slice(i + 1), n: c[k] }; })
      .sort(function (x, y) { return y.n - x.n; });
    // 섹션별 상위 4개씩 → 합쳐 12개
    var picked = [];
    SECS.forEach(function (s) { picked = picked.concat(rows.filter(function (r) { return r.sec === s; }).slice(0, 4)); });
    picked.sort(function (x, y) { return y.n - x.n; });
    if (!picked.length) { host.innerHTML = '<li class="tr-empty">데이터 없음</li>'; return; }
    var max = picked[0].n || 1;
    host.innerHTML = picked.map(function (r, i) {
      return '<li><span class="rank-i">' + (i + 1) + '</span><span class="rank-name">' + esc(r.name) + '<span class="sub">' + SEC_SHORT[r.sec] + '</span></span>' +
        '<span class="rank-bar ' + r.sec + '"><i style="width:' + Math.round(r.n * 100 / max) + '%"></i></span>' +
        '<span class="rank-n">' + r.n + '</span><span class="rank-d"></span></li>';
    }).join('');
  }

  /* ── 헤드라인 연표 ─────────────────────────── */
  function renderHeads(cur) {
    var host = document.getElementById('tr-heads');
    if (!host) return;
    var rows = cur.filter(function (e) { return e.head; }).sort(function (a, b) { return a.d < b.d ? 1 : -1; }).slice(0, 60);
    if (!rows.length) { host.innerHTML = '<li class="tr-empty">이 기간에는 저장된 헤드라인이 없습니다. (2026-11 이후 Gemini 종합이 켜지면 날짜별로 쌓입니다)</li>'; return; }
    var latest = index.latest;
    host.innerHTML = rows.map(function (e) {
      var href = e.d === latest ? 'index.html' : 'archive/' + e.d + '.html';
      var tag = e.head_src === 'ai' ? '<span class="src-ai">AI 종합</span>' : '';
      return '<li><span class="head-date"><a href="' + href + '">' + fmtLong(e.d) + '</a></span><span class="head-txt">' + esc(e.head) + tag + '</span></li>';
    }).join('');
  }
})();
