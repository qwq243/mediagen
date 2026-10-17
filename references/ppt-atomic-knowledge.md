# PPT原子化知识库 v1（本机增量实现）

## 入口与边界

原调度台侧栏内使用「设计知识库」「设计规格与验收」，不另起第二套网页应用。
入口为 `/#workflow`、`/#knowledge`、`/#design-spec`；根地址默认流程总览。
旧 `/workbench/knowledge.html` 与其 `#design` 书签自动跳转至原调度台。
六步总览逐步展示目标、产物、相关工具；历史交付状态不等于新标注或量化验收通过。
新增视图沿用原侧栏、字体、色系、项目版本和阶段进度；详细JSON只在高级区展开。
现有整套、单页、组件、收藏、截取入口保留，原标签和旧编码不覆盖。
新候选存于 `~/.mediagen/library/knowledge/candidates/<asset>/<image-version>/<annotation-hash>.json`。
**首批64页不能当完整精标金标准：8页为逐图详细候选，56页仍为结构盘点。**
8页包括五套各1页代表样例、3页空白结构反例。全部64页均无独立复核凭证。
其余页面内部细字、卡片内独立图标及复杂连接尚待精标。

## 六层合同

|层|字段|边界|
|---|---|---|
|作品|deck.title/context/styles/source_order/narrative_order/original_completeness|库内页数不等于原作者全稿；原顺序不是推断叙事顺序|
|页面|page.role/relations/layout/density/key_message/reading_order|页型、信息关系、几何布局三者分开|
|区域|regions[id,role,bbox]|标题、导航、主体、结论、安全区分别标|
|元素|elements[id,parent_id,region_id,kind,label,bbox,observed,protection,reuse,evidence]|独立文字块、卡片轮廓、图标、图片、连线分别标，不按汉字拆分|
|关系|relations[id,type,from,to,direction,label,evidence]|引用稳定元素ID，含包含、对齐、间距、连接、顺序、并列、因果、层级|
|来源质量|source/review/quality/coverage/issues/unknowns|图片版本与字节哈希双绑定；图像质量、标注质量、用途、权限分别展示|

### 参数字典

所有 `observed` 值采用 `{type,value,unit,status,evidence}`。状态：
`measured` 实测、`estimated` 估计、`verified` 有可靠证据核实、
`unknown` 未知、`not_applicable` 不适用。后两者 value 必须 null。
未知原因应在 evidence 细分：未提供、看不清、遮挡、不能测量，不能混作不存在。

|要素|建议键与类型|核验要求|
|---|---|---|
|位置|bbox=[x,y,w,h]；geometry_status|原图左上角归一化；不能为负、超边或非有限值|
|内容区域|source.content_box|原图坐标；转换为内容坐标：[(x-cx)/cw,(y-cy)/ch,w/cw,h/ch]|
|字体|font_family:fontFamily、font_class:enum、font_weight:fontWeight|family 非空必须 verified+具体元数据证据；外观相似不算字体名证据|
|文字|text:text、glyph_height:dimension、line_height:ratio、letter_spacing:dimension|字高单位px，不称原生字号；换行、强调范围另补类型化观察字段|
|几何|rotation:angle、z_index:number、padding/margin:dimension|单位deg、px；不确定叠层关系标未知|
|色彩|color:color、opacity:ratio、gradient:gradient|RGB #RRGGBB；取样必须含来源哈希、原图位置和方法|
|形状|border_radius:dimension、border_width:dimension、shadow:shadow|复杂结构需说明可见证据，不补造被遮挡外观|
|背景|background_kind:enum、subject_position:text、safe_text_area:text|照片背景与纯色分别处理，不能以纹理采样代表平面主题色|
|图标|icon_style:enum、viewpoint:text、material:text、lighting:text|同系列关系引用definitions；照片内部物体不无限拆分|
|真实素材|protection.identity/do_not_redraw|人物、品牌、证书、测量图保护，不推定上传许可|
|组件|definitions.components|固定轮廓、可变内容槽、适用页型、源元素引用|

