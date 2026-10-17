/* Editable working text, read-only source previews. No approval or generation actions. */
function storyboardField(pg, key, label, value, rows = 2) {
  const id = 'story-' + pg.page_id + '-' + key;
  return `<label class="story-field"><span>${esc(label)}</span><textarea id="${esc(id)}" rows="${rows}" spellcheck="false">${esc(value ?? '')}</textarea></label>`;
}
function storyboardEvidence(pg, state) {
  const rows = Array.isArray(pg.logic?.evidence) ? pg.logic.evidence : [];
  if (!rows.length) return '';
  return `<div class="story-evidence">${rows.map((item, i) => {
    const ident = item?.source || item?.reference_id;
    const ref = (state.content_sources || []).find(r => r.id === ident);
    if (!ident || !item.paragraph_ids?.length) return `<span class="story-empty">${esc(typeof item === 'string' ? item : item?.note || '材料待关联')}</span>`;
    return `<button type="button" data-action="page-evidence" data-page="${esc(pg.page_id)}" data-index="${i}" title="打开引用段落"><span>${esc(ref?.original_name || '原稿段落')}</span><small>${item.paragraph_ids.length} 段 ↗</small></button>`;
  }).join('')}</div>`;
}
function storyboardRemarks(pg, state) {
  if (Object.hasOwn(pg, 'remarks')) return pg.remarks ?? '';
  const refs = (state.reference_decks || []).flatMap(r => (r.page_bindings?.[pg.page_id] || [])
    .map(n => ({ deck: r, page: (r.page_previews || []).find(p => p.number === n) })).filter(x => x.page));
  // Editable copy only: original source text remains in the pinned reference preview.
  return refs.flatMap(({ page }) => page.native_text || []).join('\n');
}
function storyboardScript(pg) {
  const sources = pg.script_sources || [], hasDraft = Boolean(pg.speaker_notes);
  const paragraphs = sources.flatMap(s => s.paragraphs || []);
  return `<section class="story-script" data-script-page="${esc(pg.page_id)}">
    <header><h4>讲稿 <small data-script-label>${hasDraft ? '草稿' : '原稿'}</small></h4>${paragraphs.length ? `<button type="button" data-action="script-edit" data-page="${esc(pg.page_id)}" ${hasDraft ? 'hidden' : ''}>编辑</button>` : ''}</header>
    <div class="story-script-source" ${hasDraft ? 'hidden' : ''}>${paragraphs.map(p => `<p data-script-paragraph title="${esc(p.citation)}">${esc(p.text)}</p>`).join('')}${sources.some(s => s.availability === 'unavailable' || s.missing_paragraph_ids?.length) ? '<p class="story-empty">部分原稿待核对</p>' : ''}</div>
    <div class="story-script-editor" ${!hasDraft && paragraphs.length ? 'hidden' : ''}>${storyboardField(pg, 'speaker_notes', '本页讲稿', pg.speaker_notes, 5)}</div>
  </section>`;
}
function renderStoryboardPage(pg, state, choice = {}) {
  const l = pg.logic || {};
  const materials = pageMaterials(pg, state);
  const roles = { cover: '封面', content: '内容页', closing: '尾页', transition: '过渡页', agenda: '目录' };
  return `<article class="story-page" id="storyboard-${esc(pg.page_id)}">
    <header class="story-page-head"><span class="page-id">${esc(pg.page_id)}</span>
      <label class="story-title"><span class="sr-only">${esc(pg.page_id)} 页面标题</span><input id="story-${esc(pg.page_id)}-title" aria-label="${esc(pg.page_id)} 页面标题" value="${esc(pg.title || '')}"></label>
      <span class="story-role">${esc(roles[pg.page_role] || pg.page_role || '内容页')}</span>
      <label class="story-duration"><span class="sr-only">${esc(pg.page_id)} 预计秒数</span><input id="story-${esc(pg.page_id)}-duration_seconds" type="number" min="0" step="1" aria-label="${esc(pg.page_id)} 预计秒数" value="${esc(l.duration_seconds ?? '')}"><span>秒</span></label>
    </header><div class="story-page-body"><div class="story-copy">
      ${storyboardField(pg, 'page_text', '页面文字 · 可编辑草稿', pg.page_text, 5)}
      <div class="story-two">${storyboardField(pg, 'purpose', '本页目的', l.purpose)}${storyboardField(pg, 'key_message_or_question', '结论 / 核心问题', l.key_message_or_question)}</div>
      ${storyboardField(pg, 'visual_expression', '视觉表达', l.visual_expression)}
      <section class="story-teacher-notes">${storyboardField(pg, 'remarks', '备注', storyboardRemarks(pg, state), 3)}</section>
      <details class="story-details"><summary>衔接与组织细节</summary><div class="story-two">${storyboardField(pg, 'transition_in', '前页衔接', l.transition_in)}${storyboardField(pg, 'transition_out', '转往后页', l.transition_out)}</div><div class="story-two">${storyboardField(pg, 'information_relationship', '信息关系', l.information_relationship)}${storyboardField(pg, 'chapter', '所属章节', pg.chapter, 2)}</div></details>
      ${storyboardEvidence(pg, state)}
    </div><aside class="story-materials" aria-label="${esc(pg.page_id)} 参考与支撑材料">
      ${renderMaterialViewer(pg.page_id, materials, { all: true, ...choice })}
      ${storyboardScript(pg)}
    </aside></div></article>`;
}
function readStoryboardPages(pages, read, state = {}) {
  return pages.map(original => {
    const pg = structuredClone(original);
    for (const key of ['title', 'chapter', 'page_text', 'purpose', 'key_message_or_question',
      'visual_expression', 'transition_in', 'transition_out', 'information_relationship', 'duration_seconds', 'speaker_notes', 'remarks']) {
      const value = read('story-' + pg.page_id + '-' + key);
      if (value === undefined || value === null) continue;
      const top = ['title', 'chapter', 'page_text', 'speaker_notes', 'remarks'].includes(key);
      const old = key === 'remarks' ? storyboardRemarks(original, state) : top ? original[key] : original.logic?.[key];
      if (String(old ?? '') === value) continue;
      if (top) pg[key] = value;
      else {
        pg.logic ||= {};
        pg.logic[key] = key === 'duration_seconds' ? (value.trim() ? Number(value) : null) : value;
        if (key === 'visual_expression') pg.layout_focus = value;
      }
    }
    return pg;
  });
}
if (typeof module !== 'undefined' && module.exports) module.exports = {
  renderStoryboardPage, readStoryboardPages, storyboardField, storyboardRemarks, storyboardEvidence, storyboardScript
};
