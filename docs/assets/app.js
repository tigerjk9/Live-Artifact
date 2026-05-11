/**
 * Daily Intelligence — app.js
 * 1. 다크모드 토글 (localStorage 저장/복원)
 * 2. 날짜 pill active 상태 처리
 * 3. active pill 스크롤 인투 뷰
 */

(function () {
  'use strict';

  /* ----------------------------------------------------------
     1. 다크모드: 페이지 로드 전에 최대한 빨리 적용
        (body 깜빡임 방지 — script는 </body> 직전에 위치)
     ---------------------------------------------------------- */
  var THEME_KEY = 'di-theme';

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.querySelector('.theme-toggle');
    if (btn) {
      var icon = btn.querySelector('.theme-icon');
      if (icon) icon.textContent = theme === 'dark' ? '○' : '◐';
      btn.setAttribute('aria-label', theme === 'dark' ? '라이트모드 전환' : '다크모드 전환');
    }
  }

  // 저장된 테마 즉시 적용 (파싱 전에 실행)
  var savedTheme = localStorage.getItem(THEME_KEY) || 'light';
  applyTheme(savedTheme);

  /* ----------------------------------------------------------
     2. DOM 준비 후 이벤트 바인딩
     ---------------------------------------------------------- */
  document.addEventListener('DOMContentLoaded', function () {

    // --- 2-1. 다크모드 버튼 ---
    var themeBtn = document.querySelector('.theme-toggle');
    if (themeBtn) {
      // 버튼 아이콘 초기화 (DOMContentLoaded 시점 재설정)
      var current = document.documentElement.getAttribute('data-theme') || 'light';
      var icon = themeBtn.querySelector('.theme-icon');
      if (icon) icon.textContent = current === 'dark' ? '○' : '◐';
      themeBtn.setAttribute('aria-label', current === 'dark' ? '라이트모드 전환' : '다크모드 전환');

      themeBtn.addEventListener('click', function () {
        var now = document.documentElement.getAttribute('data-theme') || 'light';
        var next = now === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        try {
          localStorage.setItem(THEME_KEY, next);
        } catch (e) {
          // localStorage 사용 불가 시 무시
        }
      });
    }

    // --- 2-2. 날짜 네비 동적 빌드 (dates.json 페치) ---
    loadDateNav();

    // --- 2-3. 카테고리 필터 칩 ---
    initCategoryFilter();

  });

  /* ----------------------------------------------------------
     2-2. 날짜 네비 동적 로드:
        dates.json을 페치하여 .date-nav-inner를 다시 렌더링한다.
        archive 페이지에서는 ../assets/dates.json, 루트에서는 assets/dates.json
     ---------------------------------------------------------- */
  function loadDateNav() {
    var navInner = document.querySelector('.date-nav-inner');
    if (!navInner) return;

    var pathname = window.location.pathname;
    var isArchive = pathname.indexOf('/archive/') !== -1;
    var jsonPath = (isArchive ? '../' : '') + 'assets/dates.json';

    fetch(jsonPath, { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)); })
      .then(function (data) {
        var dates = (data && data.available_dates) || [];
        var latest = (data && data.latest) || '';
        if (!dates.length) {
          activateDatePill();  // 페치 실패 시에도 정적 fallback 활성화
          return;
        }
        renderDatePills(navInner, dates, latest, isArchive);
        activateDatePill();
      })
      .catch(function (err) {
        console.warn('[date-nav] dates.json 로드 실패:', err);
        activateDatePill();  // 정적 fallback 사용
      });
  }

  function renderDatePills(navInner, dates, latest, isArchive) {
    // 최신순(내림차순)으로 정렬
    var sorted = dates.slice().sort().reverse();

    var html = sorted.map(function (d) {
      var parts = d.split('-');                // ['2026','05','11']
      var month = parseInt(parts[1], 10);
      var day = parseInt(parts[2], 10);
      var dd = day < 10 ? '0' + day : '' + day;

      var isToday = (d === latest);
      var href;
      if (isToday) {
        href = isArchive ? '../index.html' : 'index.html';
      } else {
        href = (isArchive ? '' : 'archive/') + d + '.html';
      }
      var cls = 'date-pill' + (isToday ? ' today' : '');
      var label = isToday
        ? ('오늘 ' + month + '/' + dd)
        : (month + '/' + dd);
      return '<a class="' + cls + '" href="' + href + '" data-date="' + d + '">' + label + '</a>';
    }).join('');

    navInner.innerHTML = html;
  }

  /* ----------------------------------------------------------
     2-3. 카테고리 필터: 칩 클릭 시 body[data-filter] 토글
     CSS가 ≤1140px에서 비매칭 컬럼을 숨김 처리
     ---------------------------------------------------------- */
  function initCategoryFilter() {
    var chips = document.querySelectorAll('.cat-chip');
    if (!chips.length) return;

    // 초기 상태: 전체
    document.body.setAttribute('data-filter', 'all');

    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        var filter = chip.getAttribute('data-filter') || 'all';
        document.body.setAttribute('data-filter', filter);
        chips.forEach(function (c) { c.classList.remove('active'); });
        chip.classList.add('active');
        // 모바일에서 필터 변경 시 본문 최상단으로 살짝 스크롤
        var grid = document.getElementById('main-content');
        if (grid && window.innerWidth <= 1140) {
          grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  /* ----------------------------------------------------------
     3. 날짜 pill: 현재 URL 기반 active 설정
     ---------------------------------------------------------- */
  function activateDatePill() {
    var pills = document.querySelectorAll('.date-pill');
    if (!pills.length) return;

    // 현재 파일명 추출 (예: "2026-05-11.html" → "2026-05-11")
    var pathname = window.location.pathname;
    var filename = pathname.split('/').pop(); // 마지막 세그먼트

    // index.html 또는 루트('/', '')이면 오늘(index) 활성화
    var isRoot = (
      filename === '' ||
      filename === 'index.html' ||
      pathname === '/' ||
      pathname.endsWith('/docs/') ||
      pathname.endsWith('/docs')
    );

    var activePill = null;

    pills.forEach(function (pill) {
      pill.classList.remove('active');

      var href = pill.getAttribute('href') || '';
      var hrefFile = href.split('/').pop();

      if (isRoot) {
        // 루트: href가 index.html이거나 today 클래스를 가진 pill
        if (hrefFile === 'index.html' || pill.classList.contains('today')) {
          pill.classList.add('active');
          activePill = pill;
        }
      } else {
        // 아카이브 페이지: href 파일명이 현재 파일명과 일치하면 활성화
        if (hrefFile === filename) {
          pill.classList.add('active');
          activePill = pill;
        }
      }
    });

    // active pill이 없으면 today 클래스 pill로 fallback
    if (!activePill) {
      var todayPill = document.querySelector('.date-pill.today');
      if (todayPill) {
        todayPill.classList.add('active');
        activePill = todayPill;
      }
    }

    // --- 3-1. active pill 스크롤 인투 뷰 ---
    if (activePill) {
      scrollPillIntoView(activePill);
    }
  }

  /* ----------------------------------------------------------
     4. active pill이 날짜 nav 안에서 보이도록 스크롤
     ---------------------------------------------------------- */
  function scrollPillIntoView(pill) {
    var nav = document.querySelector('.date-nav-inner');
    if (!nav || !pill) return;

    // requestAnimationFrame으로 레이아웃 완료 후 실행
    requestAnimationFrame(function () {
      var navRect = nav.getBoundingClientRect();
      var pillRect = pill.getBoundingClientRect();

      // pill이 이미 보이는지 확인
      var pillLeft = pillRect.left - navRect.left + nav.scrollLeft;
      var pillRight = pillLeft + pill.offsetWidth;
      var navWidth = nav.clientWidth;

      // 가운데 정렬로 스크롤
      var targetScroll = pillLeft - (navWidth / 2) + (pill.offsetWidth / 2);
      targetScroll = Math.max(0, targetScroll);

      nav.scrollTo({ left: targetScroll, behavior: 'smooth' });
    });
  }

})();