Schema校验公共字段和类型容器，业务校验补充坐标边界、引用、循环父级、
词表、字体证据、取色来源和非有限值；目标编译器另校验渐变色标、阴影和字体角色对象。
这是本项目类型子集，不是第三方格式的完整实现。
不得将其宣传成完整Design Tokens规范实现。

### 三份真值

1. `observed`：源图实际观察，来源质量可不确定。
2. `design.atomic_spec`：项目目标，唯一生产真值；网页不会另存一套设计。
3. `design_deviation_reports`：绑定目标哈希与成品哈希的实际测量、审核。

目标沿全局→页型→页面继承，元素保留自有属性。页面同名普通参数覆盖；
elements列表显式替换而不是猜测合并。硬约束冲突报错。
坐标自动换算1280×720基准像素；提示词注明是目标，不是假装API保证。
当前编辑UI提供JSON高级面板和坐标草案编辑；不是在线图层编辑器。
默认新规格只是一份草案，不会自动改动已交付项目或追认历史审批。

## 使用步骤

1. 分配每套task-packs的manifest，固定ID/version/sha256；附Schema、词表、字典和本地原图。
2. 用annotation-agent提示词逐页精标，只向候选目录写入；不能把当前初步盘点当金标准。
3. `python scripts/ppt_knowledge.py validate --input candidates.json`：仅结构校验。
4. `python scripts/ppt_knowledge.py stage --input candidates.json --library <library>`：不可变候选入库。
5. 独立人员/独立实际看图复核后，使用review-agent提示词输出绑定标注哈希的receipt。
6. `python scripts/ppt_knowledge.py review --input receipt.json --library <library>`：只有完整覆盖与全部视觉检查通过才为reviewed。
7. 网页组合检索，点击元素看框与观察参数；“借结构/字形/色系/组件”只进入待确认队列。
8. 先补齐并启用项目规格，再从待确认队列选择目标页/元素→查看参数转换提案→填写确认依据→采用。
   结构使用content_box坐标转换；字体仅转用有依据的外观类别/字重/已核实名称，
   可见字高不转换为字号；颜色无取样依据时拒绝；组件不复制原文/品牌/图片。
   应用前核对当前候选哈希、项目版本和提案指纹；采用后显示受影响页面，旧审批需更新。
   这些操作不上传原图、不授予版权、不调用模型。高级规格仍可进一步调整。
   返回原流程做方案、提示词、样张确认。
9. 两种生成通道显式区分：样张无额外锚点；整套首图为批准锚点。
   页面实际提示词/参考图与生成器共用解析器。
10. 执行时先冻结请求包，仍需原预算与显式付费确认，失败不自动重试换模型。
11. 逐项提交绑定成品哈希的测量，未知保持pending，失败保留证据和阈值。

## 搜索与质量

同义词映射保留旧标签；上位概念进入召回，相关关系只作参考，不冒充精确匹配。
候选/精标/已复核须区别，未知字体名不做精确字体匹配。
默认按套系轮换展示；“已授权可复用”要求reviewed、明确授权、clean或verified_clean、
且无已知污染对象/问题。透明筛选不等于已授权。
新知识索引目前仅64页，不冒称8千余条全库已重标；旧素材检索继续可用。
元素详情可显式切换同一原图版本的候选历史；必须填写原因，当前哈希冲突时拒绝。
旧候选、旧标签不删除；selection-history记录切换。

## 请求与验收

`design-request-packages/<request-hash>/request.json`保存规格、编译器版本、完整提示词、
实际有序输入及文件哈希、请求模型、API参数；输入复制到同目录。
实际输出、上游reported_model及采用记录仍沿用image_recipe和generation_calls。
seed与上游未返回字段保持null/unknown。相同请求包可重建，像素不保证相同。
网页导出的请求JSON是清单；“复现包ZIP”包含实际参考图字节、提示词、规格、
已有成品、采用信息和已有审核。下载不写项目、不生图、不授予版权。
真正执行时还会冻结目录，并从冻结的图片/提示词字节调用模型，避免校验后源图变化。

