/**
 * archive.js — 전체 아카이브 페이지
 *  - data/index.json : 월별 날짜 카드 (건수 막대, 헤드라인, 주체 2개)
 *  - data/search.json: 전 기간 제목 검색 (첫 입력 때 지연 로드), ?q= 공유 지원
 */
(function () {
  'use strict';

  var ROOT = (window.DI && window.DI.ROOT) || '../';
  var esc  = (window.DI && window.DI.escapeHtml) || function (s) { return String(s); };
  var SEC_SHORT = { edu: '교육', paper: '논문', tech: '기술' };
  var WD = ['일', '월', '화', '수', '목', '금', '토'];
  var MAX_RESULTS = 150;

  var index = null;
  var searchRows = null;
  var searchLoading = null;
  var timer = null;

  document.addEventListener('DOMContentLoaded', function () {
    fetch(ROOT + 'data/index.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (data) {
        index = data;
        renderStats(data);
        renderMonths(data);
        initSearch();
        var q = new URLSearchParams(location.search).get('q');
        if (q) {
          var input = document.getElementById('arch-search');
          if (input) { input.value = q; runSearch(q); }
        }
      })
      .catch(function (err) {
        console.warn('[archive] index.json 로드 실패:', err);
        var host = document.getElementById('arch-months');
        if (host) host.innerHTML = '<p class="page-loading">아카이브 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>';
      });
  });

  /* ── 상단 통계 ─────────────────────────────── */
  function renderStats(data) {
    var host = document.getElementById('arch-stats');
    if (!host) return;
    var days = data.days || [];
    var total = data.total_items || 0;
    var span = data.first && data.latest ? fmtDate(data.first) + ' ~ ' + fmtDate(data.latest) : '';
    host.innerHTML =
      stat(days.length + '일', '수집 일수') +
      stat(total.toLocaleString('ko-KR') + '건', '누적 소식') +
      stat(span || '-', '기간');
  }
  function stat(n, k) { return '<div class="stat"><span class="stat-n">' + esc(n) + '</span><span class="stat-k">' + esc(k) + '</span></div>'; }
  function fmtDate(d) { var p = d.split('-'); return p[0] + '.' + p[1] + '.' + p[2]; }

  /* ── 월별 카드 ─────────────────────────────── */
  function renderMonths(data) {
    var host = document.getElementById('arch-months');
    if (!host) return;
    var days = (data.days || []).slice().sort(function (a, b) { return a.d < b.d ? 1 : -1; });
    if (!days.length) { host.innerHTML = '<p class="page-loading">아직 저장된 날짜가 없습니다.</p>'; return; }
    var latest = data.latest;
    var byMonth = {};
    var order = [];
    days.forEach(function (e) {
      var m = e.d.slice(0, 7);
      if (!byMonth[m]) { byMonth[m] = []; order.push(m); }
      byMonth[m].push(e);
    });
    var html = order.map(function (m) {
      var list = byMonth[m];
      var items = list.reduce(function (s, e) { return s + sum(e.n); }, 0);
      var p = m.split('-');
      return '<section class="arch-month" id="m-' + m + '">' +
        '<div class="arch-month-head"><h2 class="arch-month-title">' + p[0] + '년 ' + parseInt(p[1], 10) + '월</h2>' +
        '<span class="arch-month-sub">' + list.length + '일 · ' + items + '건</span></div>' +
        '<div class="arch-days">' + list.map(function (e) { return dayCard(e, e.d === latest); }).join('') + '</div>' +
        '</section>';
    }).join('');
    host.innerHTML = html;
  }

  function sum(n) { return (n.edu || 0) + (n.paper || 0) + (n.tech || 0); }

  function dayCard(e, isLatest) {
    var p = e.d.split('-');
    var dt = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
    var wd = dt.getDay();
    var n = e.n || {};
    var total = sum(n) || 1;
    var bars = ['edu', 'paper', 'tech'].map(function (s) {
      var v = n[s] || 0;
      return v ? '<i class="b-' + s + '" style="flex:' + v + '" title="' + SEC_SHORT[s] + ' ' + v + '건"></i>' : '';
    }).join('');
    var ents = Object.keys(e.ents || {}).slice(0, 2).map(function (k) { return '<span>' + esc(k) + '</span>'; }).join('');
    var head = e.head ? '<p class="arch-day-head">' + esc(e.head) + '</p>' : '';
    var href = isLatest ? '../index.html' : e.d + '.html';
    return '<a class="arch-day' + (isLatest ? ' is-latest' : '') + '" href="' + href + '">' +
      '<div class="arch-day-top"><span class="arch-day-date">' + parseInt(p[1], 10) + '/' + p[2] + '</span>' +
      '<span class="arch-day-wd' + (wd === 6 ? ' sat' : wd === 0 ? ' sun' : '') + '">' + WD[wd] + '</span></div>' +
      '<div class="arch-day-bars" aria-label="섹션별 건수">' + bars + '</div>' +
      '<span class="arch-day-n">' + total + '건' + (e.fb && e.fb.length ? ' · 일부 전일 데이터' : '') + '</span>' +
      head +
      (ents ? '<div class="arch-day-ents">' + ents + '</div>' : '') +
      '</a>';
  }

  /* ── 전 기간 검색 ──────────────────────────── */
  function initSearch() {
    var input = document.getElementById('arch-search');
    var clearBtn = document.querySelector('.search-clear');
    if (!input) return;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (clearBtn) clearBtn.hidden = !q;
      timer = setTimeout(function () { runSearch(q); }, 280);
    });
    if (clearBtn) clearBtn.addEventListener('click', function () { input.value = ''; clearBtn.hidden = true; runSearch(''); input.focus(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && !/input|textarea|select/i.test(e.target.tagName)) { e.preventDefault(); input.focus(); input.select(); }
      if (e.key === 'Escape' && input.value) { input.value = ''; runSearch(''); input.blur(); }
    });
  }

  function loadSearch() {
    if (searchRows) return Promise.resolve(searchRows);
    if (!searchLoading) {
      searchLoading = fetch(ROOT + 'data/search.json', { cache: 'no-cache' })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
        .then(function (rows) { searchRows = rows; return rows; });
    }
    return searchLoading;
  }

  function runSearch(q) {
    var host = document.getElementById('arch-results');
    var months = document.getElementById('arch-months');
    var badge = document.querySelector('.search-count-badge');
    if (!host) return;
    if (history.replaceState) {
      var url = location.pathname + (q ? '?q=' + encodeURIComponent(q) : '');
      history.replaceState(null, '', url);
    }
    if (!q) {
      host.hidden = true; host.innerHTML = '';
      if (months) months.hidden = false;
      if (badge) badge.hidden = true;
      return;
    }
    // 섹션 선택값은 결과 영역을 비우기 전에 읽어 둔다 (아래 innerHTML 교체로 select가 사라진다)
    var prevSel = host.querySelector('select');
    var secFilter = prevSel ? prevSel.value : 'all';
    host.hidden = false;
    host.innerHTML = '<p class="page-loading">검색 색인을 불러오는 중…</p>';
    loadSearch().then(function (rows) {
      var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
      var hits = rows.filter(function (r) {
        var text = (r.t + ' ' + (r.src || '')).toLowerCase();
        return terms.every(function (t) { return text.indexOf(t) !== -1; });
      });
      hits.sort(function (a, b) { return a.d < b.d ? 1 : a.d > b.d ? -1 : a.s < b.s ? -1 : 1; });
      var shown = secFilter === 'all' ? hits : hits.filter(function (r) { return r.s === secFilter; });
      renderResults(host, q, hits, shown, secFilter, terms);
      if (months) months.hidden = true;
      if (badge) { badge.textContent = shown.length + '건'; badge.hidden = false; }
    }).catch(function (err) {
      console.warn('[archive] search.json 로드 실패:', err);
      host.innerHTML = '<p class="page-loading">검색 색인을 불러오지 못했습니다.</p>';
    });
  }

  function renderResults(host, q, hits, shown, secFilter, terms) {
    var counts = { edu: 0, paper: 0, tech: 0 };
    hits.forEach(function (r) { counts[r.s] = (counts[r.s] || 0) + 1; });
    var daysSet = {};
    shown.forEach(function (r) { daysSet[r.d] = 1; });
    var html = '<div class="arch-results-head"><span>"' + esc(q) + '" 검색 결과 <b>' + shown.length + '건</b> · ' + Object.keys(daysSet).length + '일</span>' +
      '<label>섹션 <select aria-label="섹션 선택">' +
      opt('all', '전체 ' + hits.length, secFilter) + opt('edu', '교육 ' + counts.edu, secFilter) +
      opt('paper', '논문 ' + counts.paper, secFilter) + opt('tech', '기술 ' + counts.tech, secFilter) +
      '</select></label></div>';
    var lastDay = null;
    shown.slice(0, MAX_RESULTS).forEach(function (r) {
      if (r.d !== lastDay) {
        lastDay = r.d;
        var p = r.d.split('-');
        var dt = new Date(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10));
        html += '<h3 class="arch-result-day"><a href="' + r.d + '.html">' + p[0] + '년 ' + parseInt(p[1], 10) + '월 ' + parseInt(p[2], 10) + '일 (' + WD[dt.getDay()] + ')</a></h3>';
      }
      html += '<div class="arch-result"><i class="dot dot-' + r.s + '" title="' + SEC_SHORT[r.s] + '"></i>' +
        '<a class="arch-result-title" href="' + r.d + '.html#' + r.s + '-' + r.n + '">' + highlight(r.t, terms) + '</a>' +
        '<span class="arch-result-src">' + esc(r.src || SEC_SHORT[r.s]) + '</span></div>';
    });
    if (shown.length > MAX_RESULTS) html += '<p class="arch-more">상위 ' + MAX_RESULTS + '건만 표시 — 검색어를 더 구체적으로 입력해 주세요.</p>';
    if (!shown.length) html += '<p class="page-loading">일치하는 소식이 없습니다.</p>';
    host.innerHTML = html;
    var sel = host.querySelector('select');
    if (sel) sel.addEventListener('change', function () {
      var input = document.getElementById('arch-search');
      runSearch(input ? input.value.trim() : q);
    });
  }

  function opt(v, label, cur) { return '<option value="' + v + '"' + (v === cur ? ' selected' : '') + '>' + esc(label) + '</option>'; }

  function highlight(text, terms) {
    var out = esc(text);
    terms.forEach(function (t) {
      if (!t) return;
      var re = new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
      out = out.replace(re, '<mark>$1</mark>');
    });
    return out;
  }
})();
