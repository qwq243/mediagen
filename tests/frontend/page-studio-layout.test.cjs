const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

global.esc = x => String(x ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const root = path.join(__dirname, '../../scripts/static/ppt-workbench');
Object.assign(global, require(path.join(root, 'material-viewer.js')), require(path.join(root, 'storyboard.js')));
const ui = require(path.join(root, 'page-studio.js'));
function state() {
  const pages = [1, 2, 3].map(i => ({
    page_id: 'P0' + i, title: '页面' + i, page_role: 'content', page_text: '准确文字' + i,
    remarks: '已存决定：沿用原稿，保留来源。',
    logic: {visual_expression: 'Two panels; preserve the exact labels.', duration_seconds: 18},
    candidates: []
  }));
  pages[1].selected = {kind: 'generated', url: '/real.png', sha256: 'real', audit_status: 'passed'};
  pages[2].selected = {kind: 'reference', url: '/not-output.png', sha256: 'ref'};
  return {project: '测试项目', revision: 3, pages, proposal: {pages: structuredClone(pages)},
    pending: [], reference_assets: [], reference_decks: []};
}

test('page navigation is a right-hand thumbnail rail, never a reference disguised as output', () => {
  const html = ui.renderPageStudio(state(), {pageId: 'P02'});
  assert.ok(html.indexOf('studio-page-rail') > html.indexOf('studio-footer'));
  assert.match(html, /aria-label="整套页面导航"/);
  assert.equal((html.match(/data-action="studio-page"/g) || []).length, 3);
  assert.match(html, /class="studio-page-thumb"[^]*?src="\/real.png/);
  assert.doesNotMatch(html, /src="\/not-output.png/);
  assert.match(html, /aria-current="page"/);
  assert.match(html, /loading="lazy"/);
});

test('current requests are a lossless view of canonical remarks, not a second proposal field', () => {
  const old = '原作者备注\n2026-10-16 的风格决策 <保留>';
  assert.deepEqual(ui.studioInstructionParts(old, 'remarks'), {base: old, adjustment: ''});
  assert.equal(ui.studioJoinInstructions(old, '', 'remarks'), old);
  const joined = ui.studioJoinInstructions(old, '标题缩小，保留数字。', 'remarks');
  assert.deepEqual(ui.studioInstructionParts(joined, 'remarks'), {base: old, adjustment: '标题缩小，保留数字。'});
  assert.equal(ui.studioJoinInstructions(old, '', 'remarks'), old);
  assert.equal(ui.studioJoinInstructions('', '只改这页', 'remarks'), '\n\n【本轮修改意见】\n只改这页');
  // A marker supplied inside an adjustment stays literal user text.
  const nested = '保留原文\n\n【本轮修改意见】\n不要猜测';
  assert.deepEqual(ui.studioInstructionParts(ui.studioJoinInstructions(old, nested, 'remarks'), 'remarks'),
    {base: old, adjustment: nested});
});

test('Chinese adjustment fields preserve the original technical instructions exactly', () => {
  const s = state(), before = JSON.stringify(s);
  const html = ui.renderPageStudio(s, {pageId: 'P02'});
  assert.match(html, /本页设计调整/);
  assert.match(html, /本轮修改意见/);
  assert.match(html, /已存备注与决策/);
  assert.match(html, /完整设计要求/);
  assert.match(html, /data-studio-adjustment="visual_expression"/);
  assert.equal((html.match(/id="story-P02-visual_expression"/g) || []).length, 1);
  assert.equal((html.match(/id="story-P02-remarks"/g) || []).length, 1);
  assert.ok(html.indexOf('<details') < html.indexOf('Two panels; preserve the exact labels.'));
  assert.equal(before, JSON.stringify(s));
});

test('handoff and shared page draft retain both baseline and current instructions', () => {
  const s = state();
  const canonical = ui.studioJoinInstructions(s.pages[1].remarks, '老师要求改标题', 'remarks');
  const pages = ui.readStudioPages(s.proposal.pages, {}, id => id === 'story-P02-remarks' ? canonical : undefined, s);
  const handoff = ui.studioHandoffText(s, pages[1]);
  assert.match(handoff, /已存决定/);
  assert.match(handoff, /老师要求改标题/);
  assert.equal(s.pages[1].remarks, '已存决定：沿用原稿，保留来源。');
});

test('studio marks saving and copying as non-execution and preserves pending stage comment', () => {
  const s = state();
  const html = ui.renderPageStudio(s, {pageId: 'P02', draftComment: '整套已有意见'});
  assert.match(html, /复制本页需求/);
  assert.match(html, /回到 Codex/);
  assert.match(html, /保存不改变已有成图/);
  assert.match(html, /id="stage-comment"[^>]*>整套已有意见<\/textarea>/);
  assert.match(html, /data-studio-resizer/);
  assert.match(html, /role="separator"/);
});

test('instruction projection escapes author text, including closing textarea tags', () => {
  const s = state();
  s.proposal.pages[1].remarks = '</textarea><img src=x onerror=alert(1)>';
  const html = ui.renderPageStudio(s, {pageId: 'P02'});
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&lt;\/textarea&gt;/);
});

test('workflow uses one six-stage path with auxiliary tools and honest handoff boundaries', () => {
  const sandbox = {window: {}};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'workflow-guide.js'), 'utf8'), sandbox);
  const s = state();
  s.progress = ['stage1', 'stage2', 'samples', 'deck', 'delivery', 'feedback'].map((id, i) =>
    ({id, label: id, accessible: true, complete: i < 5, status: i < 5 ? 'completed' : 'active'}));
  const html = sandbox.window.renderWorkflowGuide(s);
  assert.equal((html.match(/class="workflow-card"/g) || []).length, 6);
  for (const text of ['同一份页面草稿', '03 → 04 → 05', '辅助工具', '回到 Codex', '不等于']) {
    assert.ok(html.includes(text), text);
  }
  assert.match(html, /未启用|启用状态/);
});
