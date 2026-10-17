# 学姐用的生图（中文预设通道）

面向「不研究参数、只要一张能用的图」的使用者：头像、壁纸、朋友圈配图、封面、贺卡、贴纸、表情包、海报。

一句话需求 → 一张成品图。用 `scripts/xuejie_gen.py`，它把参数按用途锁死，只让你填主题和文案，拼好提示词后转调 `newapi_image.py`。

## 什么时候走这个通道

- 生活/社交类图：头像、壁纸、朋友圈配图、小红书或公众号封面、贺卡、手账贴纸、聊天表情、社团海报。
- 使用者不是工程师，只需要「说清楚要什么」然后拿到文件。

不走这里：

- 幻灯片/课件页 → `references/ppt-image-workflow.md`（`lecture` / `dense` / `reconstruction`）。
- 论文配图、图文摘要、机制示意图 → `references/paper-figure-workflow.md`（内容层是 `nature-figure`）。
- **带数据的图（柱状/折线/热图/表格/统计面板）永远不进图像模型**——那是造证据，用真实数据画。

## 第一次用：三步

1. **配密钥**（只需一次）。密钥只留在本机环境变量里，绝不写进脚本、图片说明或聊天：
   - 图形界面：`C:/Users/USER/.codex/skills/mediagen/scripts/open_newapi_credentials.cmd`
   - 或者：`[Environment]::SetEnvironmentVariable("NEWAPI_API_KEY", "<本机输入，别贴聊天里>", "User")`
2. **看预设**：`python scripts/xuejie_gen.py --list`
3. **先出一张**：`python scripts/xuejie_gen.py 头像 --subject "戴圆框眼镜的橘猫"`，满意了再加 `--open` 让系统看图器自动打开。

## 预设表

| 预设 | 用途 | 默认档位 | 文字 | 备注 |
|---|---|---|---|---|
| `头像` | 微信/QQ/平台头像 | 1k 1:1 | 不放字 | 缩小到 96px 要认得出 |
| `壁纸` | 手机/电脑壁纸 | 2k 9:16 | 不放字 | `--orient landscape` 出横版 |
| `朋友圈` | 朋友圈/空间配图 | 1k 3:4 | ≤10 字 | 字越短越好 |
| `封面` | 小红书/公众号/B站封面 | 2k 3:4 | ≤10 字 | `--orient landscape` 出 16:9 |
| `贺卡` | 生日/节日祝福卡 | 1k 3:4 | ≤16 字 | 署名给 `--subtext` |
| `贴纸` | 手账/聊天贴纸 | 1k 1:1 透明 | 不放字 | 原生透明 PNG，不抠图 |
| `表情包` | 聊天表情 | 1k 1:1 | ≤6 字 | 台词大字压底 |
| `海报` | 社团/活动海报 | 2k 3:4 | ≤24 字 | 标题/副标题/时间地点三段 |

英文别名同样可用：`avatar` `wallpaper` `moments` `cover` `card` `sticker` `meme` `poster`。

## 常用命令

```powershell
# 光看参数拼成什么样，不花钱
python scripts/xuejie_gen.py 封面 --subject "秋日校园银杏" --text "社团招新" --subtext "9月28日 图书馆前广场" --print-prompt

# 出一张封面（默认存 封面_秋日校园银杏.png，重名自动加 -v2，不覆盖）
python scripts/xuejie_gen.py 封面 --subject "秋日校园银杏" --text "社团招新" --subtext "9月28日 图书馆前广场" --open

# 表情包：台词进图，6 字以内
python scripts/xuejie_gen.py 表情包 --subject "一只摊在桌上的橘猫" --text "不想动"

# 横版电脑壁纸
python scripts/xuejie_gen.py 壁纸 --subject "雨后远山与云海" --orient landscape

# 换风格 / 换档位 / 换模型
python scripts/xuejie_gen.py 头像 --subject "抱着橘子的女孩背影" --style "日系水彩插画，淡青与米白" --tier 2k
```

不写 `--out` 时文件名是 `预设_主题.png`；也可以 `--out 招新封面.png` 自己指定。

