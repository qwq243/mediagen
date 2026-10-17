# Moved

This file is a compatibility stub.

PPT image generation now lives in [`ppt-image-workflow.md`](ppt-image-workflow.md).

- Default unnamed PPT pages: `--profile lecture`
- High-density briefing / defense pages: `--profile dense`
- Main image plus later background/atom reconstruction: `--profile reconstruction`

```powershell
python C:/Users/USER/.codex/skills/mediagen/scripts/init_ppt_image_job.py `
  --out-dir work/my-project/ppt-image-job `
  --project-name "topic" `
  --profile dense
```

`scripts/init_competition_ppt_job.py` still runs and forces `--profile dense`.
