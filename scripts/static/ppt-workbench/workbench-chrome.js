/* Local UI state only. Never saves, confirms, reloads or changes a project. */
(function () {
  'use strict';

  function getAlignmentStatus(pending = [], progress = [], stage = '') {
    const count = pending.length;
    const recheck = progress.some(row => row.id === stage && row.status === 'revision_required');
    const description = [
      count ? `${count} 项修改待与 Agent 对齐。` : '',
      recheck ? '本阶段需重新对齐，可继续查看和修改。' : '',
      count || recheck ? '原成果保留，对齐后再确认与制作。' : ''
    ].filter(Boolean).join(' ');
    return { count, recheck, visible: count > 0 || recheck,
      label: count ? '待对齐' : '待重新对齐', description };
  }

  function createChromeMotion(initialY = 0) {
    let lastY = Math.max(0, initialY), direction = 0, travel = 0, visible = true;
    return {
      get visible() { return visible; },
      show() { visible = true; direction = 0; travel = 0; },
      hide() { visible = false; direction = 0; travel = 0; },
      sync(y) { lastY = Math.max(0, y); direction = 0; travel = 0; },
      scroll(y, { canHide = true, hideAfter = 160 } = {}) {
        y = Math.max(0, y);
        const delta = y - lastY;
        lastY = y;
        if (Math.abs(delta) < 1) return;
        const nextDirection = Math.sign(delta);
        travel = nextDirection === direction ? travel + Math.abs(delta) : Math.abs(delta);
        direction = nextDirection;
        if (delta < 0 && (travel >= 12 || y <= 24)) visible = true;
        if (delta > 0 && y > hideAfter && travel >= 32 && canHide) visible = false;
      }
    };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { createChromeMotion, getAlignmentStatus };
  if (typeof window !== 'undefined') window.getAlignmentStatus = getAlignmentStatus;
  if (typeof document === 'undefined') return;

  const root = document.querySelector('#workbench-chrome');
  const surface = document.querySelector('#chrome-surface');
  const collapse = document.querySelector('#collapse-chrome');
  const reveal = document.querySelector('#reveal-chrome');
  if (!root || !surface || !collapse || !reveal) return;

  const motion = createChromeMotion(window.scrollY);
  let keyboardNavigation = false, scrollFrame = 0, revealTimer = 0;
  const dialogOpen = () => !!document.querySelector('dialog[open]');
  // offsetTop on a stuck element follows its painted position, not its flow origin.
  const flowStart = () => root.parentElement.getBoundingClientRect().top + window.scrollY;

  function geometry() {
    const rect = root.getBoundingClientRect();
    reveal.style.left = rect.left + 'px';
    reveal.style.width = rect.width + 'px';
  }

  function paint({ compact = false } = {}) {
    const wasCompact = root.classList.contains('is-compact');
    const before = root.nextElementSibling?.getBoundingClientRect().top;
    const compensate = wasCompact && motion.visible && window.scrollY > flowStart() + 24;
    root.classList.toggle('is-hidden', !motion.visible);
    root.classList.toggle('is-scrolled', window.scrollY > flowStart() + 8);
    if (motion.visible) root.classList.remove('is-compact');
    else if (compact) root.classList.add('is-compact');
    reveal.hidden = motion.visible;
    collapse.setAttribute('aria-expanded', String(motion.visible));
    // Move focus out before making the header inaccessible.
    if (!motion.visible && surface.contains(document.activeElement)) reveal.focus({ preventScroll: true });
    surface.inert = !motion.visible;
    surface.setAttribute('aria-hidden', String(!motion.visible));
    // Expanding a manually collapsed header must not move the user's reading position.
    if (compensate && before != null) {
      const delta = root.nextElementSibling.getBoundingClientRect().top - before;
      window.scrollBy(0, delta);
      motion.sync(window.scrollY);
    }
    geometry();
  }

  function show(focusHeader = false) {
    clearTimeout(revealTimer);
    revealTimer = 0;
    if (dialogOpen()) return;
    motion.show();
    paint();
    if (focusHeader) collapse.focus({ preventScroll: true });
  }

  collapse.addEventListener('click', () => {
    clearTimeout(revealTimer);
    revealTimer = 0;
    motion.hide();
    paint({ compact: window.scrollY <= flowStart() + 24 });
    motion.sync(window.scrollY);
  });
  reveal.addEventListener('click', () => show(true));
  // Real pointer movement, not pointerenter: hiding under a stationary mouse must
  // not immediately re-open the header and create a scroll/hover loop.
  reveal.addEventListener('pointermove', event => {
    if (event.pointerType === 'mouse' && !motion.visible && !revealTimer) {
      // Brief intent delay also lets an actual click land on the reveal button.
      revealTimer = setTimeout(() => show(), 150);
    }
  });
  reveal.addEventListener('pointerleave', () => { clearTimeout(revealTimer); revealTimer = 0; });
  document.addEventListener('keydown', event => {
    if (event.key === 'Tab') keyboardNavigation = true;
  }, true);
  document.addEventListener('pointerdown', () => { keyboardNavigation = false; }, true);
  surface.addEventListener('focusin', () => {
    if (keyboardNavigation) show();
  });
  window.addEventListener('scroll', () => {
    if (scrollFrame) return;
    scrollFrame = requestAnimationFrame(() => {
      scrollFrame = 0;
      motion.scroll(window.scrollY, {
        canHide: !dialogOpen() && !(keyboardNavigation && surface.contains(document.activeElement)),
        hideAfter: flowStart() + surface.offsetHeight
      });
      paint();
    });
  }, { passive: true });
  window.addEventListener('hashchange', () => show());
  window.addEventListener('resize', geometry, { passive: true });
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(geometry).observe(root);
  paint();
})();