## 参数锁（别乱动）

`quality=high`、`response_format=url`、`stream=true`、`transport=auto` 是这台机器验证过的组合，交给脚本默认值即可。要调只在三种情况下调：

- 出图慢或断流：加 `--no-stream` 重试同一份提示词，别改模型和提示词。
- 网络层报连接重置：先看 [proxy-and-fallback](proxy-and-fallback.md)，脚本自己会试直连和本地代理。
- 报错说模型不支持尺寸/参数：把尺寸落回 `--tier 1k --aspect 1:1`（1024x1024）再试。

尺寸是**意图**不是承诺：这个接口可能重采样（请求 1024x1024 实际回 1254x1254 是正常的）。

## 中文文字的四条规矩

模型最容易在这里翻车，脚本已经把约束写进提示词，人工要守的是：

1. **字数**：头像一个字都不要；表情包台词 ≤6 字；封面标题 ≤10 字；海报标题+信息合计 ≤24 字。
2. **照抄**：只写你要的那几个字，模型会自作主张加英文副标题和口号，提示词里已声明「不要加我没给的字」——出图后逐字核对。
3. **字形**：要求「等笔画黑体感、字形完整」，别指望它认字体名（写「用微软雅黑」基本无效）。
4. **改字别重生成**：图上文字错了或多了，用 `edit` 带上原图只改那一处，不要让模型重画整张（重画必然换构图）。

## 从草稿到系列

1. 先出一张，看构图和文字对不对。
2. 定稿那张就是母版；后面同系列用 `edit` 以它为底图派生（换文案、换配色），风格才不会跑。
3. 存 `-v2` / `-v3`，**不要覆盖**已确认的成品。

```powershell
python scripts/newapi_image.py edit --image 封面_秋日校园银杏.png `
  --prompt "只把主标题改成「社团招新第二轮」，其余构图、配色、字体全部保持不变" `
  --tier 2k --aspect 3:4 --out 封面_秋日校园银杏-v2.png
```

## 红线（不做）

- 不生成**他人**的肖像、不做换脸、不把真人照片改成不雅或误导性内容。
- 不做证件照/票据/公文/证书样式用于身份或资格核验；形象照只作个人社交用途。
- 不带真实品牌 logo、校徽、赛事标识（模型会自己编造，出图后要检查）。
- 不生成涉政、涉黄、涉赌、暴力血腥内容。
- 出图是 AI 生成的，用于公开发布时按平台要求标注，别当新闻照片用。

## 翻车对照表

| 现象 | 原因 | 改法 |
|---|---|---|
| 图里出现多余英文/口号 | 模型默认爱加副标题 | 提示词已禁止，仍出现就用 `edit` 抹掉那行 |
| 中文字缺笔、错字 | 字形约束不够 | 缩短文案，重出 2-3 版挑；或 `edit` 局部改字 |
| 头像缩小后糊成一团 | 元素太多 | 主体再简化，`--style "极简、单主体、纯色背景"` |
| 壁纸被状态栏压住主体 | 构图没留安全区 | 提示词已留上方空区；仍压住就 `--style "主体下沉到画面下三分之一"` |
| 透明贴纸有灰底 | 请求走了不支持透明底的分支 | 保持 `贴纸` 预设默认（脚本自带 `--transparent`），别手动加 `--size` |
| 颜色/风格和上一张差很远 | 每张都是独立生成 | 以定稿为底图 `edit` 派生，别重新 `generate` |
| 报 401/403 | 密钥没配或过期 | 重跑 `open_newapi_credentials.cmd` |
| 报连接重置/超时 | 网络层（不是提示词） | 见 [proxy-and-fallback](proxy-and-fallback.md) |

## 文件放在哪

- 给项目/社团用的成品：放该项目自己的工作区（如 `assets/`、`docs/design/`），别只留在临时目录。
- 批量生成可写 JSONL 后走 `newapi_image.py batch`（见 [generate-edit-batch](generate-edit-batch.md)）。
- 需要复现的资产，把提示词记一行到 `docs/design/image-prompts.jsonl`（规则见 [asset-policies](asset-policies.md)）。
