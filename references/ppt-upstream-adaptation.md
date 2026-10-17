# 上游来源与取舍（2026-10-14 核验）

稳定版以执行时 GitHub Releases API 为准，归档的 SHA-256 与路径见
`C:\Users\USER\.mediagen\source-manifest.json`。不把 main 的当前许可误写到旧 tag。

| 项目 | 固定版本 | 此版本许可 | 本次用途 |
| --- | --- | --- | --- |
| hugohe3/ppt-master | v6.7.0 | MIT，Hugo He | 直接复用两阶段网页控件、设计候选、色卡、字体与示意预览、原生 PPTX 转场核心；安装目录更新至该版 |
| ningzimu/codex-ppt-skill | v0.6.0 | MIT | 研究内容规划、工作区与验收组织，不复制其强制子代理或不适合图片页的生产约束 |
| Anionex/banana-slides | v0.4.0 | CC BY-NC-SA 4.0 | 固定副本仅研究大纲—页面描述—生图—编辑思路，不复制代码或素材进入 mediagen |

直接复用文件在 `scripts/vendor/ppt_master`，保留 LICENSE、UPSTREAM.json 和上游版权。
`app.js`、`index.html` 是适配后的文件；完整原始源归档在共享目录 sources。
适配范围：原生 template workspace 安装及 SVG 执行控件退出此生产线；接入图片页人物政策、
素材职责、真实样张、确认哈希和反馈；阶段 final 显式映射为 stage2。

普通生图和视频引擎没有替换。引用上游完整讲稿、最终页面核对和转场/动画分离的方法，
不把整页烤字图片说成对象级可编辑，也不支持图中文字逐条动画。

## v3 交互适配

保留上游 MIT 代码与 LICENSE；旧界面仍可在 `/legacy` 访问。新的
`scripts/static/ppt-workbench` 是自写的分阶段界面，复用两轮沟通/完整设计确认思想，
不声称新页面布局是上游原样。原生转场核心继续直接使用保留许可的 vendor 模块。
新增资源购物车、固定版本、圈画批注与候选审核，不复制 banana-slides 的代码或素材。

网站素材的许可必须逐条核验，网站入口不代表其素材全部可复制。共享库中 prompt 模板
索引现有本地模板的地址、标签和用途；新增的公共检索仅调用 Wikimedia Commons 官方
Imageinfo/search API 返回原页与缩略图链接。其他网站是导航入口，不冒称有可用 API，
不抓取整站、不登录、不付费下载；用户选择后的文件通过上传或 Agent 本机导入。

备份只用于本机回滚：包含配置的备份不得作为案例、提示词或对外报告附件。

## 资源界面视觉参考

在用户解锁 AboutPPT 页面后，实际查看了网站分类与链接；只记录部分名称/网址，不复制
整站描述。用户指出该站也不够美观，因此不按其页面克隆。比较了：

- `bastienwirtz/homer` 的公开演示：分类层级、统一搜索。
- `linkwarden/linkwarden` 的公开演示：收藏组织、素材卡片与预览。
- 本机 `ppt-master` 的确认界面，以及 `frontend-design`、`ui-ux-pro-max` 的本地设计说明。

这些仅作界面参考；新工作台的 HTML/CSS/JS 为本机编写，不引入这些项目的运行时或
复制其源码。工作台导航色与 PPT 设计色分离。图标采用本地文字字标，不冒充网站官方
品牌标志。公共 API 适配仍仅 Commons；其余是明确的外链，不承诺接口可用。
