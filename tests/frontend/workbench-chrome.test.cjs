const test = require('node:test');
const assert = require('node:assert/strict');
const { createChromeMotion, getAlignmentStatus } = require('../../scripts/static/ppt-workbench/workbench-chrome.js');

test('alignment status is absent when there is nothing to align', () => {
  const status = getAlignmentStatus([], [{ id: 'stage1', status: 'active' }], 'stage1');
  assert.equal(status.visible, false);
  assert.equal(status.count, 0);
});

test('pending edits are condensed into a counted toolbar entry', () => {
  const pending = Array.from({ length: 7 }, () => ({ status: 'submitted' }));
  const status = getAlignmentStatus(pending, [{ id: 'stage1', status: 'active' }], 'stage1');
  assert.equal(status.label, '待对齐');
  assert.equal(status.count, 7);
  assert.match(status.description, /7 项修改/);
  assert.equal(status.visible, true);
});

test('historical stages still show a realignment entry without pending edits', () => {
  const status = getAlignmentStatus([], [{ id: 'samples', status: 'revision_required' }], 'samples');
  assert.equal(status.visible, true);
  assert.equal(status.recheck, true);
  assert.equal(status.label, '待重新对齐');
  assert.match(status.description, /本阶段/);
});

test('pending and historical warnings share one status', () => {
  const status = getAlignmentStatus([{}], [{ id: 'samples', status: 'revision_required' }], 'samples');
  assert.equal(status.label, '待对齐');
  assert.equal(status.count, 1);
  assert.match(status.description, /本阶段/);
});

test('an unrelated historical stage does not flag the current resource page', () => {
  const status = getAlignmentStatus([], [{ id: 'samples', status: 'revision_required' }], 'assets');
  assert.equal(status.visible, false);
});

test('starts expanded and ignores small scroll noise', () => {
  const motion = createChromeMotion();
  assert.equal(motion.visible, true);
  motion.scroll(240);
  assert.equal(motion.visible, false);
  motion.scroll(237);
  motion.scroll(239);
  assert.equal(motion.visible, false);
});

test('does not hide while the header is still at the start of the page', () => {
  const motion = createChromeMotion();
  motion.scroll(20);
  motion.scroll(60);
  assert.equal(motion.visible, true);
});

test('downward travel hides and deliberate upward travel reveals', () => {
  const motion = createChromeMotion(180);
  motion.scroll(198);
  assert.equal(motion.visible, true);
  motion.scroll(216);
  assert.equal(motion.visible, false);
  motion.scroll(210);
  assert.equal(motion.visible, false);
  motion.scroll(201);
  assert.equal(motion.visible, true);
});

test('manual collapse stays collapsed at the top until revealed', () => {
  const motion = createChromeMotion();
  motion.hide();
  motion.scroll(0);
  motion.scroll(5);
  assert.equal(motion.visible, false);
  motion.show();
  assert.equal(motion.visible, true);
});

test('keyboard focus or an open dialog can prevent automatic hiding', () => {
  const motion = createChromeMotion();
  motion.scroll(250, { canHide: false });
  assert.equal(motion.visible, true);
  motion.scroll(290);
  assert.equal(motion.visible, false);
});

test('returning to the top reveals and ignores negative overscroll', () => {
  const motion = createChromeMotion(300);
  motion.hide();
  motion.scroll(0);
  assert.equal(motion.visible, true);
  motion.scroll(-15);
  motion.scroll(0);
  assert.equal(motion.visible, true);
});

test('layout compensation can sync position without triggering a direction change', () => {
  const motion = createChromeMotion(200);
  motion.hide();
  motion.sync(350);
  motion.scroll(346);
  assert.equal(motion.visible, false);
  motion.scroll(336);
  assert.equal(motion.visible, true);
});

test('hover or click reveal resets the previous scroll travel', () => {
  const motion = createChromeMotion(300);
  motion.hide();
  motion.show();
  motion.scroll(310);
  assert.equal(motion.visible, true);
  motion.scroll(334);
  assert.equal(motion.visible, false);
});
