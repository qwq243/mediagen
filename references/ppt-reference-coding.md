# PPT 参考编码规范 v1

本规范服务于“人挑选参考 → Agent 理解借鉴对象 → 图片模型受约束生成”，不是把不同设计压成一个模板。原图片、人工标签和作品归属均保留。**分类编码不是图片身份；已入库不是已复核。**

## 1. 身份、类型与版本分离

| 层次 | 格式 | 含义与规则 |
|---|---|---|
| 整套作品 | `DK-000001` | 系统分配、永久不变。不包含主题、颜色或年份，不自行重编号 |
| 单张页面/独立图片 | `PG-000002` | 系统分配、跨作品移动也不随页序改号。独立素材也有 PG 身份，资源种类另存 |
| 项目页 | `P01` 等 | 当前项目的页号，不是参考库永久身份 |
| 图像版本 | `image_sha256` | 原始图片内容指纹。换图就必须重新核对编码和批注 |
| 元数据版本 | `asset_version` | 标签、编码等完整快照指纹。项目选用时固定版本，不跟随资源库悄悄变化 |
| 固定组件实例 | `CMP-<DK数字>-<类型>-<序号>` | 如 `CMP-000001-TOPBAR-01`，一种确切外观，不只是“顶栏”类别 |
| 字体系实例 | `TYP-<DK数字>-<序号>` | 角色字体组合；封面艺术字可与正文不同，但同角色跨页一致 |
| 色卡实例 | `PAL-<DK数字>-<序号>` | 一组有来源的具体颜色与用途，而非“蓝色科技风” |

编号的数字只保证唯一，不表示页序，也不要求连续。作品内顺序使用 `page_order`，章节引用 `page_codes`。`page_order` 来自原始清单，编码包不改变原作顺序；确需纠错时单独提供更正映射并刷新源清单。**整理人员不要改自动生成的 asset_id / deck_code / page_code / image_sha256 / asset_version，也不要重命名源图片来“重新编码”。** 因路径调整需合并身份时，先交给 Agent 做有映射的迁移；不要删除重建。

原文件编号如 `001-…jpg`、原 `id` 留在后台，用于溯源。旧名称和旧人工标签不被新分类覆盖。

## 2. 三层结构 + 五层视觉

### 整套层：为什么按这个顺序讲

- `NT-ARG` 问题—方案—验证—价值
- `NT-STORY` 情境—行动—变化—启示
- `NT-TEACH` 目标—讲解—练习—反馈
- `NT-DECIDE` 选项—标准—比较—建议
- `NT-MECHANISM` 输入—机制—输出—边界
- `NT-REPORT` 目标—进展—问题—计划
- `NT-MIXED` 混合，须解释主线及局部变化

整套记录 `purpose`（服务什么目的）、`narrative`（可以多选）、`chapters`（有顺序的章节，含名称、目的、page_codes）、`evidence`（观察依据）。只看了一页不能认定整套叙事。

### 页面层：这页承担什么任务

`RL-COVER` 封面、`RL-AGENDA` 目录、`RL-SECTION` 过渡、`RL-CONTEXT` 背景、
`RL-PROBLEM` 问题、`RL-CLAIM` 主张、`RL-SOLUTION` 方案、`RL-MECHANISM` 原理、
`RL-PROCESS` 过程、`RL-EVIDENCE` 证据、`RL-COMPARE` 比较、`RL-DEMO` 演示交接、
`RL-TEAM` 团队、`RL-MODEL` 商业/服务模式、`RL-PLAN` 规划、
`RL-SUMMARY` 总结、`RL-CLOSING` 尾页、`RL-REFERENCE` 参考资料、
`RL-EXPLORATION` 探索提问、`RL-ASSET` 组件/骨架参考。

一页优先一个主职责，不必强行是一句断言；允许问题、过渡、留白。原“正文”不是足够精确的职责，可保留原标签，主职责留空等待分析。

### 关系层：信息之间是什么关系

`IR-PARALLEL` 并列、`IR-COMPARE` 对比、`IR-CAUSE` 因果、`IR-PROGRESS` 递进、
`IR-FLOW` 流程、`IR-HIERARCHY` 层级、`IR-PART` 总分、`IR-CYCLE` 循环、
`IR-TIMELINE` 时间演进、`IR-NETWORK` 网络、`IR-SPATIAL` 空间。

允许主次关系组合。**双栏不必然是对比，环形不必然是循环，箭头不必然是因果。** 只有内容与版式共同支持时才确认。

### 视觉层：怎样呈现

1. **布局** `LY-*`：单主视觉 HERO、双栏 SPLIT-2、三栏 COLS-3、四象限 QUADRANT、
   上下 STACK、网格 GRID、放射 RADIAL、环形 RING、轴线 AXIS、阶梯 STAIRS、
   金字塔 PYRAMID、看板 DASHBOARD、满版 FULLBLEED、复合 MIXED。
   附 `description`、阅读顺序 `reading_order` 和 `regions`，不要只写一个模糊名称。
2. **固定/特殊组件** `CP-*`：TOPBAR 顶部标题栏、NAV 章节导航、PROGRESS 章节进度、
   FOOTER 页脚、PAGENUM 页码、BRAND 品牌、RIBBON 飘带、CARD 信息卡、QUOTE 结论条、
   ICON 图标家族、BACKGROUND 背景、ILLUSTRATION 插图。
   组件实例写进 `definitions` 并关联 `component_refs`，可供多个页面复用。
