"""Exercise crop/favorite orchestration without an image service or a browser."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"scripts/static/ppt-workbench/image-tools.js"

class CropFavoriteUiTests(unittest.TestCase):
    def run_helper(self, server_favorite=False, fail=False):
        code=SOURCE.read_text(encoding="utf-8")
        start=code.index("async function saveCropAndFavorite(")
        end=code.index("\nasync function showRecipe(",start)
        fn=code[start:end]
        harness="""
const calls=[];
async function api(url,payload){
 calls.push([url,payload]);
 if(url.endsWith('/crop')) return {id:'a-cropped',favorite:SERVER_FAVORITE};
 if(FAIL_FAVORITE) throw new Error('network unavailable');
 return {favorite:true};
}
""".replace("SERVER_FAVORITE",str(server_favorite).lower()).replace("FAIL_FAVORITE",str(fail).lower())
        result=subprocess.run([shutil.which("node") or "node","-e",harness+fn+"""
(async()=>{try{const result=await saveCropAndFavorite({title:'title'});console.log(JSON.stringify({calls,result}))}
catch(e){console.log(JSON.stringify({calls,error:e.message}))}})();
"""],capture_output=True,text=True,encoding="utf-8",check=True)
        return json.loads(result.stdout)

    def test_legacy_backend_is_favorited_before_success(self):
        result=self.run_helper()
        self.assertTrue(result["result"]["favorite"])
        self.assertEqual([x[0] for x in result["calls"]],["/api/v3/assets/crop","/api/v3/assets/favorite"])
        self.assertEqual(result["calls"][1][1],{"id":"a-cropped","enabled":True})

    def test_current_backend_does_not_repeat_favorite(self):
        result=self.run_helper(server_favorite=True)
        self.assertEqual(len(result["calls"]),1)

    def test_partial_failure_does_not_claim_favorited_or_resave_crop(self):
        result=self.run_helper(fail=True)
        self.assertIn("素材已保存",result["error"])
        self.assertIn("自动收藏失败",result["error"])
        self.assertEqual(len(result["calls"]),2)

if __name__=="__main__":unittest.main()
