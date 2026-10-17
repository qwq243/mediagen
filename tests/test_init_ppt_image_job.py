#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "scripts" / "init_ppt_image_job.py"
WRAPPER = ROOT / "scripts" / "init_competition_ppt_job.py"


class InitPptImageJobTests(unittest.TestCase):
    def _run(self, script: Path, extra: list[str]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "job"
            result = subprocess.run(
                [sys.executable, str(script), "--out-dir", str(out), *extra],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            pack = json.loads((out / "prompt-pack.json").read_text(encoding="utf-8"))
            jsonl = (out / "prompts" / "main-prompts.jsonl").read_text(encoding="utf-8")
            style = (out / "01-style-extraction-note.md").read_text(encoding="utf-8")
            research = (out / "02-research-brief.md").read_text(encoding="utf-8")
            provenance = json.loads((out / "02-fact-provenance.json").read_text(encoding="utf-8"))
            outline = (out / "03-outline.md").read_text(encoding="utf-8")
            qa = (out / "qa-checklist.md").read_text(encoding="utf-8")
            return {
                "payload": payload,
                "pack": pack,
                "jsonl": jsonl,
                "style": style,
                "research": research,
                "provenance": provenance,
                "outline": outline,
                "qa": qa,
                "out": out,
            }

    def test_lecture_is_default_and_generic(self) -> None:
        data = self._run(INIT, ["--project-name", "demo"])
        pack = data["pack"]
        self.assertEqual(pack["profile"], "lecture")
        self.assertEqual(pack["route"], "mediagen ppt_image_workflow")
        self.assertIn("3-5", data["jsonl"])
        self.assertNotIn("competition defense", data["jsonl"])
        self.assertNotIn("知愈", json.dumps(pack, ensure_ascii=False))
        self.assertNotIn("红旅", data["style"])
        self.assertIn("生图执行提示", data["style"])
        self.assertIn("字体与中文排印", data["style"])
        self.assertIn("Research Brief", data["research"])
        self.assertEqual(data["provenance"]["schema"], "mediagen.fact-provenance.v1")
        self.assertIn("Outline", data["outline"])
        self.assertIn("P01 generated and accepted", data["qa"])
        self.assertEqual(pack["pages"][0]["asset_prompts"], [])

    def test_reconstruction_keeps_dormant_assets(self) -> None:
        data = self._run(INIT, ["--profile", "reconstruction"])
        assets = data["pack"]["pages"][0]["asset_prompts"]
        self.assertEqual(len(assets), 2)
        self.assertTrue(all(item["status"] == "dormant_until_main_comp_approved" for item in assets))

    def test_legacy_wrapper_defaults_to_dense(self) -> None:
        data = self._run(WRAPPER, ["--project-name", "legacy"])
        self.assertEqual(data["pack"]["profile"], "dense")
        self.assertIn("high-density", data["jsonl"])


if __name__ == "__main__":
    unittest.main()