偏差默认：中心各轴≤2%；宽高相对误差≤10%；指定平坦区域ΔE00≤5；
文本/姓名/数字/日期与语义连线零误差，字体按批准样张看外观；
关键文字不得裁切遮挡，保护区不得被侵入。
阈值冻结后网页拒绝直接改阈值；需另行项目确认。测量不全不自动通过。
自动色差依赖现有numpy/skimage，当前未做OCR自动识别或自动语义测量。
网页“目标与成品”提供逐对象实际坐标、逐字文案、字体外观、取色和安全区录入；
不能将目标值自动复制为实测值。审核绑定当前规格和成品哈希，之后变更显示stale。
网页结构示意与总览使用后端同一编译器，不另写一套前端继承算法。
数字在设计编译时规范化，浏览器将`5.0`转成`5`不会使未修改页面的指纹失效。
明确启用原子规格后，旧色卡/字号/网格不再重复进入提示词；艺术方向等叙述保留。
启用前的草案不是无损迁移：仅迁入现有色卡和原文，位置为待确认提案，
字号、字体系、组件和背景仍需按参考图补齐确认，不自动替用户激活。
启用后的样张确认、整套生产和最终导出还需当前成品的偏差审核；
校验重新计算测量结论，不只相信`status=passed`；缺失、失败、旧哈希均阻断。
旧项目未启用原子规格时保持原工作流；本轮没有改写已交付生产项目。

### 复合类型示例（均为设计目标，不是API实参）

```json
{
  "title-type": {
    "type": "typography",
    "value": {"class": "FT-SANS", "family": null, "size_px": 44,
              "weight": 700, "line_height": 1.15, "letter_spacing_px": 0}
  },
  "card-shadow": {
    "type": "shadow",
    "value": {"x_px": 0, "y_px": 3, "blur_px": 12, "spread_px": 0,
              "color": "#203C36", "opacity": 0.12}
  },
  "paper-gradient": {
    "type": "gradient",
    "value": {"kind": "linear", "angle_deg": 90,
              "stops": [{"position": 0, "color": "#FAF9F5"}, {"position": 1, "color": "#E8EFEB"}]}
  }
}
```

元素中`style.typography={token:"title-type"}`引用目标字体系。`element_defaults`提供默认值，
元素显式属性覆盖普通默认；任何层的hard_constraints不可静默取消。卡片背景和描边可用
`style.fill/border_width/border_color/radius/shadow`等同样的类型化对象。
`components`记录固定轮廓、变量槽、适用页型；`background`记录背景种类、引用token和主体避让。
bbox自动导出中心及尺寸，无须重填像素位置；模型不保证精确执行这些目标。

## 尚未达到的验收项

- 64页复杂内部元素原尺寸完整精标与独立复核。
- 全库原子化检索覆盖和经过人工校准的精细质量评分。当前新索引只覆盖64页。
- 自动测量/OCR与语义连接识别未实现；目前依靠带依据的人工录入，不虚构自动通过率。
- 另行批准预算内的6次重复生图稳定性试验，本轮零生图调用。

## 本机性能与状态保护

`ppt_read_cache.py`只提供读取加速：单次工作台检查共享图片哈希，不跨请求缓存批准；
素材发现索引按数据库/WAL的文件身份、时间和头部变化失效，且不保持SQLite连接。
精确页详情与生产闸门继续读取当前版本，不把发现缓存用作授权依据。
前端原地导航取消旧请求；知识库保留筛选/分页，合并重复读取，输入防抖兼容中文组合输入。
未保存的规格离开前确认；高级草案与资源借鉴不允许静默覆盖；实际提示词始终说明其已保存版本。
同一路径的已取消请求不得被下次检索复用。前后性能证据应区分冷/热、API/页面与测试视口。

参考模型：Design Tokens Format 2025.10（类型组织，不等于模型控制）、
W3C SKOS（词表概念）、Web Annotation（来源与区域绑定）。
