/* Shared read-only image workspace. Reference pages are never output versions. */
const materialGroups = {
  teacher: '老师参考PPT', versions: '本页版本', ppt: 'PPT设计参考', web: '网页参考',
  branding: '品牌素材', background: '背景素材', component: '组件', illustration: '插图与装饰'
};
function referencePageTitle(state, deck, page, pageId) {
  const bindings = deck.page_bindings ||
    (state.reference_decks || []).find(x => x.id === deck.id)?.page_bindings || {};
  const matches = (state.pages || state.proposal?.pages || []).filter(pg =>
    (!pageId || pg.page_id === pageId) && (bindings[pg.page_id] || []).includes(page.number));
  const clean = value => String(value || '').replace(/^源?第\s*\d+\s*页\s*[·:：|｜—-]?\s*/, '').trim();
  const section = matches.length === 1 ? clean(matches[0].title) || clean(matches[0].chapter) : '';
  return section || clean(page.title) || `源第 ${page.number} 页`;
}
function referenceMaterials(state, pageId) {
  return (state.reference_decks || []).flatMap(deck => (deck.page_previews || [])
    .filter(page => !pageId || (deck.page_bindings?.[pageId] || []).includes(page.number))
    .map(page => ({ key: `${deck.id}:${page.number}`, group: 'teacher', id: deck.id,
      number: page.number, title: referencePageTitle(state, deck, page, pageId),
      subtitle: deck.original_name || deck.title || '',
      url: page.image_url, native_text: page.native_text || [], note: page.note || '' })));
}
function proposalMaterials(state) {
  const group = { deck: 'ppt', slide: 'ppt', webpage: 'web', brand: 'branding', icon: 'branding',
    background: 'background', header: 'component', footer: 'component', navigation: 'component' };
  return [...referenceMaterials(state), ...(state.reference_assets || []).map(x => ({
    ...x, key: `${x.id}:${x.version}`, group: group[x.kind] || 'illustration',
    subtitle: ({ proposal: '适配提案', selected: '项目选用', reference: '页面参考',
      recommended: '项目参考', related: '同套系素材' })[x.origin] || '素材库'
  }))];
}
function pageMaterials(pg, state) {
  const actual = pg.selected ? [{ ...pg.selected, selected: true }] : [];
  actual.push(...(pg.candidates || []).slice().reverse());
  return [...actual.filter(x => x.url).map((x, i) => ({
    key: `${pg.page_id}:${x.selected ? 'selected' : x.id}`, group: 'versions', page_id: pg.page_id,
    candidate_id: x.selected ? '' : x.id, title: x.selected ? '当前选定' : `候选 ${x.id || i + 1}`,
    subtitle: ({ generated: '模型生成', agent_composite: '合成', user_import: '本机回传',
      mock: '排版示意', reference: '参考图' })[x.kind] || '导入图片',
    url: x.url + (x.url.includes('?') ? '&' : '?') + 'v=' + encodeURIComponent(x.sha256 || '')
  })), ...referenceMaterials({ ...state, pages: [pg] }, pg.page_id),
  ...proposalMaterials(state).filter(x => (x.page_ids || []).includes(pg.page_id))];
}
function materialDescription(item) {
  return [item.title, item.subtitle, item.group === 'teacher' ? `源第 ${item.number} 页` : '']
    .filter(Boolean).join(' · ');
}
function materialStage(item, scope) {
  if (!item) return '';
  return `<div class="material-stage">
    <button type="button" class="material-image" data-action="material-fullscreen" data-scope="${esc(scope)}" aria-label="放大 ${esc(item.title)}"><img src="${esc(item.url)}" alt="${esc(item.title)}" decoding="async"></button>
    <span class="material-badge">${esc(materialGroups[item.group])}${item.number ? ' · ' + item.number : ''}</span>
    <button type="button" class="material-expand" data-action="material-fullscreen" data-scope="${esc(scope)}" aria-label="全屏预览 ${esc(item.title)}" title="全屏预览">⛶</button>
  </div><div class="material-caption"><strong title="${esc(materialDescription(item))}">${esc(item.title)}</strong><span>${esc(item.subtitle || '')}</span>${item.group === 'teacher' ? `<button class="material-detail" type="button" data-action="reference-deck-preview" data-id="${esc(item.id)}" data-start-page="${item.number}">整份PPT ↗</button>` : item.version ? `<button class="material-detail" type="button" data-action="preview-version" data-id="${esc(item.id)}" data-version="${esc(item.version)}">素材详情 ↗</button>` : ''}</div>`;
}
function renderMaterialViewer(scope, items, options = {}) {
  if (!items.length) return '';
  const vertical = !!options.vertical, activeGroup = options.group || items[0].group;
  const shown = options.all ? items : items.filter(x => x.group === activeGroup);
  const selected = shown.find(x => x.key === options.key) || shown[0];
  const groups = [...new Set(items.map(x => x.group))];
  return `<section class="material-viewer ${vertical ? 'is-vertical' : 'is-horizontal'}" data-material-scope="${esc(scope)}">
    ${vertical ? `<nav class="material-tabs" aria-label="材料分类">${groups.map(g => `<button type="button" data-action="material-group" data-scope="${esc(scope)}" data-group="${g}" aria-pressed="${g === activeGroup}">${materialGroups[g]}</button>`).join('')}</nav>` : ''}
    <div class="material-content"><div class="material-main">${materialStage(selected, scope)}</div>
    <nav class="material-rail" aria-label="${vertical ? '材料缩略图' : '参考与版本历史'}">${shown.map(item => `<button type="button" data-action="material-select" data-scope="${esc(scope)}" data-key="${esc(item.key)}" title="${esc(materialDescription(item))}" aria-pressed="${item.key === selected?.key}" aria-label="${esc(materialGroups[item.group] + ' · ' + item.title + (item.group === 'teacher' ? ' · 源第 ' + item.number + ' 页' : ''))}"><img src="${esc(item.url)}" alt="" loading="lazy"><span>${esc(item.title)}</span>${!vertical ? `<small>${esc(materialGroups[item.group])}</small>` : ''}</button>`).join('')}</nav></div>
  </section>`;
}
if (typeof module !== 'undefined' && module.exports) module.exports = {
  materialGroups, referencePageTitle, referenceMaterials, proposalMaterials, pageMaterials, materialStage, renderMaterialViewer
};
