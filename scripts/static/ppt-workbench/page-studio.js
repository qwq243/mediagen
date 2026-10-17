/* A page is the working unit. References, output versions and approval stay distinct. */
const studioRealKinds = new Set(['generated', 'agent_composite', 'user_import']);
function studioPageTitle(pg) {
  return pg.page_role === 'cover' ? '封面' : pg.page_role === 'closing' ? '致谢与收束' : pg.title || pg.chapter || pg.page_id;
}
function studioOutputVersions(pg) {
  return [...(pg.selected && studioRealKinds.has(pg.selected.kind) ? [{ ...pg.selected, studioKey: 'selected', isSelected: true }] : []),
    ...(pg.candidates || []).slice().reverse().filter(x => studioRealKinds.has(x.kind) &&
      !(pg.selected && x.status === 'adopted' && x.sha256 && x.sha256 === pg.selected.sha256))
      .map(x => ({ ...x, studioKey: x.id }))];
}
function studioPageStatus(pg) {
  if (pg.selected && studioRealKinds.has(pg.selected.kind))
    return pg.selected.audit_status === 'passed' ? { key: 'selected', label: '已选用' } : { key: 'review', label: '待复核' };
  return studioOutputVersions(pg).length ? { key: 'review', label: '待选用' } : { key: 'empty', label: '待创作' };
}
function studioPages(state, draft = {}) {
  const working = draft.pages || state.proposal?.pages || state.pages;
  return state.pages.map(pg => ({ ...pg, ...working.find(x => x.page_id === pg.page_id),
    selected: pg.selected, candidates: pg.candidates, script_sources: pg.script_sources }));
}
function readStudioPages(original, draft, read, state) {
  // Unmounted pages retain their saved edits. A revert changes only the mounted field.
  const pages = original.map(pg => (draft.pages || []).find(x => x.page_id === pg.page_id) || pg);
  return readStoryboardPages(pages, read, state);
}
function studioUrl(x) { return x.url + (x.url.includes('?') ? '&' : '?') + 'v=' + encodeURIComponent(x.sha256 || ''); }
// These are reversible views of existing proposal fields, not additional sources of truth.
const studioInstructionMarkers = {
  remarks: '\n\n【本轮修改意见】\n',
  visual_expression: '\n\n【本页设计调整】\n'
};
function studioInstructionParts(value, key) {
  const text = String(value ?? ''), marker = studioInstructionMarkers[key], index = text.indexOf(marker);
  return index < 0 ? { base: text, adjustment: '' } :
    { base: text.slice(0, index), adjustment: text.slice(index + marker.length) };
}
function studioJoinInstructions(base, adjustment, key) {
  return String(base ?? '') + (adjustment ? studioInstructionMarkers[key] + adjustment : '');
}
function studioAdjustment(pg, key, label, value, placeholder) {
  const parts = studioInstructionParts(value, key);
  return `<label class="story-field studio-adjustment"><span>${esc(label)}</span><textarea
    data-studio-adjustment="${esc(key)}" data-page="${esc(pg.page_id)}" rows="3" spellcheck="false"
    placeholder="${esc(placeholder)}">${esc(parts.adjustment)}</textarea></label>`;
}
function studioPageRail(pages, active) {
  return `<aside class="studio-page-rail"><header><strong>整套页面</strong><span>${pages.length} 页</span></header>
    <nav class="studio-page-nav" aria-label="整套页面导航">${pages.map((p, i) => {
      const status = studioPageStatus(p);
      const image = p.selected && studioRealKinds.has(p.selected.kind) ? p.selected : null;
      return `<button data-action="studio-page" data-page="${esc(p.page_id)}"
        aria-current="${p.page_id === active ? 'page' : 'false'}"
        aria-label="第 ${i + 1} 页 ${esc(studioPageTitle(p))} · ${status.label}"
        title="${esc(p.title || p.chapter || p.page_id)} · ${status.label}">
        <span class="studio-page-thumb">${image ? `<img src="${esc(studioUrl(image))}" alt="" loading="lazy" decoding="async">` :
          `<span class="studio-thumb-placeholder">${status.key === 'review' ? '待选用' : '暂无成图'}</span>`}</span>
        <span class="studio-nav-number">${String(i + 1).padStart(2, '0')}<small class="state-${status.key}">${status.label}</small></span>
        <strong>${esc(studioPageTitle(p))}</strong></button>`;
    }).join('')}</nav></aside>`;
}
function studioOutput(pg, state, key) {
  const versions = studioOutputVersions(pg), x = versions.find(v => v.studioKey === key) || versions[0];
  if (!x) return `<div class="studio-empty-canvas"><span class="canvas-corner c1"></span><span class="canvas-corner c2"></span><span class="canvas-corner c3"></span><span class="canvas-corner c4"></span><div><span class="studio-canvas-symbol" aria-hidden="true">＋</span><h3>${esc(studioPageTitle(pg))}，还没有成图</h3><p>先对齐内容与参考，再制作这一页。</p><button data-action="studio-mode" data-mode="references">查看本页参考 ↗</button></div><small>${esc(pg.page_id)} · 16:9 创作画布</small></div><div class="studio-history-empty"><span>版本历史</span>首版制作后在这里保留，修改不覆盖旧图。</div>`;
  const audit = x.audit_status === 'passed' ? '审核通过' : x.audit_status === 'stale' ? '审核已失效' : '待独立审核';
  return `<div class="studio-output-stage"><button data-action="studio-enlarge" data-page="${esc(pg.page_id)}" data-key="${esc(x.studioKey)}" aria-label="全屏查看当前成图"><img src="${esc(studioUrl(x))}" alt="${esc(studioPageTitle(pg))} 当前成图"></button><span class="studio-output-badge">${x.isSelected ? '当前选用' : '候选版本'} · ${audit}</span><button class="studio-expand" data-action="studio-enlarge" data-page="${esc(pg.page_id)}" data-key="${esc(x.studioKey)}" aria-label="放大成图">⛶</button></div>
    <nav class="studio-history" aria-label="本页成图历史">${versions.map((v, i) => `<button data-action="studio-version" data-key="${esc(v.studioKey)}" aria-pressed="${v.studioKey === x.studioKey}"><img src="${esc(studioUrl(v))}" alt=""><span>${v.isSelected ? '当前选用' : '候选 ' + (versions.length - i)}</span><small>${v.audit_status === 'passed' ? '审核通过' : '待复核'}</small></button>`).join('')}</nav>
    <div class="studio-version-actions"><button data-action="annotate" data-page="${esc(pg.page_id)}" data-id="${x.isSelected ? '' : esc(x.id)}">圈画修改</button><button data-action="recipe-page" data-page="${esc(pg.page_id)}" data-id="${x.isSelected ? '' : esc(x.id)}">制作记录</button>${x.isSelected ? '<span class="studio-selected-note">已选用此版</span>' : `<button class="primary" data-action="adopt" data-page="${esc(pg.page_id)}" data-id="${esc(x.id)}" ${x.audit_status !== 'passed' || state.pending?.length ? 'disabled' : ''} title="独立审核通过并对齐待处理修改后，可选用此版">选用此版</button>`}</div>`;
}
function renderPageStudio(state, options = {}) {
  const pages = studioPages(state, options.draft), pg = pages.find(p => p.page_id === options.pageId) || pages[0];
  if (!pg) return '<div class="empty">先在完整方案中安排页面。</div>';
  const index = pages.indexOf(pg), status = studioPageStatus(pg), l = pg.logic || {};
  const refs = pageMaterials(pg, state).filter(x => x.group !== 'versions');
  const mode = options.mode || 'output';
  return `<section class="page-studio" data-studio-page="${esc(pg.page_id)}">
    <header class="studio-heading"><div><span class="eyebrow">03 / PAGE STUDIO</span><h1>逐页创作</h1></div><a href="#deck">下一步：整套统稿 →</a></header>
    <div class="studio-workspace">
    <div class="studio-sheet"><header class="studio-sheet-head"><div><span class="studio-page-index">${String(index + 1).padStart(2, '0')}</span><div><small>${esc(pg.chapter || '页面设计')} / ${pages.length} 页</small><h2>${esc(studioPageTitle(pg))}</h2></div></div><span class="studio-status state-${status.key}"><i></i>${status.label}</span></header>
    <div class="studio-columns"><section class="studio-copy" aria-label="本页内容与设计">
      <div class="studio-section-label"><strong>页面内容</strong><a href="#stage2">与 02 共用草稿 ↗</a></div>
      ${storyboardField(pg, 'page_text', '上屏文字', pg.page_text, 7)}
      <section class="studio-design-adjustments"><h3>本页设计</h3>
        <p class="studio-field-help">整套风格沿用完整方案；这里只补充这一页的调整。</p>
        ${studioAdjustment(pg, 'visual_expression', '本页设计调整 · 可用中文', l.visual_expression || pg.layout_focus,
          '例如：左侧教学、右侧科研；标题缩小，两组内容等宽。')}</section>
      <section class="studio-remarks">
        ${studioAdjustment(pg, 'remarks', '本轮修改意见 · 老师意见与待改事项', storyboardRemarks(pg, state),
          '例如：按老师最新意见改第二行，不改其他页面。')}
      </section>
      <details class="studio-detail"><summary>页面目标与衔接</summary>
        ${storyboardField(pg, 'title', '小节名称', pg.title, 1)}
        ${storyboardField(pg, 'purpose', '本页目的', l.purpose, 2)}
        ${storyboardField(pg, 'key_message_or_question', '核心结论', l.key_message_or_question, 2)}
        ${storyboardField(pg, 'transition_in', '前页衔接', l.transition_in, 2)}
        ${storyboardField(pg, 'transition_out', '转往后页', l.transition_out, 2)}
      </details><details class="studio-detail studio-provenance"><summary>讲稿依据与已存备注</summary>
        ${storyboardEvidence(pg, state)}
        <h4>已存备注与决策</h4><p class="studio-stored-copy" data-studio-base="remarks">${esc(studioInstructionParts(storyboardRemarks(pg, state), 'remarks').base || '尚无已存备注')}</p>
        <textarea id="story-${esc(pg.page_id)}-remarks" hidden aria-label="完整备注">${esc(storyboardRemarks(pg, state))}</textarea>
      </details><details class="studio-detail studio-advanced"><summary>高级 · 完整设计要求与全局参数</summary>
        <p class="studio-field-help">以下是与 02 共用的完整设计要求；当前成图的实际请求见右侧「制作记录」。</p>
        ${storyboardField(pg, 'visual_expression', '完整设计要求', l.visual_expression || pg.layout_focus, 5)}
        <div class="studio-advanced-links"><a href="#components">全局设计与组件 ↗</a><a href="#design-spec">设计规格工具 ↗</a></div>
      </details>
    </section><div class="studio-resizer" data-studio-resizer role="separator" tabindex="0" aria-label="调整编辑区宽度" aria-orientation="vertical" aria-valuemin="280" aria-valuemax="500" aria-valuenow="340" title="拖动，或按左右方向键调整编辑区宽度"></div>
    <section class="studio-visual" aria-label="本页视觉工作区">
      <div class="studio-visual-toolbar"><nav aria-label="视觉材料类型"><button data-action="studio-mode" data-mode="output" aria-pressed="${mode === 'output'}">本页成图 <small>${studioOutputVersions(pg).length}</small></button><button data-action="studio-mode" data-mode="references" aria-pressed="${mode === 'references'}">参考资料 <small>${refs.length}</small></button></nav><button class="studio-upload" data-action="upload-page" data-page="${esc(pg.page_id)}">导入成图 ↑</button></div>
      ${mode === 'references' ? `<div class="studio-reference-area">${refs.length ? renderMaterialViewer('reference:' + pg.page_id, refs, { vertical: true, ...(options.referenceChoice || {}) }) : '<div class="studio-reference-empty">本页暂未关联参考资料</div>'}<p class="studio-reference-caption">仅作参照 · 不计入成图版本</p></div>` : studioOutput(pg, state, options.versionKey)}
      ${storyboardScript(pg)}
    </section></div>
    <footer class="studio-footer"><div class="studio-save-copy"><span class="form-save-state" data-autosave-status role="status"></span><small>保存不改变已有成图</small></div><div><button data-action="studio-save">保存草稿</button><button class="primary" data-action="studio-handoff" data-page="${esc(pg.page_id)}">复制本页需求 ↗</button></div></footer>
    <textarea id="stage-comment" hidden aria-label="整套对齐意见">${esc(options.draftComment || '')}</textarea>
    </div>${studioPageRail(pages, pg.page_id)}</div>
    <p class="studio-handoff-help">修改后：保存草稿 → 复制本页需求 → 回到 Codex 对齐 → 确认生成范围与预算 → 审核并选用。</p></section>`;
}
function renderDeckOverview(state, draft = {}) {
  const pages = studioPages(state, draft), total = pages.length;
  const counts = pages.reduce((r, p) => { r[studioPageStatus(p).key]++; return r; }, { empty: 0, review: 0, selected: 0 });
  const seconds = pages.reduce((n, p) => n + (Number(p.logic?.duration_seconds) || 0), 0);
  return `<section class="deck-overview"><header class="studio-heading"><div><span class="eyebrow">04 / DECK REVIEW</span><h1>整套统稿</h1></div><button data-action="present-project">整套预览 ↗</button></header>
    <div class="deck-summary"><div><strong>${total}</strong><span>总页数</span></div><div><strong>${counts.selected}<small> / ${total}</small></strong><span>已选用</span></div><div><strong>${counts.review}</strong><span>待选用 / 复核</span></div><div><strong>${counts.empty}</strong><span>待创作</span></div><div><strong>${seconds}<small> 秒</small></strong><span>计划讲述时长</span></div></div>
    <div class="deck-section-heading"><h2>整套页面</h2><span>点击任意一页，回到逐页创作</span></div>
    <div class="deck-contact-sheet">${pages.map((pg, i) => {
      const s = studioPageStatus(pg), image = pg.selected && studioRealKinds.has(pg.selected.kind) ? pg.selected : null;
      return `<button class="deck-page-card" data-action="studio-open" data-page="${esc(pg.page_id)}" aria-label="编辑第 ${i + 1} 页 ${esc(studioPageTitle(pg))}"><div class="deck-page-image">${image ? `<img src="${esc(studioUrl(image))}" alt="${esc(studioPageTitle(pg))}" loading="lazy">` : `<div class="deck-page-placeholder"><span>${String(i + 1).padStart(2, '0')}</span><strong>${esc(studioPageTitle(pg))}</strong><small>${s.key === 'review' ? '已有候选，待选用' : '尚无成图'}</small></div>`}<span class="deck-card-number">${String(i + 1).padStart(2, '0')}</span></div><div class="deck-card-copy"><h3>${esc(studioPageTitle(pg))}</h3><div><span class="studio-status state-${s.key}"><i></i>${s.label}</span><small>${Number(pg.logic?.duration_seconds) || 0} 秒</small></div></div></button>`;
    }).join('')}</div><aside class="deck-review-note"><strong>统稿看三件事</strong><span>风格是否统一</span><span>内容是否重复或遗漏</span><span>讲述衔接与总时长</span></aside></section>`;
}
function studioHandoffText(state, pg) {
  return `请对齐本项目「${state.project}」的 ${pg.page_id}「${studioPageTitle(pg)}」，当前方案 v${state.revision}。

页面文字：
${pg.page_text || ''}

设计要求：
${pg.logic?.visual_expression || pg.layout_focus || ''}

备注 / 老师意见：
${storyboardRemarks(pg, state)}

本页讲稿：
${pg.speaker_notes || (pg.script_sources || []).flatMap(s => s.paragraphs || []).map(p => p.text).join('\n')}

只处理这一页，保留其他页与已有版本。读取项目中已固定版本的本页参考、最新草稿和批注；先核对待处理修改及生成条件，未经本次明确确认不要付费生成。`;
}
function syncStudioAdjustment(target) {
  const root = target.closest('.page-studio');
  if (!root) return;
  if (target.matches('[data-studio-adjustment]')) {
    const canonical = document.getElementById('story-' + target.dataset.page + '-' + target.dataset.studioAdjustment);
    const parts = studioInstructionParts(canonical.value, target.dataset.studioAdjustment);
    canonical.value = studioJoinInstructions(parts.base, target.value, target.dataset.studioAdjustment);
  } else if (target.id?.endsWith('-visual_expression')) {
    const field = root.querySelector('[data-studio-adjustment="visual_expression"]');
    if (field) field.value = studioInstructionParts(target.value, 'visual_expression').adjustment;
  }
}
function restoreStudioAdjustments() {
  const root = document.querySelector('.page-studio');
  if (!root) return;
  root.querySelectorAll('[data-studio-adjustment]').forEach(field => {
    const parts = studioInstructionParts(document.getElementById('story-' + field.dataset.page + '-' + field.dataset.studioAdjustment).value, field.dataset.studioAdjustment);
    field.value = parts.adjustment;
    const base = root.querySelector('[data-studio-base="' + field.dataset.studioAdjustment + '"]');
    if (base) base.textContent = parts.base || '尚无已存备注';
  });
}
function sizeStudioFields() {
  document.querySelectorAll('.page-studio textarea:not([hidden])').forEach(field => {
    if (field.closest('details:not([open])') || !field.getClientRects().length) return;
    field.style.height = 'auto';
    field.style.height = field.scrollHeight + 2 + 'px';
  });
}
function sizeStudioLayout() {
  const workspace = document.querySelector('.studio-workspace');
  if (!workspace) return;
  workspace.style.setProperty('--studio-height', Math.max(320, window.innerHeight - workspace.getBoundingClientRect().top - 48) + 'px');
  const columns = workspace.querySelector('.studio-columns'), handle = workspace.querySelector('[data-studio-resizer]');
  if (window.innerWidth > 1150) {
    let saved;
    try { saved = Number(localStorage.getItem('mediagen-studio-editor-width')); } catch (_) {}
    const max = Math.max(280, Math.min(500, columns.clientWidth - 310));
    const width = Math.min(max, Math.max(280, saved || 340));
    columns.style.setProperty('--studio-copy-width', width + 'px');
    handle.setAttribute('aria-valuemax', String(max));
    handle.setAttribute('aria-valuenow', String(width));
  }
  sizeStudioFields();
}
function positionStudioPageRail() {
  const nav = document.querySelector('.studio-page-nav'), current = nav?.querySelector('[aria-current="page"]');
  if (!current) return;
  // Scroll only the rail, never the whole document or its sticky toolbar.
  const parent = nav.getBoundingClientRect(), child = current.getBoundingClientRect();
  if (child.top < parent.top) nav.scrollTop += child.top - parent.top;
  else if (child.bottom > parent.bottom) nav.scrollTop += child.bottom - parent.bottom;
}
if (typeof document !== 'undefined') {
  document.addEventListener('toggle', event => {
    if (event.target.matches?.('.page-studio details') && event.target.open) sizeStudioFields();
  }, true);
  window.addEventListener('resize', () => { sizeStudioLayout(); positionStudioPageRail(); });
  document.addEventListener('keydown', event => {
    if (event.target.matches('.studio-page-nav button') && ['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const buttons = [...event.target.parentElement.querySelectorAll('button')], index = buttons.indexOf(event.target);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
        Math.max(0, Math.min(buttons.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
      if (next !== index) buttons[next].click();
    }
    if (event.target.matches('[data-studio-resizer]') && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const handle = event.target, current = Number(handle.getAttribute('aria-valuenow'));
      const width = event.key === 'Home' ? 280 : event.key === 'End' ? Number(handle.getAttribute('aria-valuemax')) :
        current + (event.key === 'ArrowRight' ? 20 : -20);
      setStudioEditorWidth(handle, width);
    }
  });
  document.addEventListener('pointerdown', event => {
    const handle = event.target.closest('[data-studio-resizer]');
    if (!handle || event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX, startWidth = Number(handle.getAttribute('aria-valuenow'));
    handle.setPointerCapture(event.pointerId);
    handle.classList.add('is-dragging');
    const move = e => setStudioEditorWidth(handle, startWidth + e.clientX - startX);
    const stop = () => {
      handle.classList.remove('is-dragging');
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', stop);
      handle.removeEventListener('pointercancel', stop);
      handle.removeEventListener('lostpointercapture', stop);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
    handle.addEventListener('lostpointercapture', stop);
  });
}
function setStudioEditorWidth(handle, value) {
  const width = Math.max(280, Math.min(Number(handle.getAttribute('aria-valuemax')), value));
  handle.parentElement.style.setProperty('--studio-copy-width', width + 'px');
  handle.setAttribute('aria-valuenow', String(width));
  try { localStorage.setItem('mediagen-studio-editor-width', String(width)); } catch (_) {}
  sizeStudioFields();
}
if (typeof module !== 'undefined' && module.exports) module.exports = {
  studioPageTitle, studioPageStatus, studioOutputVersions, studioPages, readStudioPages,
  renderPageStudio, renderDeckOverview, studioHandoffText, studioInstructionParts, studioJoinInstructions
};
