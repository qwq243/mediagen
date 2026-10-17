(() => {
'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let app=null, controller=null, searchController=null, mountVersion=0, taxonomy=null;
let libraryState={}, libraryOffset=0, draftDirty=false, rawDraftDirty=false, searchTimer=null;
const pendingGets=new Map();
let csrf='',mode='library',data=null,detail=null,selected=null,design=null,pageId='',tab='overview',compiled=null,lane='samples',dict={},resolved={};
let searchVersion=0,renderVersion=0;
function notice(t){window.dispatchEvent(new CustomEvent('workbench:notice',{detail:t}))}
async function api(url,body,signal=controller?.signal){
 if(signal?.aborted)throw new DOMException('Navigation cancelled','AbortError');
 const pending=pendingGets.get(url);
 if(body===undefined&&pending&&!pending.signal?.aborted)return pending.promise;
 const call=(async()=>{const r=await fetch(url,{signal,...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Mediagen-CSRF':csrf},body:JSON.stringify(body)}:{})});
 const x=await r.json();if(signal?.aborted)throw new DOMException('Navigation cancelled','AbortError');
 if(!r.ok)throw new Error(x.error||JSON.stringify(x));if(x.csrf)csrf=x.csrf;
 if(body&&!url.endsWith('/preview')&&!url.endsWith('/borrow-preview'))window.dispatchEvent(new Event('workbench:changed'));
 return x})();
 if(body===undefined)pendingGets.set(url,{promise:call,signal});
 try{return await call}finally{if(pendingGets.get(url)?.promise===call)pendingGets.delete(url)}
}
function label(code){return dict[code]||code}
const kinds={background:'背景',title:'标题',text:'文字',card:'卡片',icon:'图标',image:'图片',chart:'图表',table:'表格',brand:'品牌标识',navigation:'导航',page_number:'页码',arrow:'箭头',decoration:'装饰',contamination:'截图污染'};
function kindLabel(code){return kinds[code]||code}
function tokenSummary(token){
 const value=token.value,type=token.type;
 if(type==='typography')return `${label(value.class)} · ${value.family||'字体文件未核实'} · ${value.size_px}px · 字重${value.weight} · 行高${value.line_height}`;
 if(type==='shadow')return `偏移 ${value.x_px},${value.y_px}px · 模糊 ${value.blur_px}px · ${value.color} · 透明度 ${value.opacity}`;
 if(type==='gradient')return `${value.kind==='linear'?'线性':'径向'}渐变 · ${value.angle_deg??'未知'}° · ${value.stops.length}个色标`;
 return typeof value==='object'?JSON.stringify(value):String(value);
}
function download(value,name){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}
function activate(which){mode=which}
async function library(){
 activate('library');
 app.innerHTML=`<section class="intro"><div><div class="eyebrow">DESIGN KNOWLEDGE / 01</div><h1>找到图片背后的设计方法</h1><p class="muted">作品、页面、区域、元素与关系。保留原图、出处和未知项。</p></div><span class="badge">候选标注不会覆盖原标签</span></section>
 <div class="warning" id="coverage">正在读取标注覆盖状态…</div>
 <form class="filters" id="search"><input id="q" aria-label="组合检索" placeholder="例如：红金非遗 三栏 顶部章节导航"><button class="primary">检索</button><div class="filter-options">
 ${['deck','role','layout','relation','font'].map((x,i)=>`<label>${['作品','页型','布局','关系','字型（非字体名猜测）'][i]}<select name="${x}"><option value="">全部</option></select></label>`).join('')}
 <label>可信度<select name="status"><option value="">含候选</option><option value="reviewed">已复核</option><option value="suggested">待复核</option></select></label>
 <label>用途<select name="usage"><option value="">结构参考及待确认</option><option value="reusable">已授权可复用</option></select></label>
 <label>对象<select name="kind"><option value="">全部</option>${['title','card','icon','arrow','brand','image','navigation','contamination'].map(x=>`<option value="${x}">${kindLabel(x)}</option>`).join('')}</select></label>
 <label><input type="checkbox" name="alpha">透明素材</label></div></form>
 <div class="examples">${['蓝白医疗 毛笔标题 封面','红金非遗 三栏 顶部章节导航','学术汇报 研究背景','蓝白商务 流程'].map(x=>`<button data-query="${esc(x)}">${esc(x)}</button>`).join('')}</div>
 <div id="results-count"></div><div id="results" class="grid"></div><div class="footer-actions"><button id="previous" hidden>上一页</button><button id="more" hidden>下一页</button></div>`;
 $('#search').onsubmit=e=>{e.preventDefault();clearTimeout(searchTimer);search(0).catch(error)};
 $('#q').oninput=e=>{if(e.isComposing)return;clearTimeout(searchTimer);searchTimer=setTimeout(()=>search(0).catch(error),300)};
 $('#q').oncompositionend=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>search(0).catch(error),300)};
 $('#search').onchange=e=>{if(e.target.id==='q')return;clearTimeout(searchTimer);search(0).catch(error)};
 document.querySelectorAll('[data-query]').forEach(b=>b.onclick=()=>{clearTimeout(searchTimer);$('#q').value=b.dataset.query;search(0).catch(error)});
 for(const [key,value] of Object.entries(libraryState)){const input=key==='q'?$('#q'):$('#search').elements[key];if(!input)continue;if(input.type==='checkbox')input.checked=value==='true';else if(input.tagName!=='SELECT'||Array.from(input.options).some(option=>option.value===value))input.value=value}
 await search(libraryOffset);
}
function error(e){if(e.name!=='AbortError'){if($('#results'))$('#results').setAttribute('aria-busy','false');notice(e.message||String(e))}}
async function search(offset){
 const requestVersion=++searchVersion;searchController?.abort();searchController=new AbortController();
 const signal=AbortSignal.any([controller.signal,searchController.signal]);
 $('#results-count').textContent='正在检索本机候选索引…';$('#results').setAttribute('aria-busy','true');
 const form=$('#search'),params=new URLSearchParams(new FormData(form));params.set('q',$('#q').value);params.set('offset',offset);
 if(form.elements.alpha.checked)params.set('alpha','true');else params.delete('alpha');
 if(offset===libraryOffset&&Object.keys(libraryState).length&&!data){for(const [k,v] of Object.entries(libraryState))params.set(k,v)}
 libraryState=Object.fromEntries(params);delete libraryState.offset;libraryOffset=offset;
 const response=await api('/api/v3/knowledge?'+params,undefined,signal);if(requestVersion!==searchVersion||mode!=='library')return;data=response;
 const c=data.coverage_summary;
 $('#coverage').textContent=c?`当前为 ${c.decks} 套 / ${c.pages} 页试点，不是全库重标结果。详细候选 ${c.detailed_candidates} 页 · 待精标 ${c.inventory_only} 页 · 独立复核 ${c.independently_reviewed} 页。候选不能冒充可直接复用的成品素材。`:'候选标注仍需独立复核。';
 for(const [key,values] of Object.entries(data.facets)){const el=form.elements[key],old=el.value;el.innerHTML='<option value="">全部</option>'+values.map(v=>`<option value="${esc(v)}">${esc(label(v))}</option>`).join('');el.value=libraryState[key]||old}
 $('#results-count').innerHTML=`<p class="muted">${data.total} 页匹配 · 每套优先展示一页 · ${data.items.length?offset+1:0}–${offset+data.items.length}</p>`;
 $('#results').innerHTML=data.items.length?data.items.map(a=>`<article class="card"><button data-open="${esc(a.asset_id)}" aria-label="查看 ${esc(a.page.title)}"><img src="${esc(a.preview_url)}" alt="${esc(a.page.title)}" loading="lazy"></button><div class="card-body">
 <small>${esc(a.deck.title)} · ${esc(a.page_id)}</small><h3>${esc(a.page.title)}</h3><div><span class="badge">${esc(label(a.page.role))}</span>${a.page.layout.map(v=>`<span class="badge">${esc(label(v))}</span>`).join('')}<span class="badge">${a.element_count} 个对象</span></div>
 <div class="quality"><span>图像：${a.quality.image.issues.length?'有遮挡/污染':'可参考，待复核'}</span><span>标注：${a.review.status==='reviewed'?'已独立复核':a.review.status==='rejected'?'复核退回':a.coverage.complete?'精标候选 / 待独立复核':'结构清单 / 待精标'}</span><span>用途：结构与外观参考</span><span>权限：${a.source.permissions.reuse==='approved'?'已授权':'未知，不可直接复用'}</span></div>
 ${a.issues.length?`<details><summary>来源与质量备注 ${a.issues.length}</summary><p>${a.issues.map(esc).join('<br>')}</p></details>`:''}
 <p class="match">${a.match_reasons.map(r=>esc(r.query)+' → '+esc(label(r.matched))).join(' · ')||'按套系分散展示'}</p></div></article>`).join(''):'<div class="empty">没有符合全部条件的标注。未知字段不会冒充精确匹配。</div>';
 $('#results').setAttribute('aria-busy','false');
 document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openDetail(b.dataset.open).catch(error));
 $('#previous').hidden=offset===0;$('#previous').onclick=()=>search(Math.max(0,offset-36)).catch(error);
 $('#more').hidden=!data.has_more;$('#more').onclick=()=>search(offset+36).catch(error);
}
async function openDetail(id){
 const [record,versions]=await Promise.all([api('/api/v3/knowledge/'+encodeURIComponent(id)),api(`/api/v3/knowledge/${id}/history`)]);detail=record;selected=detail.elements.find(x=>x.kind!=='background')?.id;
 $('#detail-title').textContent=detail.deck.title+' · '+detail.page.title;
 $('#detail-body').innerHTML=`<div class="inspect"><aside class="tree"><h3>元素树</h3><small>${esc(detail.page_id)} · ${detail.elements.length} 个对象</small><div id="tree"></div><button id="export-annotation">导出候选 JSON</button></aside>
 <section class="stage"><div class="row">${[['regions','区域框'],['boxes','元素框'],['reading','阅读顺序'],['connections','关系'],['align','对齐线']].map(([id,t])=>`<label><input type="checkbox" id="overlay-${id}" ${id==='boxes'?'checked':''}>${t}</label>`).join('')}</div>
 <div class="picture"><img src="${esc(detail.preview_url)}" alt="原图，保持原始坐标"><svg id="overlay" viewBox="0 0 ${detail.source.width} ${detail.source.height}" aria-label="元素标注"></svg></div>
 <div class="warning">${detail.coverage.complete?'候选完整，仍需独立复核':'当前为逐页结构盘点，复杂组件内部尚待精标。'}</div><small>原图 ${detail.source.width} × ${detail.source.height} · 坐标基于完整原图，而非裁切区域</small>
 <details><summary>页面关系与质量</summary><pre class="code">${esc(JSON.stringify({relations:detail.relations,quality:detail.quality,unknowns:detail.unknowns},null,2))}</pre></details></section><aside class="properties" id="properties"></aside></div>`;
 $('#export-annotation').onclick=()=>{const candidate=structuredClone(detail);delete candidate.annotation_hash;delete candidate.preview_url;candidate.review.status='suggested';candidate.review.independent_review=null;download(candidate,detail.page_id+'-candidate.json')};
 const history=document.createElement('details');history.innerHTML=`<summary>标注历史（${versions.versions.length}）</summary><select id="annotation-version" aria-label="历史标注版本">${versions.versions.map(v=>`<option value="${esc(v.annotation_hash)}" ${v.annotation_hash===versions.current?'selected':''}>${esc(v.annotation_hash.slice(0,10))} · ${v.element_count}对象</option>`).join('')}</select><input id="version-reason" aria-label="切换版本原因" placeholder="切换原因（必填）"><button id="choose-version">显式切换，不删除历史</button>`;
 $('#detail-body .tree').append(history);
 $('#choose-version').onclick=async()=>{try{await api(`/api/v3/knowledge/${id}/select-version`,{expected_hash:detail.annotation_hash,annotation_hash:$('#annotation-version').value,reason:$('#version-reason').value});$('#detail').close();await openDetail(id);notice('已切换候选版本，旧原图和标签保留')}catch(e){error(e)}};
 $('#detail-body').querySelectorAll('input[type=checkbox]').forEach(x=>x.onchange=drawDetail);
 if(!$('#detail').open)$('#detail').showModal();drawDetail();
}
function drawDetail(){
 const d=detail,w=d.source.width,h=d.source.height;
 function subtree(e,depth=0){return `<button data-element="${esc(e.id)}" style="margin-left:${Math.min(depth*9,35)}px;width:calc(100% - ${Math.min(depth*9,35)}px)" class="${e.id===selected?'active':''}">${esc(kindLabel(e.kind))} · ${esc(e.label)}</button>`+d.elements.filter(x=>x.parent_id===e.id).map(x=>subtree(x,depth+1)).join('')}
 $('#tree').innerHTML=d.regions.map(r=>`<details class="region-tree" open><summary>${esc({content:'内容区',title:'标题区',footer:'页脚区',visual:'主视觉区',navigation:'导航区'}[r.role]||r.role)} · ${esc(r.id)}</summary>${d.elements.filter(e=>!e.parent_id&&e.region_id===r.id).map(e=>subtree(e)).join('')}</details>`).join('');
 let svg='';
 function rect(b,attrs){return `<rect x="${b[0]*w}" y="${b[1]*h}" width="${b[2]*w}" height="${b[3]*h}" ${attrs}/>`}
 if($('#overlay-regions').checked)svg+=d.regions.map(r=>rect(r.bbox,'class="region-box"')).join('');
 if($('#overlay-boxes').checked)svg+=d.elements.filter(e=>e.kind!=='background').map(e=>rect(e.bbox,`data-id="${esc(e.id)}" class="${e.id===selected?'selected':''}"`)).join('');
 const e=d.elements.find(e=>e.id===selected);
 if($('#overlay-align').checked&&e){const b=e.bbox,cx=(b[0]+b[2]/2)*w,cy=(b[1]+b[3]/2)*h;svg+=`<line class="alignment" x1="${cx}" y1="0" x2="${cx}" y2="${h}"/><line class="alignment" x1="0" y1="${cy}" x2="${w}" y2="${cy}"/>`}
 if($('#overlay-reading').checked)svg+=d.page.reading_order.map((id,i)=>{const b=d.elements.find(e=>e.id===id)?.bbox;return b?`<text x="${b[0]*w+8}" y="${b[1]*h+25}">${i+1}</text>`:''}).join('');
 if($('#overlay-connections').checked){
 svg+='<defs><marker id="rel-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8" fill="#315d80"/></marker></defs>';
 svg+=d.relations.map(r=>{const a=d.elements.find(e=>e.id===r.from),b=d.elements.find(e=>e.id===r.to);return a&&b?`<line class="relation" ${['forward','bidirectional'].includes(r.direction)?'marker-end="url(#rel-arrow)"':''} ${['reverse','bidirectional'].includes(r.direction)?'marker-start="url(#rel-arrow)"':''} x1="${(a.bbox[0]+a.bbox[2]/2)*w}" y1="${(a.bbox[1]+a.bbox[3]/2)*h}" x2="${(b.bbox[0]+b.bbox[2]/2)*w}" y2="${(b.bbox[1]+b.bbox[3]/2)*h}"><title>${esc(r.type)} · ${esc(r.label||'无标签')}</title></line>`:''}).join('')}
 $('#overlay').innerHTML=svg;
 $('#detail-body').querySelectorAll('[data-element],[data-id]').forEach(b=>b.onclick=()=>{selected=b.dataset.element||b.dataset.id;drawDetail()});
 if(!e)return;
 const px=e.bbox.map((v,i)=>Math.round(v*(i%2?h:w)));
 $('#properties').innerHTML=`<h3>${esc(e.label)}</h3><span class="badge">${esc(kindLabel(e.kind))}</span><dl><dt>归一化坐标 / 原图像素</dt><dd>${e.bbox.join(', ')}<br>${px.join(', ')}</dd><dt>测量状态</dt><dd>${esc({estimated:'估计',measured:'测得',verified:'已核实',unknown:'未知',not_applicable:'不适用'}[e.geometry_status]||e.geometry_status)} · 以记录的观察依据为准</dd><dt>字体文件</dt><dd>${esc(e.observed.font_family?.value||'未知；不根据字形猜字体名')}</dd><dt>字型类别</dt><dd>${esc(label(e.observed.font_class?.value||'未知'))}</dd><dt>来源版本</dt><dd>${esc(d.source.version)}</dd><dt>原图 SHA-256</dt><dd>${esc(d.source.sha256)}</dd><dt>证据</dt><dd>${esc(e.evidence)}</dd></dl>
 <h3>只借指定方面</h3>${[['structure','结构'],['typography_appearance','字体外观'],['palette','色系'],['component','组件']].map(([p,t])=>`<button data-borrow="${p}" ${e.kind==='contamination'?'disabled':''}>借${t} → 待确认</button>`).join('')}
 <small>只加入项目请求；不上传图片，不改变已批准设计。</small><details><summary>全部参数（观察值）</summary><pre>${esc(JSON.stringify(e,null,2))}</pre></details>`;
 document.querySelectorAll('[data-borrow]').forEach(b=>b.onclick=async()=>{try{const p=await api('/api/v3/design-spec');await api(`/api/v3/knowledge/${d.asset_id}/borrow`,{revision:p.revision,annotation_hash:d.annotation_hash,element_id:e.id,purpose:b.dataset.borrow});notice('已加入待确认请求；到侧栏「设计规格与验收」查看参数提案。未上传或生成')}catch(err){error(err)}});
}
async function designView(){
 activate('design');draftDirty=false;rawDraftDirty=false;design=await api('/api/v3/design-spec');if(!design.pages.some(p=>p.id===pageId))pageId=design.pages[0]?.id||'';
 resolved=(await api('/api/v3/design-spec/preview',{revision:design.revision,spec:design.spec})).resolved;
 app.innerHTML=`<section class="intro"><div><div class="eyebrow">DESIGN CONTRACT / 02</div><h1>让设计要求清晰可检查</h1><p class="muted">结构化规格是唯一真值。整图模型按目标生成，再按容差验收。</p></div><span class="badge">${design.active?'已保存规格':'尚未启用原子化规格'}</span></section>
 ${design.validation_notice?`<div class="warning">${esc(design.validation_notice)}</div>`:''}
 ${design.warning?`<div class="warning">${esc(design.warning)}</div>`:''}
 <div class="row spread"><div class="row"><label>页面 <select id="page-choice">${design.pages.map(p=>`<option value="${esc(p.id)}" ${p.id===pageId?'selected':''}>${esc(p.id)} · ${esc(p.title)}</option>`).join('')}</select></label>
 <label>请求通道 <select id="lane"><option value="samples">代表样张（无额外风格锚点）</option><option value="deck">整套生产（首图为风格锚点）</option></select></label></div><button id="export-spec">导出设计规格</button></div>
 <p class="muted">这里展示下次请求的实际编译结果，不等于生成已获授权。执行仍受主工作流的当前确认、审核与预算约束。</p>
 <nav class="tabs">${[['overview','设计总览'],['structure','页面结构图'],['prompt','实际提示词'],['refs','实际参考图'],['audit','目标与成品']].map(([id,t])=>`<button data-tab="${id}" class="${tab===id?'active':''}">${t}</button>`).join('')}</nav><div class="work-panel" id="design-panel"></div>
 <details class="work-panel" style="margin-top:20px"><summary>高级：完整参数与继承（全局 → 页型 → 页面 → 元素）</summary><p>保存会显示受影响页面，并使旧确认失效。硬约束冲突会被拒绝；已冻结阈值不能在此放宽。</p><textarea class="spec-editor" id="spec-editor" aria-label="设计规格 JSON">${esc(JSON.stringify(design.spec,null,2))}</textarea><div class="row"><button id="save-spec" class="primary">校验并保存设计规格</button><span id="impact"></span></div></details>
 <details class="work-panel" style="margin-top:16px"><summary>资源借鉴与采用记录（${design.knowledge_requests.length}）</summary><div id="borrow-queue"></div></details>`;
 $('#lane').value=lane;$('#lane').onchange=()=>{lane=$('#lane').value;renderDesign().catch(error)};
 $('#page-choice').onchange=()=>{pageId=$('#page-choice').value;renderDesign().catch(error)};
 document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));renderDesign().catch(error)});
 $('#export-spec').onclick=()=>download(design.spec,'design-spec.json');
 $('#spec-editor').oninput=()=>{draftDirty=true;rawDraftDirty=true};$('#save-spec').onclick=saveSpec;renderBorrowQueue();await renderDesign();
}
function renderBorrowQueue(){
 const queue=$('#borrow-queue');
 queue.innerHTML=`<p>选中目标元素，先看转换提案，再明确确认。只转用有依据的参数；不复制参考文案、不猜字号、不上传图片。</p>${!design.active?'<div class="warning">请先补齐并确认项目设计规格。此处不会自动启用全套默认草案。</div>':''}`+
 design.knowledge_requests.map((r,i)=>`<article class="borrow-item" data-borrow-index="${i}"><h3>${esc(r.element_id)} · ${esc({structure:'结构',typography_appearance:'字体外观',palette:'色系',component:'组件'}[r.purpose]||r.purpose)}</h3><small>${esc(r.asset_id)} · ${esc(r.annotation_hash.slice(0,12))} · ${r.status==='applied_parameters_only'?'参数已采用；未授权生图':'待确认'}</small>
 ${r.status==='pending_user_and_agent_review'?`<div class="row"><label>目标页<select data-borrow-page>${design.pages.map(p=>`<option value="${esc(p.id)}" ${p.id===pageId?'selected':''}>${esc(p.id)}</option>`).join('')}</select></label><label>目标元素<select data-borrow-target></select></label><button data-borrow-preview ${design.active?'':'disabled'}>查看参数提案</button></div><div class="borrow-proposal"></div>`:`<p>已应用到 ${esc(r.applied_page)} / ${esc(r.applied_element)}；${esc(r.confirmation_reason)}</p>`}</article>`).join('')+
 `<details><summary>完整来源和处理记录</summary><pre class="code">${esc(JSON.stringify(design.knowledge_requests,null,2))}</pre></details>`;
 queue.querySelectorAll('[data-borrow-index]').forEach(row=>{
  const chooser=row.querySelector('[data-borrow-page]');if(!chooser)return;
  const options=()=>{row.querySelector('[data-borrow-target]').innerHTML=resolved[chooser.value].elements.map(e=>`<option value="${esc(e.id)}">${esc(e.id)} · ${esc(kindLabel(e.kind))}</option>`).join('');row.querySelector('.borrow-proposal').innerHTML=''};
  chooser.onchange=options;options();
  row.querySelector('[data-borrow-target]').onchange=()=>row.querySelector('.borrow-proposal').innerHTML='';
  row.querySelector('[data-borrow-preview]').onclick=async()=>{try{
   if(draftDirty)throw new Error('请先保存设计草案，再预览或采用资源参数，避免覆盖未保存修改。');
   const body={revision:design.revision,request_index:Number(row.dataset.borrowIndex),page_id:chooser.value,target_element_id:row.querySelector('[data-borrow-target]').value};
   const proposal=await api('/api/v3/knowledge/borrow-preview',body),host=row.querySelector('.borrow-proposal');
   host.innerHTML=`<div class="warning">${proposal.warnings.map(esc).join('<br>')}</div><pre class="code">${esc(JSON.stringify({changes:proposal.changes,source:proposal.source},null,2))}</pre><label>确认依据<input data-borrow-reason placeholder="已对照原图与目标页面，确认采用以上参数"></label><button class="primary" data-borrow-apply>确认采用参数（不生图）</button>`;
   host.querySelector('[data-borrow-apply]').onclick=async()=>{try{if(draftDirty)throw new Error('请先保存设计草案，再重新预览借鉴参数。');const result=await api('/api/v3/knowledge/borrow-apply',{...body,proposal_hash:proposal.proposal_hash,confirmation_reason:host.querySelector('[data-borrow-reason]').value.trim()});draftDirty=false;await designView();notice('参数已采用；受影响页面：'+result.affected_pages.join('、')+'。仍需主流程确认，未上传或生图。')}catch(e){error(e)}};
  }catch(e){error(e)}};
 });
}
async function saveSpec(){
 try{const spec=JSON.parse($('#spec-editor').value);const out=await api('/api/v3/design-spec',{revision:design.revision,spec});draftDirty=false;notice('已保存；受影响页面：'+out.affected_pages.join('、')+'。需重新确认。');await designView()}catch(e){error(e)}
}
async function renderDesign(){
 const version=++renderVersion;
 const panel=$('#design-panel'),spec=design.spec,pg=spec.pages[pageId],target=resolved[pageId];
 if(tab==='overview'){
 const tokens=target.tokens;
 panel.innerHTML=`<h2>色卡与角色参数</h2><p class="muted">先看关键约定；完整数值与继承规则在下方高级面板中保留。</p><div class="swatches">${Object.entries(tokens).map(([key,v])=>`<div class="swatch">${v.type==='color'&&/^#[0-9a-fA-F]{6}$/.test(v.value)?`<i style="background:${esc(v.value)}"></i>`:''}<span>${esc(key)}<br><small>${esc(tokenSummary(v))}</small></span></div>`).join('')||'<p class="muted">尚未定义类型化色卡；请从批准参考图确认。</p>'}</div><h3>必须遵守</h3><ul class="constraint-list">${Object.entries(spec.hard_constraints).map(([key,value])=>`<li>${esc({exact_text:'准确文案，不错字、不漏字',no_fake_evidence:'真实证据不得伪造',protect_identity_and_brands:'人物与品牌标识保护'}[key]||key)}<span>${value===true?'必须':esc(JSON.stringify(value))}</span></li>`).join('')}</ul><p class="muted">画布 ${spec.canvas.join(' × ')} · 坐标归一化 · 字体是外观目标，不是模型调用了该字体文件。</p><h3>验收容差</h3><div class="spec-metrics"><div><strong>≤ ${esc(Number((spec.tolerances.center_axis*100).toFixed(4)))}%</strong><span>中心位置：分别相对画布宽 / 高</span></div><div><strong>≤ ${esc(Number((spec.tolerances.relative_size*100).toFixed(4)))}%</strong><span>尺寸：相对目标宽 / 高</span></div><div><strong>ΔE00 ≤ ${esc(spec.tolerances.flat_delta_e00)}</strong><span>指定纯色取样区；不套用照片 / 阴影</span></div></div><p class="muted">这是验收约定，不是模型精确控制参数；文案与语义不允许错误，证据不足保持待核对。</p>`;
 const fonts=Object.entries(tokens).filter(([,v])=>v.type==='typography');
 panel.insertAdjacentHTML('beforeend',`<h3>角色字样 <span class="badge">浏览器示意，不是模型实测</span></h3><div class="font-samples">${fonts.map(([id,v])=>`<div><small>${esc(id)} · ${esc(label(v.value.class))} · 字体目标 ${esc(v.value.family||'仅外观类别')}</small><p data-font="${esc(id)}">见微知著 Aa 2026</p></div>`).join('')||'<p class="muted">未确认字体角色参数，不自动猜测。可在高级规格定义 typography 类型。</p>'}</div><h3>固定组件家族与背景</h3><div>${Object.keys(target.components||{}).map(id=>`<span class="badge">${esc(id)}</span>`).join('')||'<p class="muted">尚未定义固定组件。</p>'}</div><details><summary>查看固定外观、变量槽和背景的完整定义</summary><pre class="code">${esc(JSON.stringify({components:target.components,background:target.background},null,2))}</pre></details><h3>页型模板</h3><div>${Object.keys(spec.templates||{}).map(id=>`<span class="badge">${esc(id)}</span>`).join('')||'尚未定义；不自动套用外部模板'}</div>`);
 document.querySelectorAll('[data-font]').forEach(el=>{const v=tokens[el.dataset.font].value;el.style.fontSize=Math.min(v.size_px,72)+'px';el.style.fontWeight=String(v.weight);el.style.lineHeight=String(v.line_height);el.style.letterSpacing=v.letter_spacing_px+'px';if(v.family)el.style.fontFamily=v.family});
 }else if(tab==='structure'){
 const els=target.elements;
 panel.innerHTML=`<h2>页面结构示意 <span class="badge">不是生成样张</span></h2><p class="muted">点击元素查看并调整位置；保存前不会影响生产。</p><div class="schema-grid"><div class="schematic">${els.map(e=>`<button class="target" data-target="${esc(e.id)}" style="left:${e.bbox[0]*100}%;top:${e.bbox[1]*100}%;width:${e.bbox[2]*100}%;height:${e.bbox[3]*100}%">${esc(e.text||e.id)}</button>`).join('')}</div><div class="element-editor" id="element-editor">选择一个元素。高级面板可定义字体、固定组件、背景、关系与保护区。</div></div>`;
 document.querySelectorAll('[data-target]').forEach(b=>b.onclick=()=>{const e=els.find(x=>x.id===b.dataset.target);$('#element-editor').innerHTML=`<h3>${esc(e.id)}</h3><label>归一化 x,y,w,h<input id="bbox-edit" value="${e.bbox.join(',')}"></label><pre class="code">${esc(JSON.stringify(e,null,2))}</pre><button id="apply-box">更新草案（未保存）</button>`;
 $('#apply-box').onclick=async()=>{try{if(rawDraftDirty)throw new Error('高级参数有未保存修改，请先校验保存，再调整结构图。');const box=$('#bbox-edit').value.split(',').map(Number);if(box.length!==4||!box.every(Number.isFinite)||box[0]<0||box[1]<0||box[2]<=0||box[3]<=0||box[0]+box[2]>1||box[1]+box[3]>1){notice('请输入有效归一化坐标');return}
 if(!pg.elements)pg.elements=structuredClone(els).map(x=>{for(const key of ['pixels','center','center_pixels','aspect_ratio'])delete x[key];return x});
 draftDirty=true;pg.elements.find(x=>x.id===e.id).bbox=box;resolved=(await api('/api/v3/design-spec/preview',{revision:design.revision,spec})).resolved;$('#spec-editor').value=JSON.stringify(spec,null,2);await renderDesign();notice('草案已更新，点击下方“校验并保存”才生效')}catch(err){error(err)}}});
 }else{
 panel.innerHTML='<p>编译当前实际请求…</p>';const response=await api(`/api/v3/design-spec/${pageId}/compiled?lane=${lane}`);if(version!==renderVersion||mode!=='design')return;compiled=response;
 if(tab==='prompt')panel.innerHTML=`<div class="row spread"><h2>完整实际提示词</h2><button id="copy-prompt">复制提示词</button></div><small>请求指纹 ${esc(compiled.request_hash)} · ${esc(compiled.compiler_version)}</small><pre class="code">${esc(compiled.prompt)}</pre><h3>接口参数（与设计目标分开）</h3><pre class="code">${esc(JSON.stringify({api:compiled.api_parameters,fixed:compiled.api_fixed_parameters,reported_model:compiled.reported_model,seed:compiled.seed},null,2))}</pre>`;
 else if(tab==='refs')panel.innerHTML=`<h2>实际发送顺序</h2><p>此清单与生成器共用同一个输入解析器；查看不触发生图。未获入模批准的购物车素材不在这里。</p><div class="refs">${compiled.inputs.map(r=>`<article><strong>${r.order}. ${esc(r.id)}</strong><img src="${esc(r.preview_url)}" alt="第${r.order}张实际参考图" loading="lazy" decoding="async"><p>${esc(r.purpose)}</p><small>${esc(r.origin)} · 入模许可：项目已批准<br>版权：${esc(r.copyright_status)}<br>SHA-256 ${esc(r.sha256)}</small></article>`).join('')||'<p>当前请求无参考图，将使用纯文本生成。</p>'}</div><button id="export-request">导出完整请求清单</button>`;
 else panel.innerHTML=`<h2>目标规格 / 实际图片 / 偏差清单</h2>${compiled.output_url?`<img class="output-image" src="${esc(compiled.output_url)}" alt="当前采用成品">`:'<p class="empty">尚无采用成品。</p>'}<div class="warning">没有测量依据的项目保持“待核对”，不会自动判通过。</div><pre class="code">${esc(JSON.stringify(compiled.audit||{status:'pending',reason:'尚未提交绑定成品哈希的测量与视觉审核'},null,2))}</pre><details><summary>当前量化目标</summary><pre class="code">${esc(JSON.stringify(compiled.spec,null,2))}</pre></details><div id="audit-editor"></div>`;
 if($('#copy-prompt'))$('#copy-prompt').onclick=()=>navigator.clipboard.writeText(compiled.prompt).then(()=>notice('已复制实际提示词')).catch(error);
 if($('#export-request'))$('#export-request').onclick=()=>download(compiled,pageId+'-request.json');
 if(tab==='refs')panel.insertAdjacentHTML('beforeend',` <a class="button" href="/api/v3/design-spec/${encodeURIComponent(pageId)}/export?lane=${lane}">下载复现包 ZIP（含实际参考图）</a>`);
 if(tab==='audit')renderAudit();
 if(draftDirty)panel.insertAdjacentHTML('afterbegin','<div class="warning">此处为已保存规格的实际请求与验收目标；未保存草案尚未进入请求。请先在高级面板校验并保存。</div>');
 }
}
function renderAudit(){
 const host=$('#audit-editor');if(!compiled.spec||!compiled.output_sha256){host.innerHTML='<p>先保存并确认目标规格、采用成品，才可提交绑定哈希的偏差审核。</p>';return}
 const verdict=(id,label)=>`<label>${label}<select id="${id}"><option value="">待核对</option><option value="true">通过（已看图）</option><option value="false">不通过</option></select></label>`;
 host.innerHTML=`<h3>逐项录入实际观察</h3><p>坐标基于成品原图归一化。不要把目标值复制为测量值；未测量留空。</p>
 <div class="audit-table">${compiled.spec.elements.map((e,i)=>`<fieldset data-audit="${i}"><legend>${esc(e.id)} · ${esc(e.kind)}</legend><small>目标位置 ${e.bbox.join(', ')}${e.text?'<br>准确文案：'+esc(e.text):''}</small><label>实测 x,y,w,h<input data-field="bbox" placeholder="未测量"></label>
 ${'text'in e?`<label>逐字转录<textarea data-field="text"></textarea></label><label><input type="checkbox" data-field="text_verified">已对原图逐字核对</label><label>字体外观<select data-field="typography_matches"><option value="">待核对</option><option value="true">符合批准字样</option><option value="false">不符合</option></select></label>`:''}
 ${e.flat_color?'<label>实测平面颜色<input data-field="flat_color" placeholder="#RRGGBB"></label><label>取样区域<input data-field="sample_region" placeholder="x,y,w,h"></label><label>取样方法<input data-field="sample_method" placeholder="例如：指定无阴影区域的中位数"></label>':''}
 ${e.component?'<label>固定组件一致性<select data-field="component_matches"><option value="">待核对</option><option value="true">通过</option><option value="false">不通过</option></select></label>':''}</fieldset>`).join('')}</div>
 <div class="row">${compiled.spec.relations.length?verdict('audit-relations','节点与连线语义'):''}${verdict('audit-safety','遮挡与安全区')}${verdict('audit-hard','全部硬约束')}</div>
 <div class="row"><label>复核者<input id="audit-reviewer"></label><label>实际看图与测量依据<input id="audit-evidence" placeholder="原图观察位置、测量工具与方法"></label></div><button class="primary" id="submit-audit">提交偏差审核（不触发生图）</button>`;
 $('#submit-audit').onclick=async()=>{try{const measured={elements:{},reviewer:$('#audit-reviewer').value.trim(),evidence:$('#audit-evidence').value.trim()};if(!measured.reviewer||!measured.evidence)throw new Error('请填写复核者和实际证据');
 const choice=id=>$(id)?.value===''||!$(id)?null:$(id).value==='true';
 measured.safe_zones_and_occlusion_passed=choice('#audit-safety');measured.hard_constraints_passed=choice('#audit-hard');if($('#audit-relations'))measured.semantic_relations_match=choice('#audit-relations');
 document.querySelectorAll('[data-audit]').forEach(row=>{const e=compiled.spec.elements[Number(row.dataset.audit)],m={};row.querySelectorAll('[data-field]').forEach(input=>{const f=input.dataset.field;if(input.type==='checkbox'){m[f]=input.checked;return}if(!input.value.trim())return;if(input.tagName==='SELECT')m[f]=input.value==='true';else if(['bbox','sample_region'].includes(f))m[f]=input.value.split(',').map(Number);else m[f]=input.value});measured.elements[e.id]=m});
 const result=await api(`/api/v3/design-spec/${pageId}/audit`,{revision:design.revision,target_hash:compiled.spec.spec_hash,output_sha256:compiled.output_sha256,measured});design.revision=result.revision;notice('审核状态：'+result.report.status+'；未知项不会自动通过');await renderDesign()}catch(e){error(e)}};
}
function unmount(){
 ++mountVersion;++searchVersion;++renderVersion;clearTimeout(searchTimer);controller?.abort();searchController?.abort();pendingGets.clear();
 const dialog=$('#detail');if(dialog?.open)dialog.close();dialog?.remove();app=null;mode='';data=null;
}
async function mount(host,which,state){
 unmount();const version=mountVersion;controller=new AbortController();csrf=state.csrf;mode=which;
 host.innerHTML='<div class="knowledge-workspace"><div class="flow-context"><a href="#workflow">流程总览</a><span> / </span><a href="#assets">收集参考</a><span> → </span><a href="#knowledge">解析元素</a><span> → </span><a href="#design-spec">确认规格与验收</a><span> → </span><a href="#stage2">方案对齐</a></div><div id="knowledge-app"><p class="route-loading" role="status">正在读取本机设计资料…</p></div></div>';
 app=$('#knowledge-app');
 const dialog=document.createElement('dialog');dialog.id='detail';dialog.className='knowledge-workspace';dialog.setAttribute('aria-labelledby','detail-title');
 dialog.innerHTML='<div class="knowledge-dialog-top"><h2 id="detail-title"></h2><button id="close-detail" aria-label="关闭元素详情">×</button></div><div id="detail-body"></div>';
 document.body.append(dialog);$('#close-detail').onclick=()=>dialog.close();
 try{
 if(!taxonomy)taxonomy=await api('/api/v3/knowledge/taxonomy');
 if(version!==mountVersion)return;
 dict=Object.fromEntries(taxonomy.terms.map(x=>[x.id,x.prefLabel]));
 await (which==='design'?designView():library());
 }catch(e){if(e.name!=='AbortError'&&version===mountVersion){app.innerHTML='<div class="empty">读取失败：'+esc(e.message)+'<p>请使用顶栏刷新重试，已有项目未被覆盖。</p></div>';error(e)}}
}
window.PPTKnowledge={mount,unmount,hasDraft:()=>draftDirty,discardDraft:()=>{draftDirty=false}};
window.addEventListener('beforeunload',e=>{if(draftDirty){e.preventDefault();e.returnValue=''}});
})();