3. **字型类别** `FT-*`：SANS 黑体、SERIF 宋体、BRUSH 毛笔、DISPLAY 艺术字、
   HAND 手写、GEOMETRIC 几何数字、UNKNOWN 未识别。
   字型类别不等于真实字体名称。`family` 不确定就 `null`；
   只有原文件元数据、作者提供或可靠核实才写具体 family，并给 `identification` 与证据。
   字体系分 display / heading / body / numbers / caption 角色，记录字重、相对字号层级、
   字间距、行距、描边/阴影等。烤在图里的艺术字可以记录参考区域，不承诺本机有对应字体文件。
4. **色卡**：保留原 `colors` 描述；实际取色记录 `hex`（六位）、role
   （background/text/primary/accent/border 等）、来源图片及坐标、取色方法。
   渐变记录起止色与方向，不把阴影/抗锯齿采样噪点都列为主色。
   不知道真实色值就留空，不能凭“红金风”臆造一套确定色卡。
5. **密度与材质**：DN-LOW / MEDIUM / HIGH 按观看场景判断，不按固定字数；
   MT-FLAT/PAPER/GLASS/INK/WATERCOLOR/METAL/PHOTO 是材质语言，可多选。

新增分类应先扩展词表及说明，再批量使用；不要让每位整理者自行造同义编码。

## 3. 组件与坐标约定

`bbox = [x, y, width, height]`，均为 0–1 的原图归一化坐标，左上为原点；
宽高必须大于 0，右/下边界不得超过 1。例如 `[0, 0, 1, 0.12]` 表示顶部 12% 区域。
这个例子是坐标说明，**不是对任何现有页面的真实测量**。

组件定义至少包括：
- code / name / type_code
- source_page_code / image_sha256 / bbox / evidence
- appearance（外观语言）、variant_of（变式关系，可空）
- fixed（必须保持的轮廓、位置、色彩、品牌）与 variable_fields
  （如 title、chapter_label、active_chapter、page_number、page_total）
- roles（适用封面/正文/过渡/尾页）、keep_clear（安全区）

相同色彩但不同造型是不同组件实例；同一组件改当前章节属于变量，不重新造一个实例。
页序变动须重算导航/页码。真实标识和证据图保持原图，不要求模型凭记忆重画。

## 4. 整理与复核流程

1. 使用系统导出的真实清单，按 DK 分工；先整套浏览，再逐页填写。
2. 保留 `source_description`、原人工 tags、source_file，不把“推测作者意图”写成事实。
3. 自动词语匹配结果是 `suggested`，不是视觉审核。检查不适用的建议并删除/修正。
4. `reviewed` 需要 reviewer 与 evidence。可部分核验，但未识别项仍保留 null；
   不要把“这页已看过”误称“字体、色值、组件均已完整编码”。
5. 精确组件、字体系、色卡集中定义；逐页通过 refs 关联，不重复复制一长串参数。
6. 导入前校验，再明确执行；图片或元数据版本变化时重新导出，不覆盖他人的更新。

命令（在 skill 的 scripts 目录）：

```powershell
python -X utf8 ppt_coding.py export --out "D:\...\编码清单.json"
python -X utf8 ppt_coding.py import --file "D:\...\完成编码.json"
python -X utf8 ppt_coding.py import --file "D:\...\完成编码.json" --execute
python -X utf8 ppt_coding.py coverage
```

第一次 import 仅校验；只有 `--execute` 才更改共享库。原目录只读，历史库版本和项目选定版本保持不变。
网页搜索支持身份编号和分类代码；“参考编码”页展示覆盖率及词表。

## 5. Agent 使用边界

- 用户说“只借结构”：只用职责/关系/布局，不继承参考标题、数字、机构、人物或品牌。
- 字体/色卡尚未核验：向用户提出可实施的设计选择，不能把猜测伪装成原稿的确定参数。
- 组件入模需先获项目许可并固定具体图片版本；截图证据仍不进入图像模型重绘。
- 购物车、收藏、批注不等于生产许可。当前生效方案只引用经 Agent 对齐后采用的资料。
- 批注绑定 asset_id + asset_version + image_sha256，输出原图路径、叠加预览、坐标记录；
  Agent 先解释理解及修改范围，不把所有红线直接变成蒙版。

## 6. 网页与品牌关联范本

- 类型隔离：`deck/slide → pages/PPT参考`，`webpage → webpages/网页设计参考`，
  `brand → branding/品牌素材`；角色功能图标仍为 `icon/components`，背景为 `background/materials`。
  分类不同不拆散套系；不把校徽、头像、背景当作额外 PPT 页面。
- 相同逻辑素材重拍必须传原 `id`、相同 `work`；保留 DK/PG，产生新图片/编码版本。
  先确认旧版本已 pin，再替换导出图片；所有受影响组件 bbox、来源哈希和关联成员哈希重编码。
- 动画网页先核对字体、图片与文字层显现状态。滚动驱动的渐隐需停在完整显现位置，
  不仅是固定等待；保存同次 viewport、scroll、opacity、DOM rect 与实拍时间。不注入 CSS 伪造状态。
- `decks[].reference_bundle`：schema_version=1，name，members，links，usage_boundary。
  member 含 asset_id/page_code/image_sha256/role（main 或 resource）；
  link 含 source（main ID）/target（resource ID）/relation（background/icon/brand/component）/evidence。
  成员必须是同 DK 的真实图片，哈希一致，不许重复或孤立；共享标识可连接多个 main。
  预览支持双向导航；整套播放只包含 main。历史套系按固定图片哈希解析匹配版本，不偷换新图。
- `pages[].applicability` 可针对 relations/typography/density/material 写
  `{state:"not_applicable",reason:"具体原因"}`；不能遮掩已有编码值。不适用不等于待编码。
- 原始品牌 PNG 保持透明度；JPEG 缩略图只做白底合成，不能将黑色透明底误当品牌设计。
- 范本中的 reviewed 表示具名证据复核，不表示用户阶段确认、品牌使用授权或生成许可。
