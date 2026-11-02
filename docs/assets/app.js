/**
 * Daily Intelligence — app.js  (v7)
 * 1. 다크모드: 시스템 prefers-color-scheme 우선, localStorage 오버라이드
 * 2. 날짜 nav — 최근 14일 pill + 전체 아카이브 링크 (dates.json)
 * 3. 카테고리 필터 칩
 * 4. 실시간 검색 (300ms debounce)
 * 5. 키워드 배지 클릭 필터
 * 6. 읽음 추적 (localStorage)
 * 7. 키보드 단축키 (j/k 탐색, / 검색, 0-3 카테고리, Esc 해제)
 * 8. 오늘의 흐름 보드 — 접기, 주제/주체 필터, 참조 칩 점프
 */

(function () {
  'use strict';

  var THEME_KEY   = 'di-theme';
  var READ_KEY    = 'di-read';
  var BOARD_KEY   = 'di-board-collapsed';
  var NAV_DAYS    = 14;
  var searchTimer = null;
  var activeKw    = null;   // 현재 활성 키워드 필터 (null = 없음)
  var activeTopic = null;   // "edu:policy" 형태
  var activeEnt   = null;   // 주체 이름
  var body        = document.body;
  var ROOT        = (body && body.getAttribute('data-root')) || '';   // '' | '../'
  var PAGE        = (body && body.getAttribute('data-page')) || 'daily';
  var pageDate    = (body && body.getAttribute('data-date')) || null; // YYYY-MM-DD

  /* ============================================================
     1. 다크모드 — 초기화 (DOM 파싱 전 즉시 실행)
     ============================================================ */
  function getInitialTheme() {
    var saved;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { saved = null; }
    if (saved === 'dark' || saved === 'light') return saved;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    return 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    var icon = btn.querySelector('.theme-icon');
    if (icon) icon.textContent = theme === 'dark' ? '○' : '◐';
    btn.setAttribute('aria-label', theme === 'dark' ? '라이트모드 전환' : '다크모드 전환');
  }

  applyTheme(getInitialTheme());

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      var saved;
      try { saved = localStorage.getItem(THEME_KEY); } catch (ex) { saved = null; }
      if (!saved) applyTheme(e.matches ? 'dark' : 'light');
    });
  }

  /* ============================================================
     2. DOM 준비 후 바인딩
     ============================================================ */
  document.addEventListener('DOMContentLoaded', function () {
    var themeBtn = document.querySelector('.theme-toggle');
    if (themeBtn) {
      var cur = document.documentElement.getAttribute('data-theme') || 'light';
      var icon = themeBtn.querySelector('.theme-icon');
      if (icon) icon.textContent = cur === 'dark' ? '○' : '◐';
      themeBtn.setAttribute('aria-label', cur === 'dark' ? '라이트모드 전환' : '다크모드 전환');
      themeBtn.addEventListener('click', function () {
        var now  = document.documentElement.getAttribute('data-theme') || 'light';
        var next = now === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
      });
    }

    markSiteNav();
    syncHeaderHeight();
    if (PAGE === 'daily') {
      loadDateNav();
      initCategoryFilter();
      initSearch();
      initKeywordFilter();
      initReadTracking();
      initKeyboardShortcuts();
      initBoard();
    }
  });

  // sticky 스택(날짜 nav·검색·필터)의 top 오프셋은 --header-h를 쓴다. 모바일에서 메뉴가
  // 2행으로 꺾이면 높이가 달라지므로 실제 높이를 측정해 반영한다.
  function syncHeaderHeight() {
    var header = document.querySelector('.site-header');
    if (!header) return;
    function apply() {
      var h = Math.round(header.getBoundingClientRect().height);
      if (h > 0) document.documentElement.style.setProperty('--header-h', h + 'px');
    }
    apply();
    if (window.ResizeObserver) new ResizeObserver(apply).observe(header);
    else window.addEventListener('resize', apply);
  }

  function markSiteNav() {
    document.querySelectorAll('.site-nav-link').forEach(function (a) {
      a.classList.toggle('active', a.getAttribute('data-nav') === PAGE);
      if (a.getAttribute('data-nav') === PAGE) a.setAttribute('aria-current', 'page');
    });
  }

  /* ============================================================
     3. 날짜 네비 — 최근 14일 + 전체 아카이브
     ============================================================ */
  function loadDateNav() {
    var navInner = document.querySelector('.date-nav-inner');
    if (!navInner) return;

    var isArchive = ROOT === '../';
    fetch(ROOT + 'assets/dates.json', { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (data) {
        var dates  = (data && data.available_dates) || [];
        var latest = (data && data.latest) || '';
        if (!dates.length) { activateDatePill(); return; }
        renderDatePills(navInner, dates, latest, isArchive);
        activateDatePill();
      })
      .catch(function (err) {
        console.warn('[date-nav] dates.json 로드 실패:', err);
        activateDatePill();
      });
  }

  function pillLabel(d, isLatest) {
    var parts = d.split('-');
    var month = parseInt(parts[1], 10);
    var day   = parseInt(parts[2], 10);
    var dd    = day < 10 ? '0' + day : '' + day;
    return (isLatest ? '오늘 ' : '') + month + '/' + dd;
  }

  function renderDatePills(navInner, dates, latest, isArchive) {
    var sorted = dates.slice().sort().reverse();
    var recent = sorted.slice(0, NAV_DAYS);
    var html = '';
    // 열람 중인 날짜가 최근 14일 밖이면 맨 앞에 끼워 넣는다
    if (pageDate && recent.indexOf(pageDate) === -1 && dates.indexOf(pageDate) !== -1) {
      html += '<a class="date-pill active" href="' + pageDate + '.html" data-date="' + pageDate + '" aria-current="page">' + pillLabel(pageDate, false) + '</a>';
      html += '<span class="date-pill-gap" aria-hidden="true">…</span>';
    }
    html += recent.map(function (d) {
      var isLatest = (d === latest);
      var href = isLatest ? (ROOT + 'index.html') : (ROOT + 'archive/' + d + '.html');
      var cls  = 'date-pill' + (isLatest ? ' today' : '');
      return '<a class="' + cls + '" href="' + href + '" data-date="' + d + '">' + pillLabel(d, isLatest) + '</a>';
    }).join('');
    html += '<a class="date-pill date-pill-all" href="' + ROOT + 'archive/">전체 아카이브 ' + dates.length + '일 ›</a>';
    navInner.innerHTML = html;

    if (!isArchive && latest) {
      pageDate = pageDate || latest;
      var lp  = latest.split('-');
      var lY  = parseInt(lp[0], 10), lM = parseInt(lp[1], 10), lD = parseInt(lp[2], 10);
      var lDt = new Date(lY, lM - 1, lD);
      var lWd = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
      var lLabel = lY + '년 ' + lM + '월 ' + lD + '일 ' + lWd[lDt.getDay()];
      injectDateActionBar(latest, lLabel, getShareUrl());
    }
  }

  /* ============================================================
     4. 카테고리 필터 칩
     ============================================================ */
  function initCategoryFilter() {
    var chips = document.querySelectorAll('.cat-chip');
    if (!chips.length) return;
    body.setAttribute('data-filter', 'all');
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        setCategory(chip.getAttribute('data-filter') || 'all', true);
      });
    });
  }

  function setCategory(filter, scroll) {
    body.setAttribute('data-filter', filter);
    document.querySelectorAll('.cat-chip').forEach(function (c) {
      c.classList.toggle('active', (c.getAttribute('data-filter') || 'all') === filter);
    });
    var grid = document.getElementById('main-content');
    if (scroll && grid && window.innerWidth <= 1140) {
      grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  /* ============================================================
     5. 날짜 pill 활성화 & 스크롤
     ============================================================ */
  function activateDatePill() {
    var pills = document.querySelectorAll('.date-pill');
    if (!pills.length) return;
    var activePill = null;
    pills.forEach(function (pill) {
      var d = pill.getAttribute('data-date');
      var on = !!(pageDate && d === pageDate);
      pill.classList.toggle('active', on);
      if (on) activePill = pill;
    });
    if (!activePill) {
      var todayPill = document.querySelector('.date-pill.today');
      if (todayPill && ROOT === '') { todayPill.classList.add('active'); activePill = todayPill; }
    }
    if (activePill) scrollPillIntoView(activePill);
  }

  function scrollPillIntoView(pill) {
    var nav = document.querySelector('.date-nav-inner');
    if (!nav || !pill) return;
    requestAnimationFrame(function () {
      var pillLeft = pill.getBoundingClientRect().left - nav.getBoundingClientRect().left + nav.scrollLeft;
      var target   = pillLeft - (nav.clientWidth / 2) + (pill.offsetWidth / 2);
      nav.scrollTo({ left: Math.max(0, target), behavior: 'smooth' });
    });
  }

  /* ============================================================
     6. 실시간 검색 (300ms debounce, 다중 단어 AND)
     ============================================================ */
  function initSearch() {
    var input    = document.getElementById('di-search');
    var clearBtn = document.querySelector('.search-clear');
    var countEl  = document.querySelector('.search-count-badge');
    if (!input) return;

    function getText(entry) {
      return [
        '.entry-title', '.entry-desc', '.entry-impl', '.entry-src', '.entry-by', '.entry-kw', '.entry-topic'
      ].map(function (sel) {
        var el = entry.querySelector(sel);
        return el ? el.textContent : '';
      }).join(' ').toLowerCase();
    }

    function run() {
      var q     = input.value.trim().toLowerCase();
      var terms = q ? q.split(/\s+/) : [];
      var total = 0;

      document.querySelectorAll('.entry').forEach(function (entry) {
        if (!terms.length) {
          entry.classList.remove('entry--hidden-search');
        } else {
          var text  = getText(entry);
          var match = terms.every(function (t) { return text.indexOf(t) !== -1; });
          entry.classList.toggle('entry--hidden-search', !match);
          if (match) total++;
        }
      });

      document.querySelectorAll('.col').forEach(function (col) {
        var old = col.querySelector('.col-empty-search');
        var hasVisible = !!col.querySelector('.entry:not(.entry--hidden-search)');
        if (terms.length && !hasVisible) {
          if (!old) {
            var p = document.createElement('p');
            p.className = 'col-empty col-empty-search';
            p.setAttribute('aria-live', 'polite');
            col.appendChild(p);
            old = p;
          }
          old.textContent = '"' + input.value.trim() + '" 검색 결과 없음';
        } else if (old) {
          old.remove();
        }
      });

      if (clearBtn) clearBtn.hidden = !q;
      if (countEl) {
        if (terms.length) { countEl.textContent = total + '개 결과'; countEl.hidden = false; }
        else countEl.hidden = true;
      }
    }

    input.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(run, 300);
    });
    if (clearBtn) {
      clearBtn.addEventListener('click', function () { input.value = ''; run(); input.focus(); });
    }
  }

  /* ============================================================
     7. 키워드 배지 클릭 필터 — 재클릭 시 해제
     ============================================================ */
  function clearKwFilter() {
    activeKw = null;
    body.removeAttribute('data-kw-filter');
    document.querySelectorAll('.entry-kw').forEach(function (b) { b.classList.remove('kw-active'); });
    document.querySelectorAll('.entry').forEach(function (en) { en.classList.remove('entry--hidden-kw'); });
  }

  function initKeywordFilter() {
    document.addEventListener('click', function (e) {
      var badge = e.target.closest('.entry-kw');
      if (!badge) return;
      var kw = badge.textContent.trim().toLowerCase();
      if (activeKw === kw) { clearKwFilter(); return; }
      clearBoardFilters(false);
      activeKw = kw;
      body.setAttribute('data-kw-filter', kw);
      document.querySelectorAll('.entry').forEach(function (en) {
        var enBadge = en.querySelector('.entry-kw');
        var enKw    = enBadge ? enBadge.textContent.trim().toLowerCase() : '';
        en.classList.toggle('entry--hidden-kw', enKw !== kw);
      });
      document.querySelectorAll('.entry-kw').forEach(function (b) {
        b.classList.toggle('kw-active', b.textContent.trim().toLowerCase() === kw);
      });
      showToast('"' + badge.textContent.trim() + '" 키워드로 필터링 중 — 다시 클릭하면 해제', 'info');
    });
  }

  /* ============================================================
     8. 읽음 추적 — localStorage (di-read: {url: 1})
     ============================================================ */
  function initReadTracking() {
    var readSet = loadReadSet();
    document.querySelectorAll('.entry-title a').forEach(function (link) {
      if (readSet[link.href]) link.closest('.entry').classList.add('entry--read');
    });
    document.addEventListener('click', function (e) {
      var link = e.target.closest('.entry-title a');
      if (!link) return;
      readSet[link.href] = 1;
      saveReadSet(readSet);
      link.closest('.entry').classList.add('entry--read');
    });
  }
  function loadReadSet() {
    try { return JSON.parse(localStorage.getItem(READ_KEY) || '{}'); } catch (e) { return {}; }
  }
  function saveReadSet(set) {
    try { localStorage.setItem(READ_KEY, JSON.stringify(set)); } catch (e) {}
  }

  /* ============================================================
     9. 토스트 알림
     ============================================================ */
  function showToast(msg, type) {
    var container = document.querySelector('.toast-container');
    if (!container) return;
    var el = document.createElement('div');
    el.className = 'toast' + (type === 'error' ? ' toast--error' : type === 'info' ? ' toast--info' : '');
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(function () {
      el.classList.add('toast--out');
      setTimeout(function () { el.remove(); }, 280);
    }, 3200);
  }

  /* ============================================================
     10. 오늘의 흐름 보드
         - 접기/펼치기 (localStorage)
         - [data-topic-filter="sec:topic"] 클릭 → 그 섹션에서 해당 주제만
         - [data-ent-filter="이름"] 클릭 → 전 섹션에서 그 주체가 등장한 소식만
         - .ref[data-ref="sec-n"] 클릭 → 해당 카드로 이동 + 하이라이트
     ============================================================ */
  var SEC_SHORT = { edu: '교육', paper: '논문', tech: '기술' };

  function initBoard() {
    var board = document.getElementById('board');
    if (board) {
      var toggle = board.querySelector('.board-toggle');
      var collapsed = false;
      try { collapsed = localStorage.getItem(BOARD_KEY) === '1'; } catch (e) {}
      setCollapsed(board, toggle, collapsed);
      if (toggle) {
        toggle.addEventListener('click', function () {
          var now = board.classList.contains('collapsed');
          setCollapsed(board, toggle, !now);
          try { localStorage.setItem(BOARD_KEY, !now ? '1' : '0'); } catch (e) {}
        });
      }
    }

    document.addEventListener('click', function (e) {
      var tBtn = e.target.closest('[data-topic-filter]');
      if (tBtn) { toggleTopicFilter(tBtn.getAttribute('data-topic-filter')); return; }
      var eBtn = e.target.closest('[data-ent-filter]');
      if (eBtn) { toggleEntFilter(eBtn.getAttribute('data-ent-filter')); return; }
      var ref = e.target.closest('.ref[data-ref]');
      if (ref) { e.preventDefault(); spotlight(ref.getAttribute('data-ref')); return; }
      var clr = e.target.closest('.filter-clear');
      if (clr) { clearBoardFilters(true); }
    });
  }

  function setCollapsed(board, toggle, collapsed) {
    board.classList.toggle('collapsed', collapsed);
    if (toggle) {
      toggle.textContent = collapsed ? '펼치기' : '접기';
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }
  }

  function topicLabelOf(key) {
    var el = document.querySelector('.topic-chip[data-topic-filter="' + key + '"], .entry-topic[data-topic-filter="' + key + '"]');
    return el ? el.textContent.replace(/\d+$/, '').trim() : key.split(':')[1];
  }

  function toggleTopicFilter(key) {
    if (activeTopic === key) { clearBoardFilters(true); return; }
    clearKwFilter();
    activeEnt = null;
    activeTopic = key;
    var sec = key.split(':')[0];
    var topic = key.split(':')[1];
    document.querySelectorAll('.entry').forEach(function (en) {
      en.classList.remove('entry--hidden-ent');
      var col = en.closest('.col');
      var inSec = col && col.getAttribute('data-cat') === sec;
      en.classList.toggle('entry--hidden-topic', inSec && en.getAttribute('data-topic') !== topic);
    });
    markActive('[data-topic-filter]', 'data-topic-filter', key);
    markActive('[data-ent-filter]', 'data-ent-filter', null);
    if (window.innerWidth <= 1140) setCategory(sec, false);
    renderActiveFilter(SEC_SHORT[sec] + ' · 주제 <b>' + escapeHtml(topicLabelOf(key)) + '</b>');
    updateFilterEmpties();
    scrollToGridIfNeeded();
  }

  function toggleEntFilter(name) {
    if (activeEnt === name) { clearBoardFilters(true); return; }
    clearKwFilter();
    activeTopic = null;
    activeEnt = name;
    var count = 0;
    document.querySelectorAll('.entry').forEach(function (en) {
      en.classList.remove('entry--hidden-topic');
      var ents = (en.getAttribute('data-ents') || '').split('|');
      var hit = ents.indexOf(name) !== -1;
      en.classList.toggle('entry--hidden-ent', !hit);
      if (hit) count++;
    });
    markActive('[data-ent-filter]', 'data-ent-filter', name);
    markActive('[data-topic-filter]', 'data-topic-filter', null);
    if (window.innerWidth <= 1140) setCategory('all', false);
    renderActiveFilter('주체 <b>' + escapeHtml(name) + '</b> 관련 ' + count + '건');
    updateFilterEmpties();
    scrollToGridIfNeeded();
  }

  function clearBoardFilters(announce) {
    activeTopic = null;
    activeEnt = null;
    document.querySelectorAll('.entry').forEach(function (en) {
      en.classList.remove('entry--hidden-topic', 'entry--hidden-ent');
    });
    markActive('[data-topic-filter]', 'data-topic-filter', null);
    markActive('[data-ent-filter]', 'data-ent-filter', null);
    renderActiveFilter('');
    updateFilterEmpties();
    if (announce) showToast('필터를 해제했습니다', 'info');
  }

  function markActive(selector, attr, value) {
    document.querySelectorAll(selector).forEach(function (el) {
      el.classList.toggle('is-active', value !== null && el.getAttribute(attr) === value);
    });
  }

  function renderActiveFilter(html) {
    var host = document.querySelector('.board-head-main');
    if (!host) return;
    var bar = host.querySelector('.board-active-filter');
    if (!html) { if (bar) bar.remove(); return; }
    if (!bar) {
      bar = document.createElement('div');
      bar.className = 'board-active-filter';
      bar.setAttribute('role', 'status');
      host.appendChild(bar);
    }
    bar.innerHTML = '<span>필터: ' + html + '</span><button type="button" class="filter-clear">해제 (Esc)</button>';
    var board = document.getElementById('board');
    if (board && board.classList.contains('collapsed')) {
      setCollapsed(board, board.querySelector('.board-toggle'), false);
    }
  }

  function updateFilterEmpties() {
    document.querySelectorAll('.col').forEach(function (col) {
      var old = col.querySelector('.col-empty-filter');
      var filtering = activeTopic !== null || activeEnt !== null;
      var hasVisible = !!col.querySelector('.entry:not(.entry--hidden-topic):not(.entry--hidden-ent)');
      if (filtering && !hasVisible && col.querySelector('.entry')) {
        if (!old) {
          old = document.createElement('p');
          old.className = 'col-empty col-empty-filter';
          col.appendChild(old);
        }
        old.textContent = '이 섹션에는 해당 소식이 없습니다';
      } else if (old) {
        old.remove();
      }
    });
  }

  function scrollToGridIfNeeded() {
    var grid = document.getElementById('main-content');
    if (!grid) return;
    var rect = grid.getBoundingClientRect();
    if (rect.top > window.innerHeight * 0.7) {
      grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function spotlight(id) {
    var el = document.getElementById(id);
    if (!el) return;
    // 필터로 숨겨진 카드면 필터를 풀고 보여 준다
    if (el.classList.contains('entry--hidden-topic') || el.classList.contains('entry--hidden-ent')) clearBoardFilters(false);
    if (el.classList.contains('entry--hidden-kw')) clearKwFilter();
    var col = el.closest('.col');
    if (col && window.innerWidth <= 1140) setCategory(col.getAttribute('data-cat') || 'all', false);
    el.classList.remove('entry--spot');
    void el.offsetWidth; // 애니메이션 재시작
    el.classList.add('entry--spot');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    var link = el.querySelector('.entry-title a');
    if (link) link.focus({ preventScroll: true });
    if (history.replaceState) history.replaceState(null, '', '#' + id);
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // 공유 링크의 #edu-3 같은 해시로 들어오면 해당 카드 하이라이트
  window.addEventListener('load', function () {
    var m = (location.hash || '').match(/^#((?:edu|paper|tech)-\d+)$/);
    if (m) setTimeout(function () { spotlight(m[1]); }, 150);
  });

  /* ============================================================
     11. 키보드 단축키
     ============================================================ */
  function initKeyboardShortcuts() {
    function visibleEntries() {
      return Array.from(document.querySelectorAll('.entry')).filter(function (en) {
        return !en.classList.contains('entry--hidden-search') &&
               !en.classList.contains('entry--hidden-kw') &&
               !en.classList.contains('entry--hidden-topic') &&
               !en.classList.contains('entry--hidden-ent');
      });
    }
    function focusEntry(entries, idx) {
      var target = entries[Math.max(0, Math.min(idx, entries.length - 1))];
      if (!target) return -1;
      var link = target.querySelector('.entry-title a');
      if (link) { link.focus({ preventScroll: true }); target.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      return Math.max(0, Math.min(idx, entries.length - 1));
    }
    function currentIdx(entries) {
      var active = document.activeElement;
      if (!active) return -1;
      return entries.findIndex(function (en) { return en.contains(active); });
    }

    document.addEventListener('keydown', function (e) {
      var tag = (e.target.tagName || '').toLowerCase();
      var isTyping = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;

      if (e.key === 'Escape') {
        if (activeKw !== null) { clearKwFilter(); return; }
        if (activeTopic !== null || activeEnt !== null) { clearBoardFilters(false); return; }
        var inp = document.getElementById('di-search');
        if (inp && inp.value) { inp.value = ''; inp.dispatchEvent(new Event('input')); inp.blur(); }
        return;
      }
      if (isTyping) return;

      if (e.key === '/') {
        e.preventDefault();
        var si = document.getElementById('di-search');
        if (si) { si.focus(); si.select(); }
        return;
      }
      if (e.key === '0' || e.key === '1' || e.key === '2' || e.key === '3') {
        var filters = ['all', 'edu', 'paper', 'tech'];
        setCategory(filters[+e.key], true);
        return;
      }
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        var ents = visibleEntries();
        var ci   = currentIdx(ents);
        focusEntry(ents, ci < 0 ? 0 : ci + 1);
        return;
      }
      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        var ents2 = visibleEntries();
        var ci2   = currentIdx(ents2);
        focusEntry(ents2, ci2 <= 0 ? 0 : ci2 - 1);
      }
    });
  }

  /* ============================================================
     12. 공유 URL · 날짜 액션 바 · HTML 저장
     ============================================================ */
  function getShareUrl() {
    if (ROOT === '../') return window.location.href;
    if (!pageDate)  return window.location.href;
    var base = window.location.pathname.replace(/(?:index\.html)?$/, '');
    if (base[base.length - 1] !== '/') base += '/';
    return window.location.origin + base + 'archive/' + pageDate + '.html';
  }

  function copyToClipboard(text, cb) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { cb(true); }).catch(function () { cb(false); });
    } else {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        cb(true);
      } catch (e) { cb(false); }
    }
  }

  function injectDateActionBar(dateStr, dateLabel, shareUrl) {
    if (document.querySelector('.archive-date-banner')) return;
    var banner = document.createElement('div');
    banner.className = 'archive-date-banner';
    banner.setAttribute('role', 'status');

    var infoEl = document.createElement('div');
    infoEl.className = 'archive-date-info';
    infoEl.innerHTML = '<span class="archive-date-label">' + dateLabel + '</span><span class="archive-date-sub">자 지면</span>';

    var actEl = document.createElement('div');
    actEl.className = 'archive-date-actions';

    var copyBtn = document.createElement('button');
    copyBtn.className = 'archive-action-btn';
    copyBtn.type = 'button';
    copyBtn.innerHTML =
      '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>' +
      '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg> 링크 복사';
    copyBtn.addEventListener('click', function () {
      copyToClipboard(shareUrl, function (ok) {
        showToast(ok ? '링크가 복사되었습니다' : '복사 실패', ok ? 'info' : 'error');
      });
    });

    var dlBtn = document.createElement('button');
    dlBtn.className = 'archive-action-btn';
    dlBtn.type = 'button';
    dlBtn.innerHTML =
      '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> HTML 저장';
    dlBtn.addEventListener('click', function () { downloadPageHTML(dateStr); });

    actEl.appendChild(copyBtn);
    actEl.appendChild(dlBtn);
    banner.appendChild(infoEl);
    banner.appendChild(actEl);

    var anchor = document.getElementById('board') || document.getElementById('main-content');
    if (anchor) anchor.parentNode.insertBefore(banner, anchor);
  }

  function downloadPageHTML(dateStr) {
    var cssPath   = ROOT + 'assets/style.css';
    var assetBase = window.location.href
      .replace(/\/archive\/[^/?#]*$/, '/')
      .replace(/\/index\.html([?#].*)?$/, '/')
      .replace(/([^/])$/, '$1/');

    showToast('HTML 파일 준비 중…', 'info');
    fetch(cssPath)
      .then(function (r) { return r.ok ? r.text() : Promise.reject(new Error('CSS ' + r.status)); })
      .then(function (css) {
        var src = document.documentElement.outerHTML;
        var out = src
          .replace(/<link[^>]+style\.css[^>]*>/, '<style>\n' + css + '\n</style>')
          .replace(/src="\.\.\/assets\//g,  'src="'  + assetBase + 'assets/')
          .replace(/src="assets\//g,        'src="'  + assetBase + 'assets/')
          .replace(/href="\.\.\/assets\//g, 'href="' + assetBase + 'assets/')
          .replace(/href="assets\//g,       'href="' + assetBase + 'assets/')
          .replace(/<script\s+src="[^"]*"[^>]*><\/script>/gi, '');
        var blob = new Blob([out], { type: 'text/html;charset=utf-8' });
        var burl = URL.createObjectURL(blob);
        var a    = document.createElement('a');
        a.href     = burl;
        a.download = 'Daily_Intelligence_' + dateStr + '.html';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(burl); }, 5000);
      })
      .catch(function (err) {
        console.warn('[DL]', err);
        showToast('HTML 생성 실패 — 나중에 다시 시도해 주세요', 'error');
      });
  }

  /* ============================================================
     13. 푸터 — 최신 뉴스 링크(아카이브) + 상단 이동
     ============================================================ */
  (function () {
    var footerMeta = document.querySelector('.footer-meta');
    if (!footerMeta) return;
    if (ROOT === '../' && PAGE === 'daily') {
      var homeLink = document.createElement('a');
      homeLink.className = 'footer-link';
      homeLink.href = '../';
      homeLink.setAttribute('aria-label', '최신 뉴스 페이지로 이동');
      homeLink.textContent = '← 최신 뉴스';
      footerMeta.insertBefore(homeLink, footerMeta.firstChild);
    }
    var totop = document.createElement('a');
    totop.className = 'footer-totop';
    totop.href = '#';
    totop.setAttribute('aria-label', '페이지 상단으로 이동');
    totop.textContent = '↑ 상단';
    footerMeta.appendChild(totop);
    totop.addEventListener('click', function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  })();

  /* ============================================================
     14. 헤더 현재 시각 (KST) · 아카이브 날짜 배너
     ============================================================ */
  (function () {
    var hd = document.querySelector('.header-date');
    if (!hd) return;

    var sep = document.createElement('span');
    sep.className = 'header-time-sep';
    sep.setAttribute('aria-hidden', 'true');
    var clock = document.createElement('span');
    clock.className = 'header-live-time';
    clock.setAttribute('aria-label', '현재 시각');
    hd.parentNode.insertBefore(sep, hd.nextSibling);
    hd.parentNode.insertBefore(clock, sep.nextSibling);

    var md = document.querySelector('.masthead-date[data-live]');
    function kstNow() { return new Date(Date.now() + 9 * 3600000); }
    function tick() {
      var t  = kstNow();
      var wd = ['일', '월', '화', '수', '목', '금', '토'][t.getUTCDay()];
      var hh = t.getUTCHours(), mm = t.getUTCMinutes();
      hd.textContent = t.getUTCFullYear() + '년 ' + (t.getUTCMonth() + 1) + '월 ' + t.getUTCDate() + '일 (' + wd + ')';
      if (md) md.textContent = t.getUTCFullYear() + '년 ' + (t.getUTCMonth() + 1) + '월 ' + t.getUTCDate() + '일 ' + wd + '요일';
      clock.textContent = (hh < 10 ? '0' : '') + hh + ':' + (mm < 10 ? '0' : '') + mm;
    }
    tick();
    setInterval(tick, 1000);

    if (!(ROOT === '../' && PAGE === 'daily')) return;
    var d = pageDate || ((window.location.pathname.match(/(\d{4}-\d{2}-\d{2})\.html/) || [])[1]);
    if (!d) return;
    var parts = d.split('-');
    var dObj  = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    var wdays = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
    pageDate = d;
    var dateLabel = parts[0] + '년 ' + parseInt(parts[1], 10) + '월 ' + parseInt(parts[2], 10) + '일 ' + wdays[dObj.getDay()];
    injectDateActionBar(d, dateLabel, window.location.href);
  })();

  /* ============================================================
     15. Service Worker 등록 (PWA 오프라인 지원)
     ============================================================ */
  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register(ROOT + 'sw.js')
        .catch(function (e) { console.warn('[SW] 등록 실패:', e); });
    });
  }

  // 다른 페이지 스크립트(archive.js, trends.js)가 쓰는 공용 헬퍼
  window.DI = { showToast: showToast, escapeHtml: escapeHtml, ROOT: ROOT };

})();
