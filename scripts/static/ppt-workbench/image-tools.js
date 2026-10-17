'use strict';
// Version-bound image operations. No endpoint here calls a generation model.
let cropSession=null, recipeData=null;

function openAnnotation(meta,saved,title){
  annotation={...meta,tool:'ellipse',shapes:structuredClone(saved?.shapes||[]),drawing:null,noteIndex:null,legacyComment:saved?.comment||''};
  modal(title,`<div class="image-tool-heading"><p>圈出位置，直接在旁边写下想法。</p><span>原图保留 · 修改前与 Agent 对齐</span></div>
    <div class="toolbar" role="toolbar" aria-label="图片标注工具">${[['ellipse','◯ 圈画'],['rect','□ 框选'],['arrow','↗ 箭头'],['pen','〰 画线'],['text','T 文字']].map(([v,t])=>`<button data-action="tool" data-tool="${v}" class="${v==='ellipse'?'active':''}">${t}</button>`).join('')}
    <button data-action="undo">↶ 撤销</button><select id="zoom" aria-label="缩放"><option value="1">适应窗口</option><option value="1.5">放大 150%</option><option value="2">放大 200%</option></select></div>
    <div class="annotation-scroll"><div class="annotation-stage"><img id="ann-image" src="${esc(meta.im.url)}${meta.im.url.includes('?')?'&':'?'}v=${meta.im.sha256}" alt="待标注的原始图片"><canvas id="ann-canvas"></canvas><div id="ann-pins"></div><div id="ann-popover" class="ann-popover" hidden></div></div></div>
    <div class="annotation-note"><div class="row between"><small>点击编号可修改该处说明；批注不会涂入原图，也不自动作为编辑蒙版。</small><div class="actions"><button data-action="save-annotation">保存草稿</button><button class="primary" data-action="submit-annotation">提交标注</button></div></div></div>`);
  const canvas=$('#ann-canvas'),img=$('#ann-image');
  const load=()=>{canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;drawAnnotations()};
  img.onload=load;if(img.complete&&img.naturalWidth)load();
  canvas.onpointerdown=e=>{
    if(e.button!==0)return;
    commitAnnotationNote();$('#ann-popover').hidden=true;
    annotation.drawing={tool:annotation.tool,points:[annPoint(e)],text:'',comment:''};
    canvas.setPointerCapture(e.pointerId);
  };
  canvas.onpointermove=e=>{const s=annotation.drawing;if(!s)return;if(s.tool==='pen')s.points.push(annPoint(e));else s.points[1]=annPoint(e);drawAnnotations()};
  canvas.onpointerup=()=>{if(!annotation.drawing)return;annotation.shapes.push(annotation.drawing);annotation.drawing=null;drawAnnotations();openAnnotationNote(annotation.shapes.length-1)};
  canvas.onpointercancel=()=>{annotation.drawing=null;drawAnnotations()};
  $('#zoom').onchange=()=>{commitAnnotationNote();$('#ann-popover').hidden=true;$('.annotation-stage').style.width=Number($('#zoom').value)*100+'%'};
}
function annPoint(e){
  const b=$('#ann-canvas').getBoundingClientRect();
  return [Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))];
}
function commitAnnotationNote(){
  const input=$('#ann-inline-comment'),s=annotation?.shapes[annotation.noteIndex];
  if(input&&s){s.comment=input.value;if(s.tool==='text')s.text=input.value}
}
function annotationComment(){
  commitAnnotationNote();
  return annotation.shapes.map((s,i)=>s.comment?`${i+1}. ${s.comment}`:'').filter(Boolean).join('\n')||annotation.legacyComment||'请结合圈画位置与我对齐';
}
function openAnnotationNote(index){
  commitAnnotationNote();annotation.noteIndex=index;
  const s=annotation.shapes[index],pop=$('#ann-popover'),stage=$('.annotation-stage');
  if(!s)return;
  const [x,y]=s.points.at(-1),width=Math.min(292,stage.clientWidth-16);
  pop.innerHTML=`<div class="ann-popover-title"><strong>批注 ${index+1}</strong><button data-action="ann-note-close" aria-label="收起这条批注">×</button></div><textarea id="ann-inline-comment" maxlength="4000" placeholder="希望这里怎样调整？">${esc(s.comment||s.text||'')}</textarea><div class="row between"><button class="mini subtle" data-action="ann-note-delete">删除此处</button><button class="mini primary" data-action="ann-note-close">完成</button></div>`;
  pop.hidden=false;pop.style.width=width+'px';
  pop.style.left=Math.max(8,Math.min(stage.clientWidth-width-8,x*stage.clientWidth+12))+'px';
  pop.style.top=Math.max(8,Math.min(stage.clientHeight-pop.offsetHeight-8,y*stage.clientHeight+12))+'px';
  $('#ann-inline-comment').focus({preventScroll:true});
  $('#ann-inline-comment').oninput=()=>{commitAnnotationNote();drawAnnotations()};
}
function drawAnnotations(){
  const c=$('#ann-canvas');if(!c)return;
  const ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.strokeStyle='#d65e43';ctx.fillStyle='#d65e43';ctx.lineWidth=Math.max(3,c.width/350);ctx.font=`${Math.max(18,c.width/55)}px Microsoft YaHei`;
  for(const s of [...annotation.shapes,...(annotation.drawing?[annotation.drawing]:[])]){
    const pts=s.points.map(([x,y])=>[x*c.width,y*c.height]),a=pts[0],b=pts.at(-1);
    ctx.beginPath();
    if(s.tool==='ellipse')ctx.ellipse((a[0]+b[0])/2,(a[1]+b[1])/2,Math.abs(b[0]-a[0])/2,Math.abs(b[1]-a[1])/2,0,0,2*Math.PI);
    else if(s.tool==='rect')ctx.rect(a[0],a[1],b[0]-a[0],b[1]-a[1]);
    else if(s.tool==='text')ctx.fillText(s.text||'文字位置',a[0],a[1]);
    else{ctx.moveTo(...a);pts.slice(1).forEach(pt=>ctx.lineTo(...pt));if(s.tool==='arrow'){const angle=Math.atan2(b[1]-a[1],b[0]-a[0]),len=c.width/50;for(const dir of [-1,1]){ctx.moveTo(...b);ctx.lineTo(b[0]-len*Math.cos(angle+dir*.5),b[1]-len*Math.sin(angle+dir*.5))}}}
    ctx.stroke();
  }
  $('#ann-pins').innerHTML=annotation.shapes.map((s,i)=>`<button class="annotation-pin" data-action="ann-note" data-index="${i}" aria-label="编辑批注 ${i+1}" title="${esc(s.comment||'添加说明')}" style="left:clamp(14px,${s.points[0][0]*100}%,calc(100% - 14px));top:clamp(14px,${s.points[0][1]*100}%,calc(100% - 14px))">${i+1}</button>`).join('');
}

