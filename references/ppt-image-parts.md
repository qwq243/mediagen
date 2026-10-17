# 局部素材、固定组件、图例与精确留空

## 用户界面与 Agent 的分工

网页负责看图、购物、裁切、选择固定组件、指定区域与就地批注。详细制作要求继续在 Codex
与 Agent 对齐，不重新增加“参考网址 + 名字 + 长意见”表单。网页上的保存不等于用户付费授权，
也不等于上传参考图给模型的许可。真实项目不出现测试假设、验收样本文案。

## 编码图例

`#coding` 展示本机真实图片，不以绘制的占位图冒充案例。布局、组件、字型、页面职责、
信息关系、整套叙事、信息密度和材质分开。图例匹配沿用现有标注的复核状态：
标签推得的 suggested 仍需核验；没有可靠图例时留空。字型示例不等于已确认字体名称。

Agent 与网页共用：

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/ppt_coding.py examples --group layout --code LY-SPLIT-2
python C:/Users/USER/.codex/skills/mediagen/scripts/ppt_coding.py examples --group component --code CP-TOPBAR
```

结果含原图路径、id/version/sha256、编码和匹配依据。Agent必须看实际图片，再决定是否借鉴；
不把图例里的标题、事实、数字、品牌或版权信息写入待生成页面。

## 原图局部 → 独立素材 → 风格变体

大图中的“截取局部”按原图像素保存，坐标是 `[left,top,right,bottom]` 归一化值；
资源编码/布局的 `box` 则是 `[x,y,width,height]`，不能混用。

`library/fragments/crop-*/` 保存原图快照、fragment.png、derivation.json。
记录原版本、父资产、像素边界、标签、是否含真实证据。裁切不自动继承整页的事实或字体/色卡。
网页可再次精选、加入购物车、选为组件；Agent可用 `ppt_fragments.py --job ... --spec ...` 同步处理。
有可验证的原图生成记录时，一起保存为 source_generation_recipe，而非声称裁切图是一次新模型生成。

生成适配变体仍走 `ppt_studio.py asset-request / asset-authorize / asset-render`：
- spec.kind 可用 header/footer/navigation/brand/icon/background/illustration 等，不要求先完成整套PPT。
- references 写裁切图的准确 id/version，parent 写主原素材的 id/version。
- prompt 说明允许调整的色卡、材质、边缘、比例，以及不继承哪些文字。
- 透明背景按任务选择；真实品牌要严格保真时，推荐原图合成，不保证模型重画一致。
- 独立请求/提示词准备不收费；调用必须再有明确费用授权和有限次数。

## 固定组件包

`#components` 显示当前包、待对齐选择和页面留空。素材大图点“选为固定组件”：
选择部位、适用页面、使用方式（参考融图 / 先生成适配变体 / 保留原像素合成）。
保存产生 `revision_requests.kind=fixed_component`，同时加入项目素材清单；
不改当前 component_pack，不确认方案，不直接生成。

Agent对齐后：

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/ppt_components.py --job <项目> apply `
  --request <请求ID> --summary "用户确认后的用途及变化范围" `
  --result-id <选定变体ID> --result-version <准确版本> --model-upload-allowed
