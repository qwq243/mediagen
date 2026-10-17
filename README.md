# Mediagen

用于图像生成与编辑、图片页 PPT 制作和媒体任务管理的本地技能工具集。

## 功能

- 通过 OpenAI-compatible 图像接口生成、编辑或批量处理图片。
- 图片页 PPT 工作台：内容与设计确认、素材职责、批注、版本、审核与导出。
- 页面知识与设计规格、提示词编译、资源索引及来源追踪。
- 可选视频通道：依赖单独部署的本地 workstation sidecar，本仓库不包含该服务。

这是**源码快照**，不是包含个人素材与全部外部服务的开箱即用发行包。

## 安装与配置

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
```

只通过环境变量 `NEWAPI_API_KEY` 或 `OPENAI_API_KEY` 提供自己的凭据，不写入配置、
脚本或 Git。`config.json` 只保存非敏感设置，已被 Git 忽略。

图像 API 地址请显式使用 `--base-url` 或环境变量 `NEWAPI_BASE_URL` 指定；
`config.example.json` 中的地址仅为示例，图像脚本不从该文件读取 API 地址。
`--model` 必须选择所用服务实际支持的模型；仓库不保证某个模型或渠道当前可用。
联网生成可能产生费用，不会因安装而自动执行。

先查看本地命令帮助（不发送生图请求）：

```powershell
python scripts/newapi_image.py --help
python scripts/init_ppt_image_job.py --help
python scripts/ppt_confirm_ui.py --help
```

基本用法示意，执行前自行替换服务地址与模型：

```powershell
python scripts/newapi_image.py generate `
  --base-url "https://your-image-service.example/v1" `
  --model "YOUR_SUPPORTED_IMAGE_MODEL" `
  --size 1024x1024 --quality high `
  --prompt "A minimal watercolor landscape without text" --out output.png
```

PPT 制作流程见 `SKILL.md` 与 `references/ppt-image-workflow.md`。
代码保留了部分机器特定路径及服务默认值；资源扫描应显式指定自己的目录，
视频功能需要另行配置 sidecar。文档中的用户路径只是示例。

## 仓库内容

| 目录 | 内容 |
| --- | --- |
| `scripts/` | Python 工具、工作台界面代码、必要 UI 图标与带许可的 vendor 代码 |
| `references/` | 使用说明、协议、提示词与配置描述；不含实际 PPT 素材 |
| `tests/` | 自动化测试源码与合成测试数据 |
| `agents/` | 技能元信息 |

**不上传 PPT 资源**：个人素材库、参考 PPT、资源预览图、生成成品、数据库、项目历史、
运行记录、本地配置、备份及第三方完整源码归档均不在仓库中。
旧版界面附带的 `style_previews` 示意图也已排除，相关旧版预览可能不显示。
必要界面图标和运行时描述性配置不是 PPT 素材。

## 验证与许可

本次发布只整理源码并做静态发布检查，**未重新运行测试、构建、生图或浏览器验收**。
测试源码的存在不代表所有功能均已在新环境验证。

公开可见不等于授予统一开源许可；本仓库暂未为原创部分指定统一许可证。
第三方部分继续遵守各自许可证，详见 `THIRD_PARTY_NOTICES.md`。
