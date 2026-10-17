# 图片型 PPT 数据与工具合同（v3）

仅 PPT 通道适用；普通生图、论文概念配图、生视频保持原路由。
唯一生产真值是任务目录的 `prompt-pack.json`。Markdown、JSONL 是其派生文档，
不允许改了派生文档却继续拿旧 JSON 生图。

## 核心字段

- `schema_version: 3`、`revision`、`project_id`、`project_name`。旧数据保留 `prior_receipts`，
  不把旧版本审核追认为新版本通过；每次保存前建立 `revisions/` 不可变快照。
- `resource_cart[]`：收集意图，不进入生产 hash。固定资产 id/version/hash、借鉴方式、说明，
  或用户提供的外部 URL；提交快照作为 revision_request 交给 Agent。
- `asset_selection[]`：Agent对齐后用于生产的固定版本；含 usage、model_allowed、protected_evidence。
  structure-only 不上传模型；真实证据必须确定性合成。
- `component_pack`：enabled、variants（cover/content/divider/closing）、chapters、progress_mode。
  页码/总页数/标题/当前章节从当前页序计算；固定外观资产放 asset_selection，页面用 asset_ids 指定。
- `revision_requests[]`：draft/submitted/applied/discarded，原方案 hash、patch、comment、impact。
  `annotations[]` 记录页、候选 id、原图 hash、归一化坐标、工具和说明，原图不涂改。
  `composition_records`、`asset_exports`、`edit_plans` 为合成、交接、编辑台账。
- `communication`：观众、意图、希望观众发生的改变、主旨、交付场景、后续用途；
  `organization` 和理由为开放文本；`reading_mode` 为 presentation/text/balanced；
  `duration_seconds` 仅指 PPT 段，不自动包含演示和答辩。
  `page_count` 为可选对象：`mode:recommend/exact/range`；exact 使用正整数 `count`，
  range 使用正整数 `min/max`（min≤max），非当前模式的数值为空。
  第一轮确认页数要求，不要求当时已有匹配的分镜；第二轮确认和生产门禁检查实际总页数
  （含封面、尾页）。变更需走修订与重新确认；旧任务缺此字段不在读取时自动改写。
- `design`：色卡、display/heading/body/numbers 角色字体、层级字号、图标、材质、
  网格、人物政策、视觉指令语言。默认 `human_policy:none`、`text_in_image:true`。
  角色字体可以不同，同角色跨页保持一致；艺术字并不被全局禁用。
- `references[]`：id、title、url/path、role（style/content/evidence）、use、license、
  preserve、redraw_allowed、upload_allowed、send_to_model。
  URL 仅作来源与导航，不自动抓图；授权不清不复制；上传需用户明确许可。
  **证据图禁止上传图像模型重画**。
  网页新输入的本地路径先记为 requested_path/pending_agent_inspection，不直接读文件或上传。
  agent 核验素材与权限后使用 reference 入口导入 assets 管理副本；不能把证据改标签成风格图。
  可记录 human_content:none/real/illustrated/unknown，帮助执行人物政策。
- `pages[]`：page_id、page_role、page_text、logic、layout_focus、visual_instructions、
  reference_ids、materials、speaker_notes、selected_output、可选 transition、
  must_preserve、required_elements、forbidden_elements。
  `logic` 包含 purpose、key_message_or_question、evidence、information_relationship、
  visual_expression、transition_in/out、duration_seconds，不限定一种标题或叙事语法。
- `materials[]` 为证据合成槽：`reference_id` 和 `box:[x,y,w,h]`，归一化坐标；
  保持原图比例，不更改原始素材。没有合成槽不要假装真实证据已插入。
- `selected_output` 记录具体选定文件、选择时 hash、kind 和来源；
  generated/legacy/mock/reference 必须如实区分。
  v3 使用 output_candidates 区分 generated / agent_composite / user_import，导入不自动选定。
  candidate-audit 必须对应当前候选哈希；adopt 需要通过审核且无未处理修订。
  generated 必须匹配受控调用记录的输出路径和 hash；导入历史图用 legacy。
  mock/reference 不能作为真实任务的生成样张或交付图；仅显式 test_fixture 离线夹具例外。
- `notes_policy` 默认 enabled:true、mode:generate、audio:false。
  有原稿询问 optimize 或 preserve，不默认覆盖。AI 讲稿由当前 agent 创作，
  这个本地脚本不进行文字推理调用。
- `transition` 默认关闭；开启推荐 fade/0.4 秒/manual，无声音；
  可选 fade/push/wipe/split/cover，逐页 override 继承全套设置。
- `approvals`、`audits`、`generation_authorization`、`generation_calls`、`deliveries`
  记录确认与生产证据；不得手改“passed”替代实际检查。

## 哈希与闸门

