/**
 * Daily Intelligence — app.js  (v5)
 * 1. 다크모드: 시스템 prefers-color-scheme 우선, localStorage 오버라이드
 * 2. 날짜 nav — 로딩 스피너 + 오류 토스트
 * 3. 카테고리 필터 칩
 * 4. 실시간 검색 (300ms debounce)
 * 5. 키워드 배지 클릭 필터
 * 6. 읽음 추적 (localStorage)
 * 7. 키보드 단축키 (j/k 탐색, / 검색, 0-3 카테고리, Esc 해제)
 */

(function () {
  'use strict';

  var THEME_KEY   = 'di-theme';
  var READ_KEY    = 'di-read';
  var searchTimer = null;
  var activeKw    = null;   // 현재 활성 키워드 필터 (null = 없음)

  /* ============================================================
     1. 다크모드 — 초기화 (DOM 파싱 전 즉시 실행)
     ============================================================ */
  function getInitialTheme() {
    var saved;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { saved = null; }
    if (saved === 'dark' || saved === 'light') return saved;
    // localStorage 오버라이드 없으면 시스템 선호 반영
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
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

  // 시스템 다크모드 변경 감지 (localStorage 오버라이드 없을 때만)
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

    // 다크모드 버튼
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

    loadDateNav();
    initCategoryFilter();
    initSearch();
    initKeywordFilter();
    initReadTracking();
    initKeyboardShortcuts();
  });

  /* ============================================================
     3. 날짜 네비 — 로딩 스피너 + 오류 토스트
     ============================================================ */
  function loadDateNav() {
    var navInner = document.querySelector('.date-nav-inner');
    if (!navInner) return;

    // 로딩 상태 표시
    navInner.innerHTML = '<span class="nav-loading"><span class="nav-spinner" aria-hidden="true"></span>날짜 로딩 중…</span>';

    var isArchive = window.location.pathname.indexOf('/archive/') !== -1;
    var jsonPath  = (isArchive ? '../' : '') + 'assets/dates.json';

    fetch(jsonPath, { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (data) {
        var dates  = (data && data.available_dates) || [];
        var latest = (data && data.latest) || '';
        if (!dates.length) { navInner.innerHTML = ''; activateDatePill(); return; }
        renderDatePills(navInner, dates, latest, isArchive);
        activateDatePill();
      })
      .catch(function (err) {
        console.warn('[date-nav] dates.json 로드 실패:', err);
        navInner.innerHTML = '';
        showToast('날짜 목록을 불러오지 못했습니다.', 'error');
        activateDatePill();
      });
  }

  function renderDatePills(navInner, dates, latest, isArchive) {
    var sorted = dates.slice().sort().reverse();
    var html = sorted.map(function (d) {
      var parts = d.split('-');
      var month = parseInt(parts[1], 10);
      var day   = parseInt(parts[2], 10);
      var dd    = day < 10 ? '0' + day : '' + day;
      var isToday = (d === latest);
      var href = isToday
        ? (isArchive ? '../index.html' : 'index.html')
        : (isArchive ? '' : 'archive/') + d + '.html';
      var cls   = 'date-pill' + (isToday ? ' today' : '');
      var label = isToday ? ('오늘 ' + month + '/' + dd) : (month + '/' + dd);
      return '<a class="' + cls + '" href="' + href + '" data-date="' + d + '">' + label + '</a>';
    }).join('');
    navInner.innerHTML = html;
  }

  /* ============================================================
     4. 카테고리 필터 칩
     ============================================================ */
  function initCategoryFilter() {
    var chips = document.querySelectorAll('.cat-chip');
    if (!chips.length) return;
    document.body.setAttribute('data-filter', 'all');

    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        var filter = chip.getAttribute('data-filter') || 'all';
        document.body.setAttribute('data-filter', filter);
        chips.forEach(function (c) { c.classList.remove('active'); });
        chip.classList.add('active');
        var grid = document.getElementById('main-content');
        if (grid && window.innerWidth <= 1140) {
          grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  /* ============================================================
     5. 날짜 pill 활성화 & 스크롤
     ============================================================ */
  function activateDatePill() {
    var pills = document.querySelectorAll('.date-pill');
    if (!pills.length) return;

    var pathname = window.location.pathname;
    var filename = pathname.split('/').pop();
    var isRoot   = (
      filename === '' || filename === 'index.html' ||
      pathname === '/' || pathname.endsWith('/docs/') || pathname.endsWith('/docs')
    );
    var activePill = null;

    pills.forEach(function (pill) {
      pill.classList.remove('active');
      var hrefFile = (pill.getAttribute('href') || '').split('/').pop();
      if (isRoot) {
        if (hrefFile === 'index.html' || pill.classList.contains('today')) {
          pill.classList.add('active'); activePill = pill;
        }
      } else {
        if (hrefFile === filename) { pill.classList.add('active'); activePill = pill; }
      }
    });

    if (!activePill) {
      var todayPill = document.querySelector('.date-pill.today');
      if (todayPill) { todayPill.classList.add('active'); activePill = todayPill; }
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
        '.entry-title', '.entry-desc', '.entry-src', '.entry-by', '.entry-kw'
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

      // 컬럼별 빈 메시지
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
        if (terms.length) {
          countEl.textContent = total + '개 결과';
          countEl.hidden = false;
        } else {
          countEl.hidden = true;
        }
      }
    }

    input.addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(run, 300);
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        input.value = '';
        run();
        input.focus();
      });
    }
  }

  /* ============================================================
     7. 키워드 배지 클릭 필터 — 재클릭 시 해제
     ============================================================ */
  function initKeywordFilter() {
    document.addEventListener('click', function (e) {
      var badge = e.target.closest('.entry-kw');
      if (!badge) return;

      var kw = badge.textContent.trim().toLowerCase();

      if (activeKw === kw) {
        // 해제
        activeKw = null;
        document.body.removeAttribute('data-kw-filter');
        document.querySelectorAll('.entry-kw').forEach(function (b) { b.classList.remove('kw-active'); });
        document.querySelectorAll('.entry').forEach(function (en) { en.classList.remove('entry--hidden-kw'); });
      } else {
        // 활성화
        activeKw = kw;
        document.body.setAttribute('data-kw-filter', kw);
        document.querySelectorAll('.entry').forEach(function (en) {
          var enBadge = en.querySelector('.entry-kw');
          var enKw    = enBadge ? enBadge.textContent.trim().toLowerCase() : '';
          en.classList.toggle('entry--hidden-kw', enKw !== kw);
        });
        document.querySelectorAll('.entry-kw').forEach(function (b) {
          b.classList.toggle('kw-active', b.textContent.trim().toLowerCase() === kw);
        });
        showToast('"' + badge.textContent.trim() + '" 키워드로 필터링 중 — 다시 클릭하면 해제', 'info');
      }
    });
  }

  /* ============================================================
     8. 읽음 추적 — localStorage (di-read: {url: 1})
     ============================================================ */
  function initReadTracking() {
    var readSet = loadReadSet();

    // 이미 읽은 항목 복원
    document.querySelectorAll('.entry-title a').forEach(function (link) {
      if (readSet[link.href]) link.closest('.entry').classList.add('entry--read');
    });

    // 클릭 시 읽음 처리
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
     10. 키보드 단축키
         /       → 검색 포커스
         0       → 전체 카테고리
         1/2/3   → 교육/논문/기술 카테고리
         j / ↓  → 다음 항목
         k / ↑  → 이전 항목
         Esc     → 검색 지우기 / 키워드 필터 해제
     ============================================================ */
  function initKeyboardShortcuts() {
    function visibleEntries() {
      return Array.from(document.querySelectorAll('.entry')).filter(function (en) {
        return !en.classList.contains('entry--hidden-search') &&
               !en.classList.contains('entry--hidden-kw');
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
      var tag     = (e.target.tagName || '').toLowerCase();
      var isTyping = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;

      // Escape: 키워드 필터 → 검색 지우기 순서로 해제
      if (e.key === 'Escape') {
        if (activeKw !== null) {
          document.body.removeAttribute('data-kw-filter');
          activeKw = null;
          document.querySelectorAll('.entry-kw').forEach(function (b) { b.classList.remove('kw-active'); });
          document.querySelectorAll('.entry').forEach(function (en) { en.classList.remove('entry--hidden-kw'); });
          return;
        }
        var inp = document.getElementById('di-search');
        if (inp && inp.value) {
          inp.value = '';
          inp.dispatchEvent(new Event('input'));
          inp.blur();
        }
        return;
      }

      if (isTyping) return;

      // / → 검색 포커스
      if (e.key === '/') {
        e.preventDefault();
        var si = document.getElementById('di-search');
        if (si) { si.focus(); si.select(); }
        return;
      }

      // 0/1/2/3 → 카테고리 필터
      if (e.key === '0' || e.key === '1' || e.key === '2' || e.key === '3') {
        var filters = ['all', 'edu', 'paper', 'tech'];
        var chip = document.querySelector('.cat-chip[data-filter="' + filters[+e.key] + '"]');
        if (chip) chip.click();
        return;
      }

      // j/↓ → 다음, k/↑ → 이전
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

})();