```

只有用户同意发送参考图时才加 `--model-upload-allowed`，这不是费用授权。
选“变体”必须有不同的产物版本且 parent 对应原素材；原裁切不能冒充适配变体。
保真合成不发送模型，需提供 `--box x y w h`，范围0–1。`items` 中记录
slot、scope、asset_id、version、sha256、mode、box。specific page role 覆盖同部位 all。
组件图只固定装饰外观；标题/章节/页码/总页数由当前页面记录计算。
**不要把参考图自带的旧标题、旧页码直接贴遍全套**；若裁切里有这些文字，
先生成无字变体，或采用现有确定性文字/进度合成配方更新动态内容。

采纳组件后相关设计确认、样张和视觉审核按 hash 失效。独立素材若仍只是候选，
需实际读图审核并与用户确认后才采用，不能用测试记录放行。

## 区域留空、透明底板与编辑蒙版不是一回事

| 模式 | 做什么 | 精确性与边界 |
|---|---|---|
| prompt_only | 提示模型避免在指定范围放文字/装饰 | 需要真实结果审核，不保证精确 |
| solid | 生成后按像素范围填指定颜色 | 确定性处理；会清除框内内容 |
| transparent | 生成后把区域变透明，输出PNG底板 | 为 Agent/用户后续合成；不是PPT可编辑图层 |
| edit_mask | 对已有图片生成同尺寸RGBA蒙版 | 框内透明为请求编辑区，外部不透明；实际模型服从度待实测 |

网页支持拖框和 X/Y/宽/高像素输入。原图版本、坐标空间、像素边界、原图快照与 mask.png
保存在 `project/regions/zone-*/`；候选图片与选定图片不混淆。没有成图时只提供版式留空，
不能伪造已有图的编辑蒙版。含真实证据的扁平成图不得送模型编辑。

所有区域操作先生成待对齐请求。预留区域变更还需核对：
1. 文字与证据是否被挡住，是否需要重新排版或调整可见文案；
2. 与页眉、品牌及安全边距是否冲突；
3. 透明底板是否采用 agent_composite/external 路线，最终回传图是否完整。

Agent用正常 `ppt_studio.py resolve --patch ...` 合并/重定向区域方案，再重新过内容与提示词审核。
留空/蒙版按钮不自动执行编辑或重生图。要在已有图上确定性做底板：

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/ppt_regions.py --job <项目> materialize --page P02 --candidate <图片ID>
```

须先解决待处理修改；输出新 agent_composite 候选、配方与输入/输出hash，不覆盖原图或自动采纳。
mask交给 `ppt_studio.py prepare-edit --mask ...`，再进行编辑专属提示词审核/费用授权。
不以 mask.png 存在或尺寸正确，宣称当前渠道已通过蒙版能力验证。

## 图片生成记录

`newapi_image.py generate/edit/variation` 保存每次实际请求的：
请求模型、上游明确返回的模型（没有就未知）、提示词、实际请求参数、
后处理参数、完整输入图片和蒙版快照、原始产物快照、父生成记录ID。
原输出旁有 `.recipe.json`；完整档案在 `generation-records/gen-*/`。
项目/资产导入会复制完整档案而非依赖临时路径。重复导入相同记录保持幂等。

浏览器“生成记录”以可读字段和输入图展示；可导出JSON供Agent重建请求。
未报告的随机种子、上游路由、默认参数不猜；有相同输入和参数也不保证像素完全一致。
旧图没有记录则明示缺失。dry-run不建生成档案、不发请求、不产生费用。
来源裁切、确定性合成和真实模型生成分开标记；密钥/Authorization/Cookie不入档案。

## 就地批注

画圈/框/箭头/自由线后，在附近的小弹窗直接写文字。编号可再点开修改或删除。
`annotation.json` 同时有每个形状的 comment 和归一化/像素坐标；marked-preview.png
保留对应编号。Agent要同时读原图、叠加图与逐条comment，不能只看总留言。
普通批注不是蒙版，除非用户明确提出编辑范围并经对齐转换。
# 精确嵌入导入图片

「固定组件与留空 → 设置区域 → 直接嵌入图片」可搜索已入库图片、选用购物车图片或从本机导入。
在同一画布输入 X/Y/宽/高原始像素并预览，记录时归一为 `[x,y,width,height]`，绑定源素材
ID、版本、SHA256、项目冻结副本和适配方式。不把网页缩放坐标当作原图像素。

- `reserved_regions[].mode="image"`，内含 `embedded_asset`；默认 `fit="contain"` 等比完整显示。
  非证据装饰图可选择 `cover` 居中裁切；不支持拉伸。真实截图/数据图完整保留且不上传模型。
- 仍先生成待 Agent 对齐的修订，不自动采纳或付费。采纳后由 `finish_layout` 精确合成，
  或 `ppt_regions.py materialize` 在现有图上产生新候选；不覆盖原图。
- 模型提示词只得到区域、用途和避让要求，不得到嵌入文件路径、内部资产元数据或证据像素。
- 导出所选页面的素材包时带上该页冻结的嵌入图片；不是导出整个素材库。
- 图片位置、大小、比例与周围内容仍须视觉审核。代码能保证像素区域和源文件不变，
  不能保证模型在附近没有产生多余文字或装饰。