async function startCrop(target,id,pid,cid){
  let meta;
  if(target==='reference'){
    const r=currentPreview?.id===id?currentPreview:await api('/api/v3/assets/'+encodeURIComponent(id));
    meta={target_kind:'reference',asset_id:r.id,asset_version:r.version,sha256:r.sha256,title:r.title,url:`/api/assets/${r.id}/download?version=${r.version}`};
  }else{
    const pg=S.pages.find(x=>x.page_id===pid),im=cid?pg.candidates.find(x=>x.id===cid):pg.selected;
    meta={target_kind:'page',page_id:pid,candidate_id:cid||null,sha256:im.sha256,title:pg.title||pid,url:im.url};
  }
  cropSession={meta,box:null,start:null};
  modal('截取局部参考',`<div class="image-tool-heading"><p>拖出一个框，把喜欢的这一部分单独留下。</p><span>按原图像素裁切，不降低清晰度</span></div>
    <div class="crop-stage"><img id="crop-image" src="${esc(meta.url)}${meta.url.includes('?')?'&':'?'}v=${meta.sha256}" alt="裁切原图"><canvas id="crop-canvas"></canvas></div>
    <div class="crop-meta"><label class="field">素材名称<input id="crop-title" maxlength="200" value="${esc(meta.title.slice(0,100))} · 局部"></label><label class="field">素材类型<select id="crop-kind">${Object.entries(kindNames).filter(([k])=>k!=='deck').map(([k,v])=>`<option value="${k}" ${k==='decoration'?'selected':''}>${v}</option>`).join('')}</select></label><label class="field">标签（用逗号分隔）<input id="crop-tags" placeholder="例如 章节进度、弧形页眉、艺术字"></label></div>
    <div class="row between"><small id="crop-dimensions">在图片上拖动选择范围</small><button class="primary" data-action="save-crop" disabled>保存为独立素材</button></div>`);
  const img=$('#crop-image'),c=$('#crop-canvas');
  const load=()=>{c.width=img.naturalWidth;c.height=img.naturalHeight;$('.crop-stage').style.width=`min(100%, ${Math.floor(innerHeight*.56*c.width/c.height)}px)`;drawCrop()};img.onload=load;if(img.complete&&img.naturalWidth)load();
  const point=e=>{const b=c.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))]};
  c.onpointerdown=e=>{if(e.button!==0)return;cropSession.start=point(e);cropSession.box=null;c.setPointerCapture(e.pointerId)};
  c.onpointermove=e=>{if(!cropSession.start)return;const a=cropSession.start,b=point(e);cropSession.box=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];drawCrop()};
  c.onpointerup=()=>{cropSession.start=null;drawCrop()};
  c.onpointercancel=()=>{cropSession.start=null};
}
function drawCrop(){
  const c=$('#crop-canvas'),ctx=c.getContext('2d'),box=cropSession.box;ctx.clearRect(0,0,c.width,c.height);
  if(!box)return;
  const x=Math.round(box[0]*c.width),y=Math.round(box[1]*c.height),w=Math.round(box[2]*c.width)-x,h=Math.round(box[3]*c.height)-y;
  ctx.fillStyle='#ffffff99';ctx.fillRect(0,0,c.width,c.height);ctx.clearRect(x,y,w,h);
  ctx.strokeStyle='#be593e';ctx.lineWidth=Math.max(2,c.width/500);ctx.setLineDash([c.width/180,c.width/300]);ctx.strokeRect(x,y,w,h);
  $('#crop-dimensions').textContent=`已选 ${w} × ${h} 像素 · 将保留原图与截取位置`;
  $('[data-action="save-crop"]').disabled=w<4||h<4;
}
async function saveCropAndFavorite(payload){
  const r=await api('/api/v3/assets/crop',payload);
  if(!r.favorite){
    try{
      await api('/api/v3/assets/favorite',{id:r.id,enabled:true});
      r.favorite=true;
    }catch(err){
      throw new Error(`素材已保存（${r.id}），但自动收藏失败：${err.message}。请在素材详情手动收藏。`);
    }
  }
  return r;
}
async function showRecipe(query){
  const q=new URLSearchParams(query).toString(),r=await api('/api/v3/recipe?'+q);recipeData=r;
  if(r.status==='unavailable'){modal('生成记录',`<div class="empty">${esc(r.message)}</div>`);return}
  const labels={model:'请求模型',size:'请求尺寸',quality:'质量',n:'图片数量',stream:'流式返回',output_format:'输出格式',response_format:'返回方式',background:'背景',seed:'随机种子',style:'风格',moderation:'审核选项',output_compression:'压缩质量'};
  modal('生成记录 · 可追溯的这一版',`<div class="panel"><div class="row"><span class="pill">${r.mode==='edit'?'图片编辑':r.mode==='variation'?'生成变式':'文字生图'}</span><span class="caption">${esc(r.id)}</span></div><h3>${esc(r.requested_model)}</h3><p class="caption">上游返回模型：${esc(r.reported_model||'未明确返回，不能确认内部实际模型')} · 未返回的默认参数和种子不补猜。</p><dl class="recipe-parameters">${Object.entries(r.parameters).map(([k,v])=>`<div><dt>${esc(labels[k]||k)}</dt><dd>${valueHtml(v)}</dd></div>`).join('')}</dl></div>
    <h3>当时使用的图片 · ${r.inputs.length} 张</h3><div class="recipe-inputs">${r.inputs.map((x,i)=>`<figure><a href="/api/v3/recipe/input/${i}?${esc(q)}" target="_blank" rel="noopener"><img src="/api/v3/recipe/input/${i}?${esc(q)}" alt="第 ${i+1} 张${x.role==='mask'?'蒙版':'参考图'}"></a><figcaption>${i+1} · ${x.role==='mask'?'编辑蒙版':'输入参考图'}${x.parent_recipe_id?' · 有父版本记录':''}</figcaption></figure>`).join('')||'<p class="muted">本次请求未使用输入图片。</p>'}</div>
    <details class="panel"><summary>完整生成提示词</summary><div class="recipe-prompt">${esc(r.prompt||'此变式请求没有文本提示词')}</div></details><div class="row between"><small>输入图片、提示词与参数均已保存；再次生成不保证像素完全一致。</small><button data-action="download-recipe">下载生成记录</button></div>`);
}
document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-action]');if(!el)return;
  try{
    switch(el.dataset.action){
      case 'ann-note':openAnnotationNote(Number(el.dataset.index));break;
      case 'ann-note-close':commitAnnotationNote();$('#ann-popover').hidden=true;drawAnnotations();break;
      case 'ann-note-delete':annotation.shapes.splice(annotation.noteIndex,1);annotation.noteIndex=null;$('#ann-popover').hidden=true;drawAnnotations();break;
      case 'crop-reference':await startCrop('reference',el.dataset.id);break;
      case 'preview-version':await preview(el.dataset.id,el.dataset.version);break;
      case 'crop-page':await startCrop('page',null,el.dataset.page,el.dataset.id);break;
      case 'save-crop':{
        el.disabled=true;
        try{
          const r=await saveCropAndFavorite({...cropSession.meta,box:cropSession.box,title:$('#crop-title').value,kind:$('#crop-kind').value,tags:$('#crop-tags').value.split(/[,，、]/).map(x=>x.trim()).filter(Boolean)});
          await preview(r.id);toast('局部素材已保存并加入精选收藏，原图与截取位置已保留。');
        }finally{if(el.isConnected)el.disabled=false}
        break;
      }
      case 'recipe-asset':await showRecipe({asset_id:el.dataset.id,version:el.dataset.version});break;
      case 'recipe-page':await showRecipe({page_id:el.dataset.page,candidate_id:el.dataset.id||''});break;
      case 'download-recipe':{
        const url=URL.createObjectURL(new Blob([JSON.stringify(recipeData,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=recipeData.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);break;
      }
    }
  }catch(err){toast(err.message)}
});
