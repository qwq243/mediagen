/* One navigation shell, one project truth, explicit production gates. */
(function () {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const steps = [
    {id:'stage1', title:'沟通与参考', goal:'先确定讲什么、给谁看，再选参考。', output:'讲稿底稿、目标、时长与参考用途',
      tools:[['assets','本机素材'],['knowledge','设计元素检索'],['cart','选材待对齐']]},
    {id:'stage2', title:'完整方案', goal:'从整套看：顺序、每页职责、文案、时长与统一风格。', output:'可以执行的整套方案',
      tools:[['design-spec','规格 / 提示词 / 参考图'],['components','全局组件'],['coding','标注规范']]},
    {id:'samples', title:'逐页创作', goal:'聚焦一页：改内容、对照参考、核对成图并选择版本。', output:'逐页审核并采用的成图',
      tools:[['design-spec','目标与成品对照'],['favorites','收藏 / 局部素材']]},
    {id:'deck', title:'整套统稿', goal:'统一风格锚点，检查跨页一致性。', output:'完整页面、版本采用记录、整套审核', tools:[]},
    {id:'delivery', title:'讲稿与交付', goal:'对照讲稿、导出并在目标软件验证。', output:'完整 PPT、讲稿、逐页图、复现包',
      tools:[['design-spec','请求与复现包']]},
    {id:'feedback', title:'使用反馈', goal:'记录老师意见与真实使用问题，沉淀可复用设计。', output:'下一轮修改依据',
      tools:[['knowledge','知识库'],['coding','标注与复核']]}
  ];
  const statuses={completed:'已完成',active:'进行中',locked:'待前序确认',revision_required:'需要重新对齐',preview:'可浏览，待审核',waiting_agent:'等待 Agent 审核'};
  window.renderWorkflowGuide = state => {
    const current=state.progress.find(x=>x.accessible&&!x.complete)||state.progress.at(-1);
    return `<div class="intro"><div class="eyebrow">WORKFLOW / 调度台</div><h1>一条主线，完成整份 PPT。</h1><p>先对齐内容与风格，再逐页制作、统稿和交付。素材与设计工具按需使用，不是额外必经步骤。</p></div>
    <nav class="workflow-path" aria-label="制作主线">${steps.map((step, i) => `<a href="#${step.id}"><span>${String(i + 1).padStart(2,'0')}</span>${step.title}</a>${i < steps.length - 1 ? '<b aria-hidden="true">→</b>' : ''}`).join('')}</nav>
    <section class="workflow-next"><div><small>建议下一步</small><h2>${escape(current.label)}</h2><p>${escape(current.reason||'进入当前阶段，与 Agent 对齐后继续。')}</p></div><a class="button primary" href="#${escape(current.id)}">继续当前阶段 →</a></section>
    <aside class="workflow-shared"><div><strong>02 看整套，03 改一页</strong><p>两处共用同一份页面草稿。编辑、保存不会改变已有成图；对齐并制作新候选后，再审核选用。</p></div><div><strong>已交付后，只修改几页？</strong><p>从 <a href="#samples">03 → 04 → 05</a> 继续即可；只有整套结构或风格变化，才回 02 重新对齐。</p></div></aside>
    <div class="workflow-map">${steps.map((step,i)=>{
      const row=state.progress.find(x=>x.id===step.id);
      return `<article class="workflow-card"><div class="row between"><span class="workflow-number">${String(i+1).padStart(2,'0')}</span><span class="pill">${escape(statuses[row?.status]||'待开始')}</span></div><h2>${step.title}</h2><p>${step.goal}</p><dl><dt>本步产物</dt><dd>${step.output}</dd></dl><a class="workflow-enter" href="#${step.id}">${row?.accessible?'进入此阶段':'查看前置要求'} →</a></article>`;
    }).join('')}</div>
    <section class="panel workflow-utilities"><header><h2>辅助工具 · 按需使用</h2><span>服务主流程，不另走一套</span></header><div class="workflow-utility-grid">
      <div><h3>找参考与收集素材</h3><p>素材库检索 → 收藏或截取 → 购物车整理用途 → 与 Agent 对齐。</p><div class="workflow-tools"><a href="#assets">本机素材库</a><a href="#favorites">精选收藏</a><a href="#cart">素材购物车</a><a href="#sites">灵感导航</a></div></div>
      <div><h3>定统一风格与参数</h3><p>02 确认整套风格；需要细化时，再看组件、参数、提示词与参考顺序。</p><div class="workflow-tools"><a href="#components">全局设计与组件</a><a href="#design-spec">设计规格与验收</a></div></div>
      <div><h3>管理设计知识</h3><p>标注、检索和复核素材，供后续借鉴；普通制作无需逐项填写。</p><div class="workflow-tools"><a href="#knowledge">设计知识库</a><a href="#coding">参考编码</a></div></div>
    </div></section>
    <details class="panel workflow-operation-help"><summary>保存、交接、确认、生成，有什么区别？</summary><dl>
      <div><dt>保存草稿</dt><dd>保存文字和修改意见，不等于改变成图或开始生成。</dd></div>
      <div><dt>提交给 Agent / 复制本页需求</dt><dd>记录或整理待对齐需求，不等于自动派单执行。目前需回到 Codex 对话继续；03 可直接复制本页需求。</dd></div>
      <div><dt>确认方案</dt><dd>确认当前设计版本，不等于付费授权；新增修改须先对齐。</dd></div>
      <div><dt>生成与选用</dt><dd>确认本次范围和预算后制作候选，审核通过再采用；已有版本继续保留。</dd></div>
    </dl><p>选择参考不代表授权上传。新规格的启用状态以「设计规格与验收」为准；历史主流程完成不等于新增标注或量化偏差审核已完成。</p></details>`;
  };
  window.workflowContext = id => {
    const links = {
      assets:[['knowledge','下一步：检索元素与设计方法'],['cart','查看选材购物车']],
      favorites:[['knowledge','查看元素标注'],['cart','整理采用意图']],
      components:[['design-spec','核对量化规格与实际请求'],['stage2','返回完整方案']],
      coding:[['knowledge','查看真实标注样板'],['design-spec','从标注到设计规格']],
      stage2:[['samples','聚焦一页修改'],['components','整套统一风格']],
      samples:[['stage2','返回整套方案']]
    };
    return links[id]?`<div class="workflow-context"><a href="#workflow">流程总览</a><span>·</span>${links[id].map(([r,t])=>`<a href="#${r}">${t} →</a>`).join('')}</div>`:'';
  };
})();
