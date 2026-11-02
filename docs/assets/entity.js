/**
 * entity.js — 주체 페이지
 *  ?e=이름  : data/entities.json(목록) → data/entity/{slug}.json(전체 등장) 로 한 주체의 1년 흐름
 *  파라미터 없음 : 주체 목록 (종류별, 언급 많은 순)
 */
(function () {
  'use strict';

  var ROOT = (window.DI && window.DI.ROOT) || '';
  var esc  = (window.DI && window.DI.escapeHtml) || function (s) { return String(s); };
  var SECS = ['edu', 'paper', 'tech'];
  var SEC_SHORT = { edu: '교육', paper: '논문', tech: '기술' };
  var SEC_LABEL = { edu: '교육 뉴스', paper: '연구 논문', tech: '기술 뉴스' };
  var KIND_LABEL = { org: '기업·기관', model: '모델·제품', edu_org: '교육 당국', issue: '교육 이슈', tech: '기술 개념' };
  var KIND_ORDER = ['org', 'model', 'edu_org', 'issue', 'tech'];
  var PAGE = 60;

  var root = document.getElementById('ent-root');
  var name = new URLSearchParams(location.search).get('e');

  document.addEventListener('DOMContentLoaded', function () {
    fetch(ROOT + 'data/entities.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (idx) { name ? renderEntity(idx) : renderDirectory(idx); })
      .catch(function (err) {
        console.warn('[entity]', err);
        root.innerHTML = '<p class="page-loading">주체 데이터를 불러오지 못했습니다.</p>';
      });
  });

  function fmtDate(d) { return d.replace(/-/g, '.'); }
  function monthLabel(m) { return parseInt(m.slice(5), 10) + '월'; }

  /* ── 목록 ─────────────────────────────────── */
  function renderDirectory(idx) {
    document.title = 'Daily Intelligence — 주체 목록';
    var list = idx.entities || [];
    var byKind = {};
    list.forEach(function (e) { (byKind[e.kind] = byKind[e.kind] || []).push(e); });
    var html = '<div class="page-head"><div><h1 class="page-title">주체</h1>' +
      '<p class="page-sub">기업·모델·교육 당국·교육 이슈·기술 개념이 교육 뉴스·논문·기술 뉴스에 언제, 얼마나 등장했는지 봅니다. 사전에 등록된 이름을 제목과 요약에서 찾아 셉니다(' + idx.min_mentions + '회 이상).</p></div>' +
      '<div class="stat-row"><div class="stat"><span class="stat-n">' + list.length + '</span><span class="stat-k">주체</span></div></div></div>';
    KIND_ORDER.forEach(function (k) {
      var arr = byKind[k];
      if (!arr || !arr.length) return;
      var max = arr[0].n;
      html += '<section class="ent-group"><h2 class="arch-month-title">' + KIND_LABEL[k] + ' <small class="arch-month-sub">' + arr.length + '</small></h2><ol class="rank-list">';
      arr.slice(0, 40).forEach(function (e, i) {
        var last = e.months ? Object.keys(e.months).sort().pop() : '';
        html += '<li><span class="rank-i">' + (i + 1) + '</span><a class="rank-name" href="entity.html?e=' + encodeURIComponent(e.name) + '">' + esc(e.name) +
          '<span class="sub">' + SECS.map(function (s) { return e.sec[s] ? SEC_SHORT[s] + ' ' + e.sec[s] : ''; }).filter(Boolean).join(' · ') + '</span></a>' +
          '<span class="rank-bar"><i style="width:' + Math.round(e.n * 100 / max) + '%"></i></span><span class="rank-n">' + e.n + '</span>' +
          '<span class="rank-d">' + (last ? monthLabel(last) : '') + '</span></li>';
      });
      html += '</ol></section>';
    });
    root.innerHTML = html;
  }

  /* ── 한 주체 ──────────────────────────────── */
  function renderEntity(idx) {
    var meta = (idx.entities || []).filter(function (e) { return e.name === name; })[0];
    if (!meta) {
      root.innerHTML = '<div class="page-head"><div><h1 class="page-title">' + esc(name) + '</h1><p class="page-sub">이 이름은 사전에 없거나 등장이 ' + idx.min_mentions + '회 미만입니다.</p></div></div>' +
        '<p><a class="footer-link" href="entity.html">← 주체 목록</a> · <a class="footer-link" href="archive/?q=' + encodeURIComponent(name) + '">전 기간 제목 검색</a></p>';
      return;
    }
    document.title = 'Daily Intelligence — ' + name;
    fetch(ROOT + 'data/entity/' + meta.slug + '.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (ent) { draw(idx, meta, ent); })
      .catch(function (err) { console.warn('[entity]', err); root.innerHTML = '<p class="page-loading">주체 파일을 불러오지 못했습니다.</p>'; });
  }

  function draw(idx, meta, ent) {
    var months = meta.months || {};
    var keys = Object.keys(months).sort();
    // 첫 달부터 마지막 달까지 빈 달 채우기
    var filled = [];
    if (keys.length) {
      var cur = keys[0], last = keys[keys.length - 1];
      while (cur <= last) {
        filled.push({ m: cur, n: months[cur] || 0 });
        var y = parseInt(cur.slice(0, 4), 10), mo = parseInt(cur.slice(5), 10) + 1;
        if (mo > 12) { mo = 1; y++; }
        cur = y + '-' + (mo < 10 ? '0' + mo : mo);
      }
    }
    var max = Math.max.apply(null, filled.map(function (x) { return x.n; }).concat([1]));
    var recent3 = filled.slice(-3).reduce(function (s, x) { return s + x.n; }, 0);
    var prev3 = filled.slice(-6, -3).reduce(function (s, x) { return s + x.n; }, 0);

    var html = '<div class="page-head"><div>' +
      '<p class="page-kicker"><a href="entity.html">주체</a> · ' + (KIND_LABEL[meta.kind] || meta.kind) + '</p>' +
      '<h1 class="page-title">' + esc(meta.name) + '</h1>' +
      '<p class="page-sub">' + fmtDate(meta.first) + '부터 ' + fmtDate(meta.last) + '까지 ' + meta.n + '번 등장. ' +
      SECS.map(function (s) { return meta.sec[s] ? SEC_LABEL[s] + ' ' + meta.sec[s] + '건' : ''; }).filter(Boolean).join(', ') + '.</p></div>' +
      '<div class="stat-row">' +
      '<div class="stat"><span class="stat-n">' + meta.n + '</span><span class="stat-k">총 언급</span></div>' +
      '<div class="stat"><span class="stat-n">' + recent3 + '</span><span class="stat-k">최근 3개월' + delta(recent3 - prev3) + '</span></div>' +
      '<div class="stat"><span class="stat-n">' + fmtDate(meta.last) + '</span><span class="stat-k">마지막 등장</span></div>' +
      '</div></div>';

    // 월별 막대
    html += '<section class="tr-card span-2"><h2 class="tr-card-title">월별 언급 <span class="cell-hint">' + filled.length + '개월</span></h2>' +
      '<div class="vol-chart ent-chart" role="img" aria-label="월별 언급 수">' +
      filled.map(function (x) { return '<div class="vol-col" style="height:' + (x.n ? Math.max(4, Math.round(x.n * 100 / max)) : 2) + '%" title="' + x.m + ' · ' + x.n + '건"><i class="b-ink" style="flex:1"></i></div>'; }).join('') +
      '</div><div class="vol-axis">' + filled.map(function (x, i) { return (i === 0 || i === filled.length - 1 || x.m.slice(5) === '01') ? '<span>' + x.m.slice(2).replace('-', '.') + '</span>' : ''; }).join('') + '</div></section>';

    html += '<div class="tr-grid">';
    // 주제 분포
    html += '<section class="tr-card"><h2 class="tr-card-title">어떤 주제로 등장했나</h2>';
    var labels = idx.topic_labels || {};
    SECS.forEach(function (s) {
      var tp = (ent.topics || {})[s];
      if (!tp) return;
      var rows = Object.keys(tp).map(function (k) { return { id: k, n: tp[k], label: (labels[s] || {})[k] || k }; }).sort(function (a, b) { return b.n - a.n; });
      var tot = rows.reduce(function (a, r) { return a + r.n; }, 0);
      html += '<div class="share-row" data-cat="' + s + '"><div class="share-head"><span>' + SEC_LABEL[s] + '</span><small>' + tot + '건</small></div>' +
        '<div class="share-bar">' + rows.map(function (r, i) { return '<i class="seg-' + Math.min(i, 5) + '" style="flex:' + r.n + '" title="' + esc(r.label) + ' ' + r.n + '"></i>'; }).join('') + '</div>' +
        '<div class="share-legend">' + rows.slice(0, 5).map(function (r, i) { return '<span class="topic-chip seg-' + Math.min(i, 5) + '">' + esc(r.label) + '<b>' + Math.round(r.n * 100 / tot) + '%</b></span>'; }).join('') + '</div></div>';
    });
    html += '</section>';
    // 함께 등장한 주체
    var co = Object.keys(ent.co || {});
    html += '<section class="tr-card"><h2 class="tr-card-title">함께 등장한 주체 <span class="cell-hint">같은 기사에서</span></h2>';
    if (co.length) {
      var cmax = ent.co[co[0]];
      html += '<ol class="rank-list">' + co.map(function (k, i) {
        return '<li><span class="rank-i">' + (i + 1) + '</span><a class="rank-name" href="entity.html?e=' + encodeURIComponent(k) + '">' + esc(k) + '</a>' +
          '<span class="rank-bar"><i style="width:' + Math.round(ent.co[k] * 100 / cmax) + '%"></i></span><span class="rank-n">' + ent.co[k] + '</span><span class="rank-d"></span></li>';
      }).join('') + '</ol>';
    } else {
      html += '<p class="tr-empty">함께 등장한 사전 주체가 없습니다.</p>';
    }
    html += '</section></div>';

    // 등장 목록
    html += '<section class="ent-items"><h2 class="tr-card-title">등장한 기사 <span class="cell-hint">최근순 · 지면으로 이동</span></h2><div id="ent-list"></div>' +
      '<p class="arch-more" id="ent-more" hidden><button type="button" class="archive-action-btn">더 보기</button></p></section>';
    root.innerHTML = html;

    var items = ent.items || [];
    var shown = 0;
    var listEl = document.getElementById('ent-list');
    var moreEl = document.getElementById('ent-more');
    function more() {
      var chunk = items.slice(shown, shown + PAGE);
      var h = ''; var lastDay = shown ? items[shown - 1].d : null;
      chunk.forEach(function (it) {
        if (it.d !== lastDay) { lastDay = it.d; h += '<h3 class="arch-result-day"><a href="archive/' + it.d + '.html">' + fmtDate(it.d) + '</a></h3>'; }
        h += '<div class="arch-result"><i class="dot dot-' + it.s + '" title="' + SEC_SHORT[it.s] + '"></i><a class="arch-result-title" href="archive/' + it.d + '.html#' + it.s + '-' + it.n + '">' + esc(it.t) + '</a>' +
          '<span class="arch-result-src">' + esc((labels[it.s] || {})[it.tp] || '') + '</span></div>';
      });
      listEl.insertAdjacentHTML('beforeend', h);
      shown += chunk.length;
      moreEl.hidden = shown >= items.length;
    }
    more();
    moreEl.querySelector('button').addEventListener('click', more);
  }

  function delta(d) {
    if (!d) return '';
    return ' <span class="delta ' + (d > 0 ? 'up' : 'down') + '">' + (d > 0 ? '▲' : '▼') + Math.abs(d) + '</span>';
  }
})();
