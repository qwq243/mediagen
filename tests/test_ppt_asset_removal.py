"""Reversible catalogue removal; source images and pinned projects stay intact."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_ppt_v3 as fixtures
import ppt_assets as assets
import ppt_coding as coding
import ppt_workflow as wf


class AssetRemovalTests(unittest.TestCase):
    setUp, tearDown = fixtures.V3Tests.setUp, fixtures.V3Tests.tearDown
    manifest, scan, client, post = (
        fixtures.V3Tests.manifest, fixtures.V3Tests.scan,
        fixtures.V3Tests.client, fixtures.V3Tests.post)

    def test_remove_restore_preserves_bytes_versions_tags_and_favorites(self):
        r = self.scan()
        source_hash = wf.file_sha(self.image)
        assets.favorite(r["id"], True, self.library)
        before = assets.get(r["id"], r["version"], self.library)
        assets.set_archived(r["id"], True, r["version"], self.library)
        self.assertEqual(assets.search(library=self.library)["total"], 0)
        self.assertEqual(assets.search(filters={"favorite": True}, library=self.library)["total"], 0)
        removed = assets.search(filters={"archived": True}, library=self.library)["items"]
        self.assertEqual(len(removed), 1)
        self.assertTrue(removed[0]["archived"])
        self.assertTrue(removed[0]["archived_at"])
        self.assertEqual(assets.get(r["id"], r["version"], self.library), before)
        self.assertEqual(wf.file_sha(self.image), source_hash)
        assets.set_archived(r["id"], False, r["version"], self.library)
        restored = assets.search(filters={"favorite": True}, library=self.library)["items"][0]
        self.assertEqual(restored["version"], r["version"])
        self.assertEqual(restored["tags"], r["tags"])
        self.assertFalse(assets.search(filters={"archived": True}, library=self.library)["items"])

    def test_refresh_does_not_resurrect_removed_asset_or_erase_new_version(self):
        r = self.scan()
        assets.set_archived(r["id"], True, r["version"], self.library)
        self.rows[0]["summary"] = "重新整理后的标题"
        self.manifest()
        assets.scan(self.source, self.library)
        self.assertEqual(assets.search(library=self.library)["total"], 0)
        current = assets.search(filters={"archived": True}, library=self.library)["items"][0]
        self.assertNotEqual(current["version"], r["version"])
        with self.assertRaisesRegex(ValueError, "版本"):
            assets.set_archived(r["id"], False, r["version"], self.library)
        assets.set_archived(r["id"], False, current["version"], self.library)
        self.assertEqual(assets.search(library=self.library)["items"][0]["title"], "重新整理后的标题")
        self.assertEqual(assets.get(r["id"], r["version"], self.library)["title"], r["title"])

    def test_pinned_cart_survives_removal_but_new_selection_is_blocked(self):
        r = self.scan()
        entry = assets.choose(self.root, self.p, r["id"], r["version"], library=self.library)
        project_before = copy.deepcopy(wf.load(self.root))
        assets.set_archived(r["id"], True, r["version"], self.library)
        self.assertEqual(wf.load(self.root), project_before)
        self.assertEqual(wf.file_sha(Path(entry["path"])), r["sha256"])
        with self.assertRaisesRegex(ValueError, "已移除"):
            assets.choose(self.root, self.p, r["id"], r["version"], library=self.library)
        self.assertEqual(wf.load(self.root), project_before)

    def test_removed_not_in_coding_examples_and_reference_presentation(self):
        r = self.scan()
        self.p["asset_recommendations"] = [{"id": r["id"], "title": r["title"]}]
        wf.save(self.root, self.p)
        self.client()
        assets.set_archived(r["id"], True, r["version"], self.library)
        examples = coding.examples(self.library, "layout", "LY-SPLIT-2")
        self.assertEqual(examples["items"][0]["matches"], 0)
        state = self.web.get("/api/v3/workbench").get_json()
        self.assertEqual(state["recommendations"], [])
        deck = self.web.get("/api/v3/presentation?deck_code=" + r["deck_code"]).get_json()
        self.assertEqual(deck["pages"], [])

    def test_http_confirmation_guards_restore_and_no_project_mutation(self):
        r = self.scan()
        self.client()
        before = wf.load(self.root)
        url = "/api/v3/assets/visibility"
        body = {"id": r["id"], "archived": True, "version": r["version"]}
        self.assertGreaterEqual(self.web.post(url, json={"revision": before["revision"], **body}).status_code, 400)
        self.assertGreaterEqual(self.post(url, {**body, "version": "stale"}).status_code, 400)
        self.assertGreaterEqual(self.post(url, {**body, "archived": "false"}).status_code, 400)
        self.assertEqual(self.web.get("/api/v3/assets").get_json()["total"], 1)
        res = self.post(url, body)
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertTrue(res.get_json()["archived"])
        self.assertFalse(res.get_json()["inference_performed"])
        self.assertEqual(self.web.get("/api/v3/assets?archived=1").get_json()["total"], 1)
        self.assertTrue(self.web.get("/api/v3/assets/" + r["id"]).get_json()["archived"])
        self.assertEqual(self.post(url, {**body, "archived": False}).status_code, 200)
        self.assertEqual(wf.load(self.root), before)


if __name__ == "__main__":
    unittest.main()
