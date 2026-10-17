'use strict';
let codingGroup='layout',componentSource=null,regionSession=null;
const codingGroups={layout:'空间布局',component:'固定组件',font_style:'字型与艺术字',role:'页面职责',relation:'信息关系',narrative:'整套叙事',density:'信息密度',material:'材质语言'};
const componentSlots={header:'顶部标题栏',footer:'页脚',navigation:'章节导航',brand:'品牌形象',progress:'进度',page_number:'页码'};
const componentScopes={all:'全套通用',content:'正文页',cover:'封面',divider:'章节过渡',closing:'尾页'};
async function codingView(){
  const [c,g]=await Promise.all([api('/api/v3/coding'),api('/api/v3/coding/examples?group='+codingGroup)]);
  return intro('REFERENCE LANGUAGE','看得见的编码，选得到的参考。','从本机已接入的图片中找图例。未复核的匹配会明确标出；可看大图、截取局部，再交给 Agent 按同一编码检索。')+
    `<div class="coding-stats">${[[c.pages,'已接入页面'],[c.decks,'套系'],[c.reviewed,'人工复核编码'],[c.missing_typography,'待补字体系']].map(([n,t])=>`<div><strong>${n}</strong><span>${t}</span></div>`).join('')}</div>
    <div class="code-tabs" role="tablist">${Object.entries(codingGroups).map(([k,v])=>`<button role="tab" aria-selected="${codingGroup===k}" class="${codingGroup===k?'active':''}" data-action="coding-group" data-group="${k}">${v}</button>`).join('')}</div>
    <div class="code-examples">${g.items.sort((a,b)=>Number(!a.matches)-Number(!b.matches)).map(item=>`<article class="code-example"><header><div><span class="eyebrow">${esc(item.code)}</span><h3>${esc(item.label)}</h3></div><span class="caption">${item.matches} 页</span></header>
      ${item.examples.length?`<div class="example-images">${item.examples.map(r=>`<button data-action="preview-version" data-id="${r.id}" data-version="${r.version}" title="查看、裁切或选用 ${esc(r.page_code)}"><img loading="lazy" src="${esc(r.preview_url)}" alt="${esc(r.title)}"><span>${esc(r.page_code)}<small>${r.status==='reviewed'?'已复核图例':'标签匹配 · 待复核'}</small></span></button>`).join('')}</div>`:'<div class="example-empty">暂无可靠图例<br><small>保留编码，待实际图片补充，不用示意图冒充。</small></div>'}
      ${codingGroup==='font_style'?'<p class="caption">图例展示字型特征，不等于已确认字体名称。</p>':''}</article>`).join('')}</div>
    <details class="panel"><summary>编码规则与整理交接</summary><p>DK：整套作品；PG：页面。页序独立，永久编号不随重排变化。</p><p>CMP：组件实例；TYP：角色字体系；PAL：实际色卡。精确字体、色值、组件坐标只采纳已核验记录，不据缩略图猜测。</p><p>Agent 可用 ppt_coding.py examples --group ${esc(codingGroup)} 获取同一组图例、原图路径、版本和复核状态。</p></details>`;
}
function componentsView(){
  const pack=S.proposal.component_pack,items=pack.items||[],pending=S.pending.filter(x=>['fixed_component','reserved_region','region_edit'].includes(x.kind));
  return intro('GLOBAL DESIGN & COMPONENTS','全局设计与组件','完整方案看整体方向；这里细化全局样式、制作交付、组件适配与局部留空，贯穿各制作阶段。')+
    globalSettingsView()+
    componentProposal(S.proposal.design)+
    `<div class="component-intro"><section class="panel"><span class="eyebrow">01 · 选择</span><h3>从局部细节开始</h3><p>在素材大图中截取喜欢的部分，再点击「选为固定组件」。封面、正文、过渡和尾页可以用不同变式。</p><a class="button" href="#assets">去素材库选择</a></section>
    <section class="panel"><span class="eyebrow">02 · 适配</span><h3>统一风格，不照搬文字</h3><p>标题、章节和页码随页面变化；固定的是装饰和视觉语言。变体先审核、再选定，不会自动替换旧图。</p><button data-action="brand-guide">独立制作品牌形象</button></section>
    <section class="panel"><span class="eyebrow">03 · 留空</span><h3>给后续编辑预留位置</h3><p>先选页面，再框定区域。可精确填色或挖透明，作为人工制作底板；已有图还可制作编辑蒙版。</p><div class="row"><select id="region-page-select" aria-label="选择留空页面">${S.pages.map(p=>`<option value="${p.page_id}">${esc(p.page_id+' '+(p.title||p.page_text.split('\n')[0]))}</option>`).join('')}</select><button data-action="new-region">设置区域</button></div></section></div>
    <section class="panel"><div class="row between"><h2>当前组件包</h2><span class="pill">${pack.enabled?'已启用':'尚未启用'}</span></div>${items.length?`<div class="component-list">${items.map(x=>`<div><img src="/api/assets/${x.asset_id}/preview?version=${x.version}" alt="${esc(x.title||'组件')}"><section><strong>${esc(componentSlots[x.slot])} · ${esc(componentScopes[x.scope])}</strong><p>${esc(x.title||x.asset_id)}</p><span class="caption">${x.mode==='composite'?'确定性合成 · 保留原像素':'参考融图 · 需视觉审核'}</span></section><button data-action="preview-version" data-id="${x.asset_id}" data-version="${x.version}">查看版本</button></div>`).join('')}</div>`:'<p class="muted">还没有选定固定组件。素材库里的选择先交给 Agent 对齐，再进入当前组件包。</p>'}</section>
    ${pending.length?`<section class="panel"><h2>待与 Agent 对齐 · ${pending.length}</h2>${pending.map(x=>`<div class="region-request"><strong>${esc(x.kind==='fixed_component'?componentSlots[x.details.slot]+' / '+componentScopes[x.details.scope]:x.details.page_id+' · '+(x.kind==='region_edit'?'编辑蒙版':'版式留空'))}</strong><p>${esc(x.details.instruction||x.details.region?.purpose||'按所选图片确认适用页面与风格。')}</p>${x.details.mask?`<a href="/api/v3/regions/${x.details.id}/mask" class="button">下载蒙版</a>`:''}<span class="caption">已记录，不等于执行或付费授权</span></div>`).join('')}</section>`:''}
    <section class="panel"><h2>当前页面留空安排</h2>${S.pages.filter(p=>p.reserved_regions?.length).map(p=>`<div class="region-request"><strong>${esc(p.page_id)}</strong>${p.reserved_regions.map(r=>`<p>${esc(r.purpose)} · ${esc(({prompt_only:'提示避让',solid:'精确填色',transparent:'透明底板',image:'导入图片 · 精确合成'})[r.mode])}</p>`).join('')}</div>`).join('')||'<p class="muted">尚未采纳留空安排。</p>'}</section>`;
}
async function chooseComponent(id,version){
  const r=await api('/api/v3/assets/'+id+'?version='+version);componentSource=r;
  modal('选择固定组件',`<div class="component-picker"><img src="/api/assets/${r.id}/preview?version=${r.version}" alt="${esc(r.title)}"><div><h3>${esc(r.title)}</h3><p>若只喜欢图中的一部分，建议先截取局部。此处只记录选择，随后回到 Codex 与 Agent 对齐。</p><div class="two"><label class="field">用于哪里<select id="component-slot">${Object.entries(componentSlots).map(([k,v])=>`<option value="${k}" ${k===r.kind?'selected':''}>${v}</option>`).join('')}</select></label><label class="field">适用页面<select id="component-scope">${Object.entries(componentScopes).map(([k,v])=>`<option value="${k}" ${k==='content'?'selected':''}>${v}</option>`).join('')}</select></label></div></div></div>
    <div class="component-strategies">${[['reference','参考融图','借鉴外观，按当前页面内容生成。'],['variant','先生成风格变体','以原素材为参考，适配当前色卡与材质后再选定。'],['composite','保留原像素合成','适合品牌标志等固定素材，摆放位置与 Agent 对齐。']].map(([k,t,d])=>`<label><input type="radio" name="component-strategy" value="${k}" ${k==='variant'?'checked':''}><strong>${t}</strong><span>${d}</span></label>`).join('')}</div>
    <div class="row between"><small>选定后仍需确认内容、位置与变体；不自动生成。</small><button class="primary" data-action="save-component">保存选择，交给 Agent</button></div>`);
}
function startRegion(pid,cid){
  const p=S.pages.find(x=>x.page_id===pid),im=cid?p.candidates.find(x=>x.id===cid):p.selected;
  regionSession={page_id:pid,candidate_id:cid||null,sha256:im?.sha256,box:null,start:null,embedded:null,embeddedPreview:null};
  modal('版式留空与编辑蒙版',`<div class="image-tool-heading"><p>${esc(pid)} · 拖动框选区域，也可精确输入像素。</p><span>不修改原图 · 待 Agent 对齐</span></div>
    <div class="region-stage"><canvas id="region-canvas"></canvas></div>
    <div class="region-controls"><label class="field">处理方式<select id="region-mode"><option value="prompt_only">提示模型避让 · 结果仍需核对</option><option value="image">直接嵌入图片 · 精确定位与等比适配</option><option value="solid">生成后精确填色留空</option><option value="transparent">生成后挖透明 · 用于人工合成底板</option>${im?'<option value="edit_mask">现有图的编辑蒙版 · 框内可改，框外保留</option>':''}</select></label><label class="field">填充颜色<input id="region-color" type="color" value="#ffffff"></label><label class="field">预留用途<input id="region-purpose" maxlength="2000" placeholder="例如右上品牌标志，或下方后贴真实数据图"></label></div>
    <section id="region-image-picker" class="region-image-picker" hidden><div class="row between"><h3>选一张原图嵌入</h3><button data-action="region-upload">从本机导入</button><input type="file" id="region-upload-file" accept="image/png,image/jpeg,image/webp" hidden></div><div class="row"><input id="region-image-search" placeholder="搜索本机素材、购物车中的图片" aria-label="搜索嵌入图片"><button data-action="region-image-search">查找图片</button><label class="field">适配方式<select id="region-fit"><option value="contain">等比完整显示（推荐）</option><option value="cover">填满区域，居中裁切装饰图</option></select></label></div><div id="region-image-results" class="region-image-results"></div><p id="region-image-selected" class="caption">尚未选图。真实数据图与截图保持完整，不交给模型重画。</p></section>
    <div class="region-pixels">${['X','Y','宽','高'].map((t,i)=>`<label>${t}<input type="number" id="region-p${i}" min="${i>1?4:0}" step="1" aria-label="区域${t}像素"></label>`).join('')}<span id="region-size" class="caption"></span></div>
    <div class="row between"><small>透明底板不是可编辑图层。精确留空会清除框内内容，采纳前需核对文字及证据。</small><button class="primary" data-action="save-region" disabled>保存区域，交给 Agent</button></div>`);
  $('#region-mode').onchange=()=>{const show=$('#region-mode').value==='image';$('#region-image-picker').hidden=!show;if(show)searchRegionImages().catch(e=>toast(e.message));drawRegion(false)};
  $('#region-fit').onchange=()=>drawRegion(false);
  $('#region-upload-file').onchange=uploadRegionImage;
  const c=$('#region-canvas'),size=S.proposal.generation_contract.size.split('x').map(Number);
  regionSession.background=null;
  const init=(w,h)=>{c.width=w;c.height=h;$('.region-stage').style.width=`min(100%,${Math.floor(innerHeight*.48*w/h)}px)`;$('#region-size').textContent=`画布 ${w} × ${h} px`;drawRegion()};
  if(im){const img=new Image();img.onload=()=>{regionSession.background=img;init(img.naturalWidth,img.naturalHeight)};img.src=im.url+'?v='+im.sha256}
  else init(...size);
  const point=e=>{const b=c.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))]};
  c.onpointerdown=e=>{if(e.button!==0)return;regionSession.start=point(e);c.setPointerCapture(e.pointerId)};
  c.onpointermove=e=>{if(!regionSession.start)return;const a=regionSession.start,b=point(e);regionSession.box=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1])];drawRegion(true)};
  c.onpointerup=()=>{regionSession.start=null};c.onpointercancel=c.onpointerup;
  for(let i=0;i<4;i++)$('#region-p'+i).oninput=()=>{const vals=[0,1,2,3].map(j=>Number($('#region-p'+j).value));regionSession.box=[vals[0]/c.width,vals[1]/c.height,vals[2]/c.width,vals[3]/c.height];drawRegion(false)};
}
function drawRegion(sync){
  const c=$('#region-canvas'),ctx=c.getContext('2d');ctx.fillStyle='#f4f1eb';ctx.fillRect(0,0,c.width,c.height);
  if(regionSession.background)ctx.drawImage(regionSession.background,0,0,c.width,c.height);
  const b=regionSession.box;if(!b)return;
  const v=[Math.round(b[0]*c.width),Math.round(b[1]*c.height),Math.round(b[2]*c.width),Math.round(b[3]*c.height)];
  if(sync){v.forEach((x,i)=>$('#region-p'+i).value=x);regionSession.box=[v[0]/c.width,v[1]/c.height,v[2]/c.width,v[3]/c.height]}
  if($('#region-mode').value==='image'&&regionSession.embeddedPreview){const img=regionSession.embeddedPreview,fit=$('#region-fit').value;ctx.save();ctx.beginPath();ctx.rect(...v);ctx.clip();ctx.fillStyle=$('#region-color').value;ctx.fillRect(...v);const scale=(fit==='cover'?Math.max:Math.min)(v[2]/img.naturalWidth,v[3]/img.naturalHeight),w=img.naturalWidth*scale,h=img.naturalHeight*scale;ctx.drawImage(img,v[0]+(v[2]-w)/2,v[1]+(v[3]-h)/2,w,h);ctx.restore()}else{ctx.fillStyle='#be593e33';ctx.fillRect(...v)};ctx.strokeStyle='#b75337';ctx.lineWidth=Math.max(2,c.width/500);ctx.strokeRect(...v);
  $('[data-action="save-region"]').disabled=!(v[0]>=0&&v[1]>=0&&v[2]>=4&&v[3]>=4&&v[0]+v[2]<=c.width&&v[1]+v[3]<=c.height&&($('#region-mode').value!=='image'||regionSession.embedded));
}
let regionSearchSerial=0;
async function searchRegionImages(){const serial=++regionSearchSerial,session=regionSession;const result=await api('/api/v3/assets?'+new URLSearchParams({q:$('#region-image-search').value,limit:12}));if(session!==regionSession||serial!==regionSearchSerial||!$('#region-image-results'))return;$('#region-image-results').innerHTML=result.items.map(r=>`<button data-action="region-image-select" data-id="${r.id}" data-version="${r.version}"><img src="${esc(r.preview_url)}" alt=""><span>${esc(r.title)}${S.cart.some(x=>x.id===r.id)?'<small>已在购物车</small>':''}</span></button>`).join('')||'<p class="caption">未找到图片，可修改关键词或从本机导入。</p>'}
async function selectRegionImage(id,version){const session=regionSession;const r=await api('/api/v3/assets/'+id+'?version='+version);if(session!==regionSession)return;regionSession.embedded=r;const evidence=r.original_metadata?.role==='evidence';$('#region-fit').value='contain';$('#region-fit').options[1].disabled=evidence;$('#region-image-selected').textContent='已选：'+r.title+(evidence?' · 真实证据完整保留':' · 固定此版本，不自动上传模型');if(!$('#region-purpose').value)$('#region-purpose').value='嵌入导入图片，模型仅留空';const img=new Image();img.onload=()=>{if(session!==regionSession)return;regionSession.embeddedPreview=img;drawRegion(false)};img.src='/api/assets/'+r.id+'/download?version='+r.version;drawRegion(false)}
async function uploadRegionImage(){try{const f=$('#region-upload-file').files[0];if(!f)return;const form=new FormData();form.append('revision',S.revision);form.append('file',f);form.append('kind','illustration');form.append('usage','material');form.append('role','evidence');const res=await fetch('/api/v3/upload',{method:'POST',headers:{'X-Mediagen-CSRF':S.csrf},body:form});const r=await res.json();if(!res.ok)throw Error(r.error||'上传失败');await reload(false);await selectRegionImage(r.id,r.version);toast('原图已保存；保存位置后仍需与 Agent 对齐')}catch(e){toast(e.message)}}
document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-action]');if(!el)return;
  try{
    switch(el.dataset.action){
      case 'coding-group':codingGroup=el.dataset.group;await renderView();break;
      case 'choose-component':await chooseComponent(el.dataset.id,el.dataset.version);break;
      case 'save-component':
        el.disabled=true;
        try{await api('/api/v3/components/request',{asset_id:componentSource.id,asset_version:componentSource.version,sha256:componentSource.sha256,slot:$('#component-slot').value,scope:$('#component-scope').value,strategy:$('input[name="component-strategy"]:checked').value});$('#modal').close();await reload();location.hash='components';toast('组件选择已保存，等待与 Agent 对齐。未生成图片。')}finally{el.disabled=false}break;
      case 'brand-guide':modal('品牌形象可以独立制作',`<p>直接在 Codex 说明要制作的品牌形象、图标或吉祥物，并提供已有标志及参考。无需先确认整套 PPT。</p><ol><li>Agent 从参考素材建立独立资产任务，明确色卡、比例与透明背景。</li><li>确认提示词、参考图和生成费用后，才调用模型。</li><li>保存模型、参数、输入图和变体关系；审核选定后加入固定组件。</li></ol><p class="muted">真实标志如需严格保真，优先保留原素材合成，不依赖模型重画。</p>`);break;
      case 'region-image-search':await searchRegionImages();break;
      case 'region-image-select':await selectRegionImage(el.dataset.id,el.dataset.version);break;
      case 'region-upload':$('#region-upload-file').click();break;
      case 'new-region':startRegion($('#region-page-select').value);break;
      case 'region-page':startRegion(el.dataset.page,el.dataset.id);break;
      case 'save-region':
        el.disabled=true;
        try{await api('/api/v3/regions',{page_id:regionSession.page_id,candidate_id:regionSession.candidate_id,sha256:regionSession.sha256,box:regionSession.box,mode:$('#region-mode').value,color:$('#region-color').value,purpose:$('#region-purpose').value,...($('#region-mode').value==='image'?{asset_id:regionSession.embedded?.id,asset_version:regionSession.embedded?.version,asset_sha256:regionSession.embedded?.sha256,fit:$('#region-fit').value}:{})});$('#modal').close();await reload();location.hash='components';toast('区域及蒙版已保存。回到 Codex 对齐后再执行。')}finally{el.disabled=false}break;
    }
  }catch(err){toast(err.message)}
});
