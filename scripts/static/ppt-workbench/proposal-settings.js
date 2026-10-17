/* One stage2 configuration, edited in Components and only displayed in the overview.
   Browser edits remain recoverable drafts until Agent alignment, never approvals. */
'use strict';
const paletteLabels={primary:'主色',accent:'强调色',background:'背景色',text:'正文色',muted:'辅助文字',border:'边框色',surface:'卡片底色',secondary_bg:'次级背景色'};
const typeLabels={display:'封面 / 展示',heading:'标题',title:'标题',subtitle:'副标题',body:'正文',numbers:'数字',caption:'注释',annotation:'注释'};
const readingLabels={presentation:'现场讲述：简洁，细节进讲稿',balanced:'兼顾讲述与阅读',text:'独立阅读：信息更完整'};
const routeLabels={full_image:'整页直接生图（默认）',agent_composite:'我提要求，由 Agent 合成',external:'导出素材，我在本机制作后回传'};
const notesLabels={optimize:'优化现有讲稿（默认）',generate:'生成完整分页讲稿',preserve:'逐字保留原稿',off:'不生成讲稿'};
const globalSettingKeys=['design','communication','production_route','notes_policy','transition','component_pack'];
function settingsDraft(){return formAutosave?.getPatch('stage2')||{}}
function displayedProposal(){return {...S.proposal,...settingsDraft()}}
function hasSettingsDraft(){const p=settingsDraft();return globalSettingKeys.some(k=>Object.hasOwn(p,k))}
function notesChoice(p){return p.notes_policy.enabled?p.notes_policy.mode:'off'}
function settingOptions(labels,selected){return Object.entries(labels).map(([k,v])=>`<option value="${k}" ${selected===k?'selected':''}>${esc(v)}</option>`).join('')}
function settingSelect(label,id,labels,value){return `<label class="field">${esc(label)}<select id="${id}">${settingOptions(labels,value)}</select></label>`}
function globalSettingsSummary(){
  const p=displayedProposal(),d=p.design,t=p.transition,pack=p.component_pack;
  return `<section class="scheme-settings" aria-label="当前全局配置"><div class="row between"><strong>当前全局配置</strong><small>${hasSettingsDraft()?'草稿 · 待对齐':'与全局设计同步'}</small></div>
    <button class="scheme-setting-row" data-action="proposal-details" data-kind="design" aria-haspopup="dialog"><span><b>视觉与组件</b><span class="scheme-mini-palette" aria-hidden="true">${Object.values(d.palette||{}).filter(v=>/^#[a-f0-9]{3,8}$/i.test(v)).slice(0,7).map(v=>`<i style="background:${v}"></i>`).join('')}</span><small>${esc(d.typography.heading)} 标题 / ${esc(d.typography.body)} 正文 · ${pack.enabled?'统一组件已启用':'统一组件未启用'}</small></span><em>详情 ↗</em></button>
    <button class="scheme-setting-row" data-action="proposal-details" data-kind="production" aria-haspopup="dialog"><span><b>制作与交付</b><small>${esc(routeLabels[p.production_route]||p.production_route)} · ${esc(roleNames[d.human_policy]||d.human_policy)}<br>${esc(notesLabels[notesChoice(p)]||notesChoice(p))} · ${t.enabled?'淡化 '+esc(t.duration)+' 秒':'无翻页动效'}</small></span><em>详情 ↗</em></button></section>`;
}
function detailRows(rows){return `<dl class="settings-detail-list">${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v??'待补充')}</dd></div>`).join('')}</dl>`}
function globalSettingsDetails(kind){
  const p=displayedProposal(),d=p.design,pack=p.component_pack;
  const body=kind==='production'?detailRows([
    ['人物政策',roleNames[d.human_policy]||d.human_policy],
    ['文字量与阅读方式',readingLabels[p.communication.reading_mode]||p.communication.reading_mode],
    ['制作路线',routeLabels[p.production_route]||p.production_route],
    ['文字直接生成在图里',d.text_in_image?'是':'否'],
    ['AI 讲稿',notesLabels[notesChoice(p)]||notesChoice(p)],
    ['整页翻页动效',p.transition.enabled?'淡化 · '+p.transition.duration+' 秒 · 手动翻页':'关闭'],
    ['淡化时长（秒）',p.transition.duration]
  ]):`<h3>色彩与字体</h3>${detailRows([
    ...Object.entries(d.palette||{}).map(([k,v])=>[paletteLabels[k]||k,v]),
    ...['display','heading','body','numbers'].map(k=>[(typeLabels[k]||k)+'字体',d.typography[k]]),
    ...Object.entries(d.typography.sizes||{}).map(([k,v])=>[(typeLabels[k]||k)+'字号',v])
  ])}<h3>图标、材质与组件规则</h3>${detailRows([
    ['图标语言',d.icons],['材质语言',d.material],['网格与安全边距',d.grid],
    ['统一页眉页脚 / 导航组件',pack.enabled?'已启用':'尚未启用'],
    ['章节顺序',(pack.chapters||[]).join(' → ')||'待补充'],
    ['组件适配提案',d.component_proposal?.title?d.component_proposal.title+' · 待对齐':'暂无'],
    ['已选组件数量',(pack.items||[]).length]
  ])}`;
  return `<p class="caption">${hasSettingsDraft()?'当前草稿 · 待与 Agent 对齐，尚未采纳':'当前方案配置'}。此处只读展示；具体参数统一在「全局设计与组件」中调整。</p>${body}<div class="actions"><button class="primary" data-action="configure-global" data-kind="${kind==='production'?'production':'design'}">前往全局设计与组件</button></div>`;
}
function globalSettingsView(){
  // Render the aligned base; the shared autosave restores the exact editable draft.
  const p=S.proposal,d=p.design,c=p.communication,t=p.transition,n=p.notes_policy;
  return `<div id="global-settings"><p class="caption">色彩、字体、组件规则与交付参数统一在这里配置；完整方案只展示摘要和只读详情。修改自动保存为同一份方案草稿，仍需与 Agent 对齐。</p><div class="two global-settings-grid">
    <section class="panel" id="global-visual"><span class="eyebrow">01 / VISUAL SYSTEM</span><h2>视觉样式与组件规则</h2>${swatches(d.palette)}
    <div class="two">${Object.entries(d.palette).filter(([,v])=>/^#[a-f0-9]{6}$/i.test(v)).map(([k,v])=>field(paletteLabels[k]||k,'palette-'+k,v,'color')).join('')}</div>
    ${field('封面 / 展示字体','font-display',d.typography.display)}${field('标题字体','font-heading',d.typography.heading)}${field('正文字体','font-body',d.typography.body)}
    <div class="type-sample" style="font-family:${font(d.typography.display)}">${esc(S.project)}</div><p style="font-family:${font(d.typography.body)}">正文示例：${esc(S.pages[0]?.page_text?.split('\n').find(x=>x.trim())||'清楚表达每一页，让内容与设计相互支持。')}</p><small style="font-family:${font(d.typography.numbers)}">数字角色 0123456789</small>
    <div class="two">${Object.entries(d.typography.sizes||{}).map(([k,v])=>field((typeLabels[k]||k)+'字号','size-'+k,v,'number')).join('')}</div><small>这里展示本机字体示例；模型生成的实际字形仍需样张核对。</small>
    <h3>图标、材质与网格</h3>${field('图标语言','icons',d.icons)}${field('材质语言','material',d.material,'textarea')}${field('网格与安全边距','grid',d.grid,'textarea')}
    <h3>统一组件规则</h3><label><input id="components-enabled" type="checkbox" ${p.component_pack.enabled?'checked':''}> 使用统一页眉页脚 / 导航组件</label>
    ${field('章节顺序（逗号分隔）','chapters',p.component_pack.chapters.join('，'))}<small>具体组件适配、适用页面、变式与局部留空见下方；页码、标题和当前章节随页序计算。</small></section>
    <section class="panel" id="global-production"><span class="eyebrow">02 / PRODUCTION & DELIVERY</span><h2>制作与交付配置</h2>
    ${settingSelect('人物政策','human_policy',roleNames,d.human_policy)}
    ${settingSelect('文字量与阅读方式','reading_mode',readingLabels,c.reading_mode)}
    ${settingSelect('制作路线','production_route',routeLabels,p.production_route)}
    <p><label><input id="text_in_image" type="checkbox" ${d.text_in_image?'checked':''}> 文字直接生成在图里</label></p>
    ${settingSelect('AI 讲稿','notes_mode',notesLabels,n.enabled?n.mode:'off')}
    <p><label><input id="transition-enabled" type="checkbox" ${t.enabled?'checked':''}> 开启整页翻页动效</label></p>
    ${field('淡化时长（秒）','transition-duration',t.duration||.4,'number')}<small>默认关闭；开启推荐 0.4 秒、手动翻页、无声音。不是图内文字逐条出现。</small>
    <div class="motion" id="motion">下一页 · 动效示意</div><button data-action="motion">预览淡化</button></section></div>
    <section class="panel"><div class="row between"><h3>全局配置补充意见</h3><span class="form-save-state" data-autosave-status role="status"></span></div><textarea id="stage-comment" aria-label="全局配置补充意见" placeholder="与完整方案共用的补充意见"></textarea><div class="actions"><button data-action="draft" data-stage="stage2">保存草稿</button><button data-action="submit" data-stage="stage2">提交给 Agent</button><a class="button" href="#stage2">返回完整方案查看</a></div><p class="caption">保存不等于确认，不会自动生成或替换组件。</p></section></div>`;
}
function globalSettingsPatch(){
  const original=S.proposal,result={},d=structuredClone(original.design);
  for(const k of ['icons','material','grid','human_policy'])if($('#'+k))d[k]=$('#'+k).value;
  for(const k of ['display','heading','body'])if($('#font-'+k))d.typography[k]=$('#font-'+k).value;
  for(const k in d.palette)if($('#palette-'+k)){const value=$('#palette-'+k).value;if(value.toLowerCase()!==String(d.palette[k]).toLowerCase())d.palette[k]=value}
  for(const k in d.typography.sizes)if($('#size-'+k))d.typography.sizes[k]=Number($('#size-'+k).value);
  if($('#text_in_image'))d.text_in_image=$('#text_in_image').checked;
  result.design=d;
  if($('#reading_mode'))result.communication={...original.communication,reading_mode:$('#reading_mode').value};
  if($('#production_route'))result.production_route=$('#production_route').value;
  if($('#notes_mode')){const mode=$('#notes_mode').value;result.notes_policy={...original.notes_policy,enabled:mode!=='off',mode:mode==='off'?'optimize':mode}}
  if($('#transition-enabled')&&$('#transition-duration'))result.transition={...original.transition,enabled:$('#transition-enabled').checked,duration:Number($('#transition-duration').value),advance:'manual'};
  if($('#components-enabled')&&$('#chapters'))result.component_pack={...original.component_pack,enabled:$('#components-enabled').checked,chapters:$('#chapters').value.split(/[,，]/).map(x=>x.trim()).filter(Boolean)};
  return Object.fromEntries(Object.entries(result).filter(([k,v])=>JSON.stringify(v)!==JSON.stringify(original[k])));
}