- stage1 只绑定沟通场景/目标/时长/参考方向，不绑定逐页文案；content 绑定完整逻辑和证据。
  stage2 绑定完整方案、设计、素材、生产设置。只调整某页不无故重开第一轮沟通。
- prompts 绑定当前编译提示词；visual 绑定单页实际图片；samples 绑定封面和代表页；
  deck 绑定整套选择结果；notes 另绑定最终讲稿。
- 改内容会使内容和相关下游确认失效；页级视觉 hash 不包含其他页面文字、讲稿和转场。
  改色卡/字体会使全套视觉失效；已批准锚点变化会使依赖它的页面视觉审核失效；
  原地替换参考/图片文件同样失效；仅改讲稿不要求重新生图，但须重新核对讲稿。
- 尺寸检查不是视觉审核。审核报告必须有独立 reviewer、具体 evidence、
  当前 subject_hash、findings 和 passed/failed/pending。
  未修复 major/blocker 不得通过。看不到图片就 pending，不能猜。
- 自动拦截 required_elements/forbidden_elements 同名冲突，以及少量高置信度的
  通栏色带、深底、霓虹和全局字体禁用冲突。它不替代语义审核：
  原文显示文本不是绘图指令；复杂否定、角色限定和隐含矛盾仍由独立提示词审核判断。
- 历史状态字段、旧助手“逐字无误”口述、空勾选表均不迁移成新审批。

## 工具入口

下面命令的脚本绝对路径为
`C:\Users\USER\.codex\skills\mediagen\scripts\ppt_workflow.py`。
`--job` 指用户指定的任务目录，不能默认为当前无关仓库。

```text
--job <dir> init --name <title>                 空任务，不覆盖旧文件
--job <dir> migrate                            保留旧 JSON 快照，无审核追认
--job <dir> check [--target inspect|samples|render|export]
--job <dir> compile                            编译提示词，不收费
--job <dir> confirm --stage stage1|stage2|samples --evidence <真实用户答复>
--job <dir> audit --report <实际审核报告.json>
--job <dir> reference --file <核验后的素材元数据.json>
--job <dir> select --page P01 --image <file> --kind generated|legacy|mock|reference --provenance <来源>
--job <dir> authorize --calls <N> --evidence <用户授权原文及预算>
--job <dir> render --lane samples --pages P01 P02  dry-run，不发模型请求
--job <dir> render --lane samples --pages P01 P02 --execute --ack-cost
--job <dir> render --lane deck --pages P03 P04     后续页延续已批准视觉参考
--job <dir> export --out <新的版本.pptx>
--job <dir> feedback --file <评价.json>
--job <dir> index
library --search <关键词> [--kind reference|preference|feedback|issue|lesson|project]
library --add <元数据.json> --kind reference
```

样张 render 需要两阶段确认和内容、提示词审核；其他页还需要样张通过。
实际 render 必须有当前授权和调用次数预算；失败计入尝试，停止且不自动换模型、
降质量、加预算、重复请求。出图后还必须独立读图审核，脚本不自动判美观。
v3 render 输出候选，需 `ppt_studio candidate-audit` 后 `adopt`，不自动覆盖当前选定图。
auto 在样张未确认时按指定代表页推断，样张已确认后走 deck 编辑线；明确指定 lane 更好。
同角色内容页默认参考已批准代表内容页；封面/过渡/收尾默认参考封面，
也可指定 style_reference_page_id（只能选当前批准样张）。
保存带源文件 hash 比对及排他写锁，检测并发编辑后停止，不覆盖较新的网页/agent 修改。

审核文件形状：

```json
{
  "phase": "visual",
  "page_id": "P02",
  "independent": true,
  "reviewer": "实际审核者及运行标识",
  "subject_hash": "从 select / check 取得的当前哈希",
  "status": "pending",
  "evidence": ["实际读取的文件、观察位置、工具记录"],
  "findings": [
    {"severity": "major", "description": "具体问题", "resolution": "pending"}
  ]
}
```

## 共享库

`C:\Users\USER\.mediagen\library\index.sqlite3` 为追加式经验索引，不放入技能安装目录。
参考、项目版本、反馈、偏好、问题、候选经验分别保存；无密钥、Cookie 或登录 URL。
单次主观反馈保存适用场景和来源，不自动升级为所有 PPT 的规则。
feedback 支持 comment、scope 和 preferences/issues/lessons 数组；分别索引，保留候选或未修复状态。
先检索相似任务；明确用户偏好可优先推荐；已解决重复问题才提炼成通用经验。

交付时邀请用户说视觉/逻辑/文字量/讲稿/动效；尚未使用保留 pending。
普通生图也可检索 reference/preference，但不强制套 PPT 的确认闸门。

资源、购物车、修订、合成和编辑的具体命令见 [ppt-resource-workbench.md](ppt-resource-workbench.md)。
