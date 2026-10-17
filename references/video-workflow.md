# Video channel (绘影 / workstation sidecar)

Image generation in this skill still goes through NewAPI (`/v1/images/*`). Video does **not**. NewAPI on this machine has no Seedance / video models; the live video path is the workstation sidecar.

Use this channel when the user asks for a generated clip, 图生视频, Seedance, 幻映, or "绘影生视频". Do not invent a `/v1/videos` call against `netcup-1.toapi.xyz`.

## Where it lives

- Panel: `http://127.0.0.1:5278/#/studio/video` (library `#/studio/library`)
- HTTP: `POST /api/studio/generate` with `{kind:"video", prompt, model, size, duration, upstream}`
- MCP (same sidecar): `generate_video` then `get_studio_item` / `get_video_task`
- Helper: `scripts/newapi_video.py` (talks to the sidecar, not NewAPI)

Keys stay in the sidecar `secrets.json` (`fallbackp.apiKey` / `dolaPool.apiKey`). This skill never prints them.

## Upstreams

| id | What | When |
|---|---|---|
| `fallbackp` | 幻映 `fallbackp.top` (paid Seedance) | Default. Key already set. Clip usually 3–13 min. |
| `dolaPool` | Local `工具/dola-pool` on `127.0.0.1:8000` | Free, but the pool is empty until accounts are added. One account ≈ 1–2 clips/day. |

Default model: `seedance_v2.5`. Keep `seedance_v2.0_mini` last — it has failed in a live run. Sizes: `1280x720` / `720x1280` / `1024x1024`. Durations: `10` / `15` / `30`.

Status words from 幻映 include `succeeded`; the sidecar normalizes to OpenAI-style `queued` / `in_progress` / `completed` / `failed`. Artifact URLs from 幻映 need `Authorization`; the sidecar downloads them into `server/data/videogen/` and the library record.

`reference_images` must be public `http(s)` URLs. Localhost / LAN URLs are rejected upstream.

## Prompt structure (Seedance six-step formula)

Follow **主体 → 动作 → 环境 → 镜头 → 风格 → 约束**, roughly one beat each, 60–100 words for a 10s clip. Assemble the prompt before calling `generate`; do not hand the raw user sentence straight through if it is thinner than this.

1. **主体**：谁/什么，带两三个外观细节（毛色、衣着、材质）。
2. **动作**：一个主动作 + 一两个微动作；动作要能在 10 秒里完成。
3. **环境**：场景 + 天气/时段 + 光线（暖光 / 逆光 / 阴天柔光）。
4. **镜头**：一个景别 + **一个**运镜（推/拉/摇/跟/固定）。镜头运动和主体动作分开写，别让"镜头追着跑"这种复合描述混在一起。
5. **风格**：写实 / 电影感 / 动画 / 胶片颗粒……一次一个，别堆。
6. **约束**：画质或负面约束放最后（"画面稳定，无字幕无水印"）。

中文示例：

```
一只橘猫，白色爪子，戴着蓝色项圈，在草地上轻快地奔跑，耳朵随步伐抖动。
午后阳光洒在草地上，背景是模糊的野花和树影。
中景跟拍，镜头平稳地横向跟随。
写实风格，浅景深，色彩明快。
画面稳定，无字幕无水印。
```

Common camera vocabulary: 固定镜头 / 推近 / 拉远 / 左右横摇 / 跟拍 / 升降 / 环绕. Pick one per shot; if the user asks for multiple camera moves, split into multiple clips instead of stacking them into one prompt.

Keep the user's intent (subject, scene, mood) exactly; you are adding camera/style/constraint structure, not rewriting content. If the user supplies a complete structured prompt, use it as-is.

## CLI

Need the sidecar token from `work/workstation/server/config.json` `auth.token` (or `X-WS-Token`). The helper reads it itself; do not paste the token into chat.

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_video.py generate `
  --prompt "一只橘猫在草地上奔跑，阳光明媚" `
  --model seedance_v2.5 `
  --size 1280x720 `
  --duration 10 `
  --upstream fallbackp
```

Poll:

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/newapi_video.py status --id cr_v_...
```

`--dry-run` prints the JSON body and does not spend. `--wait` polls until `done`/`failed` (default 15 min).

If the sidecar is down, say so and stop. Do not fall back to NewAPI image generation for a video request.
