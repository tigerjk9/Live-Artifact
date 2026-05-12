/**
 * Daily Intelligence — app.js  (v6)
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
  var pageDate    = null;   // 현재 페이지의 콘텐츠 날짜 (YYYY-MM-DD, 공유 URL용)

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
    initShareButton();
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
    if (!isArchive && latest) pageDate = latest; // index 페이지: 공유 URL용 날짜 기록
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

  /* ============================================================
     11-b. 공유 버튼 — 영구 아카이브 URL + Web Share API
     ============================================================ */
  function initShareButton() {
    var headerRight = document.querySelector('.header-right');
    if (!headerRight) return;

    var btn = document.createElement('button');
    btn.className = 'share-btn';
    btn.type      = 'button';
    btn.setAttribute('aria-label', '이 날의 기사 링크 공유');
    btn.setAttribute('title', '링크 공유 / 복사');
    btn.innerHTML =
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' +
      '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>' +
      '<polyline points="16 6 12 2 8 6"/>' +
      '<line x1="12" y1="2" x2="12" y2="15"/>' +
      '</svg>';

    var themeBtn = headerRight.querySelector('.theme-toggle');
    if (themeBtn) headerRight.insertBefore(btn, themeBtn);
    else headerRight.appendChild(btn);

    btn.addEventListener('click', function () {
      var url   = getShareUrl();
      var label = pageDateLabel();
      var title = 'Daily Intelligence' + (label ? ' — ' + label : '');
      var text  = '교육 뉴스 · AI 논문 · AI 기술 일일 브리핑';

      if (navigator.share) {
        navigator.share({ title: title, text: text, url: url }).catch(function () {});
      } else {
        copyToClipboard(url, function (ok) {
          showToast(ok ? '링크가 복사되었습니다' : '복사 실패 — 직접 복사해 주세요: ' + url,
                    ok ? 'info' : 'error');
        });
      }
    });
  }

  function getShareUrl() {
    var isArchive = window.location.pathname.indexOf('/archive/') !== -1;
    if (isArchive) return window.location.href; // 이미 영구 URL
    if (!pageDate)  return window.location.href; // dates.json 미로드 시 fallback
    // index.html → 날짜별 아카이브 영구 URL
    var base = window.location.pathname.replace(/(?:index\.html)?$/, '');
    if (base[base.length - 1] !== '/') base += '/';
    return window.location.origin + base + 'archive/' + pageDate + '.html';
  }

  function pageDateLabel() {
    if (!pageDate) return '';
    var p = pageDate.split('-');
    return parseInt(p[0], 10) + '년 ' + parseInt(p[1], 10) + '월 ' + parseInt(p[2], 10) + '일';
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

  /* ============================================================
     12. 아카이브 개선 — 최신 뉴스 링크 + 상단 이동 버튼
     ============================================================ */
  (function () {
    var isArchivePage = window.location.pathname.indexOf('/archive/') !== -1;
    var footerMeta    = document.querySelector('.footer-meta');
    if (!footerMeta) return;

    if (isArchivePage) {
      var homeLink       = document.createElement('a');
      homeLink.className = 'footer-link';
      homeLink.href      = '../';
      homeLink.setAttribute('aria-label', '최신 뉴스 페이지로 이동');
      homeLink.textContent = '← 최신 뉴스';
      footerMeta.insertBefore(homeLink, footerMeta.firstChild);
    }

    var totop       = document.createElement('a');
    totop.className = 'footer-totop';
    totop.href      = '#';
    totop.setAttribute('aria-label', '페이지 상단으로 이동');
    totop.textContent = '↑ 상단';
    footerMeta.appendChild(totop);
    totop.addEventListener('click', function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  })();

  /* ============================================================
     13. 헤더 현재 시각 (KST) — 항상 현재 날짜/시간 표시
         아카이브 페이지: 열람 중인 날짜 배너 삽입
     ============================================================ */
  (function () {
    var hd = document.querySelector('.header-date');
    if (!hd) return;

    var isArchive = window.location.pathname.indexOf('/archive/') !== -1;

    var sep = document.createElement('span');
    sep.className = 'header-time-sep';
    sep.setAttribute('aria-hidden', 'true');

    var clock = document.createElement('span');
    clock.className = 'header-live-time';
    clock.setAttribute('aria-label', '현재 시각');

    hd.parentNode.insertBefore(sep, hd.nextSibling);
    hd.parentNode.insertBefore(clock, sep.nextSibling);

    function tick() {
      var now = new Date();
      hd.textContent = now.toLocaleString('ko-KR', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
      clock.textContent = now.toLocaleString('ko-KR', {
        timeZone: 'Asia/Seoul',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      });
    }
    tick();
    setInterval(tick, 30000);

    // 아카이브: 열람 중인 날짜 배너
    if (!isArchive) return;
    var urlMatch = window.location.pathname.match(/(\d{4}-\d{2}-\d{2})\.html/);
    if (!urlMatch) return;

    var parts = urlMatch[1].split('-');
    var year  = parseInt(parts[0], 10);
    var month = parseInt(parts[1], 10);
    var day   = parseInt(parts[2], 10);
    var dObj  = new Date(year, month - 1, day);
    var days  = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
    pageDate = urlMatch[1]; // 아카이브 페이지: 공유 URL용 날짜 기록
    var dateLabel = year + '년 ' + month + '월 ' + day + '일 ' + days[dObj.getDay()];

    var banner = document.createElement('div');
    banner.className = 'archive-date-banner';
    banner.setAttribute('role', 'status');
    banner.innerHTML =
      '<span class="archive-date-label">' + dateLabel + '</span>' +
      '<span class="archive-date-sub">의 기사</span>';

    var grid = document.getElementById('main-content');
    if (grid) grid.parentNode.insertBefore(banner, grid);
  })();

  /* ============================================================
     11. Service Worker 등록 (PWA 오프라인 지원)
     ============================================================ */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      var isArchive = window.location.pathname.indexOf('/archive/') !== -1;
      navigator.serviceWorker.register(isArchive ? '../sw.js' : 'sw.js')
        .catch(function (e) { console.warn('[SW] 등록 실패:', e); });
    });
  }

})();
