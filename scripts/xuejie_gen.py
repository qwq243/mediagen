#!/usr/bin/env python3
"""学姐用的生图 —— 中文预设通道（薄封装，转调同目录的 newapi_image.py）。

一句话需求 -> 一张能用图。参数按用途锁死，使用者只需要给主题和文案。

用法：
  python xuejie_gen.py --list
  python xuejie_gen.py 头像 --subject "戴圆框眼镜的橘猫"
  python xuejie_gen.py 封面 --subject "秋日校园银杏" --text "社团招新" --subtext "9月28日 图书馆前广场"
  python xuejie_gen.py 贺卡 --subject "康乃馨和奶油蛋糕" --text "生日快乐" --dry-run
  python xuejie_gen.py 壁纸 --subject "雨后远山" --orient landscape

本脚本不含任何密钥；密钥只从环境变量 NEWAPI_API_KEY 读（由 newapi_image.py 负责）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:  # 中文提示不乱码
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - 老 Python / 非交互流
    pass

HERE = Path(__file__).resolve().parent
GENERATOR = HERE / "newapi_image.py"

# 中文字形锁：模型爱丢的中文约束，固定复用（见 references/gpt-image-prompting.md）
CJK_LOCK = (
    "图中文字只用简体中文，逐字照抄我给的文字，字形完整、笔画清晰、排版整齐；"
    "不要乱码、不要缺字、不要拼音、不要英文副标题、不要加我没有给的字、不要水印和签名。"
)
NO_JUNK = (
    "不要文字水印、不要签名、不要 logo、不要边框、不要手指畸变、不要多余肢体、"
    "不要低清噪点、不要拼接感、不要模板化塑料质感。"
)

PRESETS: Dict[str, Dict[str, object]] = {
    "头像": {
        "aliases": ["avatar", "touxiang"],
        "use": "微信 / QQ / 学习平台头像",
        "tier": "1k",
        "aspect": "1:1",
        "text": False,
        "text_max": 0,
        "style_default": "干净背景、柔和自然光、主体居中、半身构图、细节干净利落",
        "layout": "方形头像构图：主体头部位于画面上三分之一区域，四周留出安全边距，缩小到 96px 仍能看清是谁。",
        "notes": "头像不要塞字，缩小后必糊。",
    },
    "壁纸": {
        "aliases": ["wallpaper", "bizhi"],
        "use": "手机 / 电脑壁纸",
        "tier": "2k",
        "aspect": "9:16",
        "text": False,
        "text_max": 0,
        "style_default": "大面积呼吸感留白或柔和虚化、层次分明、低饱和耐看、光线柔和",
        "layout": "主体偏一侧或下三分之一，画面上部留出状态栏与图标区，不被主体压住；无文字。",
        "notes": "竖版给手机、加 --orient landscape 出横版电脑壁纸。",
    },
    "朋友圈": {
        "aliases": ["moments", "pengyouquan"],
        "use": "朋友圈 / 空间 / 相册配图",
        "tier": "1k",
        "aspect": "3:4",
        "text": True,
        "text_max": 10,
        "style_default": "生活感、自然光、轻微胶片颗粒、构图松弛不做作",
        "layout": "竖版单图：一个主体、一处空隙，文字排在下方或留白处，字号克制。",
        "notes": "配图文字越短越好，10 字以内。",
    },
    "封面": {
        "aliases": ["cover", "fengmian"],
        "use": "小红书 / 公众号 / B站 封面",
        "tier": "2k",
        "aspect": "3:4",
        "text": True,
        "text_max": 10,
        "style_default": "竖版封面感、主色统一、对比清楚、缩略图也认得出主题",
        "layout": (
            "竖版封面：主标题占上方三分之一、超大加粗居中，副标题一行压在标题下方，"
            "主体图形或照片占中下部，四周留安全边距。"
        ),
        "notes": "加 --orient landscape 出 16:9 横版封面（B站 / 公众号头图）。",
    },
    "贺卡": {
        "aliases": ["card", "heka"],
        "use": "生日 / 节日祝福卡",
        "tier": "1k",
        "aspect": "3:4",
        "text": True,
        "text_max": 16,
        "style_default": "温暖手作质感、柔和纸纹、花材或甜点元素、配色干净",
        "layout": "竖版贺卡：祝词居中偏上、分行排布，装饰元素在四周环绕，四周留白不拥挤。",
        "notes": "祝词用 --text，署名给 --subtext。",
    },
    "贴纸": {
        "aliases": ["sticker", "tiezhi"],
        "use": "手账 / 聊天贴纸（透明底 PNG）",
        "tier": "1k",
        "aspect": "1:1",
        "text": False,
        "text_max": 4,
        "style_default": "扁平插画、粗描边、纯色块、高对比、无投影无底色",
        "layout": "单一主体居中、占画面 70% 左右、边缘完整不裁切、背景全透明。",
        "notes": "透明底由 --transparent 走模型原生 RGBA，不要自己抠图。",
        "transparent": True,
    },
    "表情包": {
        "aliases": ["meme", "biaoqingbao"],
        "use": "聊天表情 / 群图",
        "tier": "1k",
        "aspect": "1:1",
        "text": True,
        "text_max": 6,
        "style_default": "手绘涂鸦感、表情夸张、线条活泼、配色欢快",
        "layout": "方形表情：主体占上半部、表情夸张好认，台词用大字压在下方三分之一，字号大、可读。",
        "notes": "台词 6 字以内才认得出。",
    },
    "海报": {
        "aliases": ["poster", "haibao"],
        "use": "社团 / 活动 / 宣讲海报",
        "tier": "2k",
        "aspect": "3:4",
        "text": True,
        "text_max": 24,
        "style_default": "校园社团风、主色统一、信息层级清楚、留白干净",
        "layout": (
            "海报：主标题最大居中偏上，副标题一行，主体图在中部，"
            "时间地点等信息排在最下方一行，全部文字左对齐或居中成一条中轴。"
        ),
        "notes": "标题 --text，副标题 --subtext，时间地点 --info。",
    },
}

ALIAS_TO_KEY = {k: k for k in PRESETS}
for _key, _meta in PRESETS.items():
    for _alias in _meta["aliases"]:  # type: ignore[index]
        ALIAS_TO_KEY[str(_alias).lower()] = _key


def resolve_preset(name: str) -> str:
    key = ALIAS_TO_KEY.get(name) or ALIAS_TO_KEY.get(name.strip().lower())
    if not key:
        die(f"没有这个预设：{name}\n可用的有：{'、'.join(PRESETS)}（见 --list）")
    return key


def die(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)
    raise SystemExit(2)


def print_list() -> None:
    print("学姐用的生图 —— 可用预设\n")
    for key, meta in PRESETS.items():
        texts = "要不要写字" if meta["text"] else "不放文字"
        tier, aspect = meta["tier"], meta["aspect"]
        print(f"  {key:<4} {meta['use']}  ·  {tier} {aspect}  ·  {texts}")
        print(f"       默认风格：{meta['style_default']}")
        print(f"       提示：{meta['notes']}\n")
    print("示例：python xuejie_gen.py 头像 --subject \"戴圆框眼镜的橘猫\"\n")


def text_block(text: Optional[str], subtext: Optional[str], info: Optional[str], text_max: int) -> str:
    parts: List[str] = []
    if text:
        if text_max and len(text) > text_max:
            print(f"[提醒] 主文案 {len(text)} 字，超过建议的 {text_max} 字，模型容易写错或排不下。", file=sys.stderr)
        parts.append(f"主文字：「{text}」")
    if subtext:
        parts.append(f"第二行文字：「{subtext}」")
    if info:
        parts.append(f"底部信息文字：「{info}」")
    if not parts:
        return "画面里不要出现任何文字。"
    body = "，".join(parts)
    return f"{body}。{CJK_LOCK}"


def build_prompt(preset: str, args: argparse.Namespace) -> str:
    meta = PRESETS[preset]
    subject = args.subject or args.text or preset
    style = args.style or meta["style_default"]
    orient = args.orient
    layout = meta["layout"]
    if orient == "landscape" and preset in ("壁纸", "封面", "海报"):
        layout = "横版构图：" + str(layout).split("：", 1)[-1]
    blocks = [
        f"用途：{meta['use']}（{preset}）。",
        f"画面主体：{subject}。",
        f"构图：{layout}",
        f"风格质感：{style}。",
        text_block(args.text, args.subtext, args.info, int(meta["text_max"])),
        "画面干净、印刷级清晰，主体边缘锐利。",
        NO_JUNK,
    ]
    if args.extra_note:
        blocks.insert(-2, f"补充要求：{args.extra_note}。")
    return "\n".join(b for b in blocks if b)


def aspect_for(preset: str, orient: Optional[str], args: argparse.Namespace) -> str:
    if args.aspect:
        return args.aspect
    meta = PRESETS[preset]
    aspect = str(meta["aspect"])
    if orient == "landscape" and aspect in ("9:16", "3:4"):
        return "4:3" if aspect == "3:4" else "16:9"
    if orient == "portrait" and aspect in ("16:9", "4:3"):
        return "3:4" if aspect == "4:3" else "9:16"
    return aspect


def slugify(text: str, limit: int = 14) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "", text or "")
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned)
    return (cleaned[:limit] or "图")


def default_out(preset: str, args: argparse.Namespace) -> str:
    stem = f"{preset}_{slugify(args.subject or args.text or preset)}"
    candidate = Path(f"{stem}.png")
    index = 2
    while candidate.exists():  # 不覆盖已有文件
        candidate = Path(f"{stem}-v{index}.png")
        index += 1
    return str(candidate)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="学姐用的生图：中文预设通道，一句话出一张图。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("preset", nargs="?", help="预设名（头像/壁纸/朋友圈/封面/贺卡/贴纸/表情包/海报）")
    parser.add_argument("--list", action="store_true", help="列出全部预设后退出")
    parser.add_argument("--subject", help="画面主体，如“戴圆框眼镜的橘猫”")
    parser.add_argument("--text", help="画面主文案（原样写进图里）")
    parser.add_argument("--subtext", help="第二行文字")
    parser.add_argument("--info", help="底部信息（时间地点等）")
    parser.add_argument("--style", help="覆盖默认风格描述")
    parser.add_argument("--extra-note", help="临时补充要求（这一张图专用）")
    parser.add_argument("--orient", choices=["portrait", "landscape"], help="改方向（壁纸/封面/海报适用）")
    parser.add_argument("--tier", choices=["1k", "2k", "4k"], help="覆盖分辨率档")
    parser.add_argument("--aspect", help="覆盖比例，如 1:1 / 3:4 / 16:9")
    parser.add_argument("--size", help="直接给定 WxH（最高优先级）")
    parser.add_argument("--out", help="输出文件；默认按 预设_主题.png 命名，已存在则自动加 -v2")
    parser.add_argument("--model", help="覆盖模型（默认 gpt-image-2）")
    parser.add_argument("--quality", help="覆盖质量（默认 high）")
    parser.add_argument("--prompt", help="跳过预设拼装，直接使用这段提示词")
    parser.add_argument("--print-prompt", action="store_true", help="只打印最终提示词，不生成")
    parser.add_argument("--dry-run", action="store_true", help="走完整流程但只校验请求，不真的生成")
    parser.add_argument("--open", action="store_true", help="生成完成后用系统看图器打开")
    parser.add_argument("--base-url")
    parser.add_argument("--proxy")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--retries", type=int)
    parser.add_argument("--extra", action="append", help="透传给接口的额外参数 key=value")

    args = parser.parse_args()

    if args.list or not args.preset:
        print_list()
        return 0

    preset = resolve_preset(args.preset)

    if not args.prompt and not args.subject and not args.text:
        die("至少给一个 --subject（画面主体）或 --text（画面文案）。")

    prompt = args.prompt or build_prompt(preset, args)
    meta = PRESETS[preset]

    if args.print_prompt or args.dry_run:
        print("=== 最终提示词 ===\n" + prompt + "\n==================")

    if args.print_prompt:
        return 0

    out = args.out or default_out(preset, args)
    tier = args.tier or meta["tier"]
    aspect = aspect_for(preset, args.orient, args)

    cmd: List[str] = [
        sys.executable, "-X", "utf8", str(GENERATOR), "generate",
        "--prompt", prompt,
        "--tier", str(tier),
        "--aspect", aspect,
        "--out", out,
    ]
    if args.size:
        cmd += ["--size", args.size]
    if meta.get("transparent"):
        cmd.append("--transparent")
    if args.model:
        cmd += ["--model", args.model]
    if args.quality:
        cmd += ["--quality", args.quality]
    if args.base_url:
        cmd += ["--base-url", args.base_url]
    if args.proxy:
        cmd += ["--proxy", args.proxy]
    if args.no_proxy:
        cmd.append("--no-proxy")
    if args.no_stream:
        cmd.append("--no-stream")
    if args.timeout:
        cmd += ["--timeout", str(args.timeout)]
    if args.retries:
        cmd += ["--retries", str(args.retries)]
    for extra in args.extra or []:
        cmd += ["--extra", extra]
    if args.dry_run:
        cmd.append("--dry-run")

    print(f"[预设] {preset} · {meta['use']} · {tier} {aspect} · 输出 {out}")
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(cmd, env=env)

    if result.returncode == 0 and args.open and not args.dry_run and Path(out).exists():
        try:
            os.startfile(out)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - 仅影响便利性
            print(f"[提醒] 自动打开失败：{exc}", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
