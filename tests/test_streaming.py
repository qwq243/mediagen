import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "newapi_image.py"
SPEC = importlib.util.spec_from_file_location("newapi_image", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class NewApiImageStreamingTests(unittest.TestCase):
    def test_base_url_normalizes_to_single_v1(self):
        self.assertEqual(MODULE.normalize_base_url("https://api.toapi.xyz"), "https://api.toapi.xyz/v1")
        self.assertEqual(MODULE.normalize_base_url("https://api.toapi.xyz/v1"), "https://api.toapi.xyz/v1")

    def test_sse_uses_last_event_with_image_data(self):
        raw = "\n".join(
            [
                'data: {"type":"image_generation.partial","data":[{"url":"https://images.example/partial.png"}]}',
                'data: {"type":"image_generation.completed","data":[{"url":"https://images.example/final.png"}]}',
                "data: [DONE]",
            ]
        )
        parsed = MODULE.parse_api_response(raw, "https://api.toapi.xyz/v1/images/generations", expect_stream=True)
        self.assertEqual(parsed["data"][0]["url"], "https://images.example/final.png")
        self.assertEqual(parsed["stream_events"], 2)

    def test_stream_flag_accepts_normal_json_response(self):
        raw = '{"data":[{"url":"https://images.example/final.png"}]}'
        parsed = MODULE.parse_api_response(raw, "https://api.toapi.xyz/v1/images/generations", expect_stream=True)
        self.assertEqual(parsed["data"][0]["url"], "https://images.example/final.png")

    def test_sse_prefers_final_over_late_partial_frame(self):
        raw = "\n".join(
            [
                'event: image_generation.completed',
                'data: {"type":"image_generation.completed","data":[{"url":"https://images.example/final.png"}]}',
                "",
                "event: image_generation.partial_image",
                'data: {"type":"image_generation.partial_image","partial_image_index":0,"data":[{"url":"https://images.example/partial.png"}]}',
            ]
        )
        parsed = MODULE.parse_api_response(raw, "https://api.toapi.xyz/v1/images/generations", expect_stream=True)
        self.assertEqual(parsed["data"][0]["url"], "https://images.example/final.png")

    def test_image_arguments_default_to_streaming(self):
        parser = MODULE.build_parser()
        args = parser.parse_args(["generate", "--prompt", "test image"])
        self.assertTrue(args.stream)

    def test_size_presets_and_partial_images_are_in_payload(self):
        parser = MODULE.build_parser()
        args = parser.parse_args(
            ["generate", "--prompt", "test", "--tier", "2k", "--aspect", "16:9", "--partial-images", "2"]
        )
        payload = MODULE.build_payload(args, "test")
        self.assertEqual(MODULE.resolve_size(None, "2k", "16:9"), "2560x1440")
        self.assertEqual(payload["size"], "2560x1440")
        self.assertEqual(payload["partial_images"], 2)

    def test_edit_parser_and_multipart_body(self):
        parser = MODULE.build_parser()
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "source.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nsource")
            args = parser.parse_args(
                ["edit", "--prompt", "replace background", "--image", str(image), "--no-stream"]
            )
            body, content_type = MODULE.build_multipart_payload(args, "edit", args.prompt)
            self.assertIn(b'name="prompt"', body)
            self.assertIn(b'name="image"; filename="source.png"', body)
            self.assertIn(b"replace background", body)
            self.assertTrue(content_type.startswith("multipart/form-data; boundary="))

    def test_batch_nested_output_path_stays_nested_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "images"
            nested = MODULE.safe_batch_output(root, "pages/hero.png")
            self.assertEqual(nested, root.resolve() / "pages" / "hero.png")
            with self.assertRaises(SystemExit):
                MODULE.safe_batch_output(root, "../outside.png")

    def test_auto_transport_prefers_curl_on_windows(self):
        transport = MODULE.select_transport(
            "auto",
            platform_name="nt",
            curl_path="C:/Windows/System32/curl.exe",
        )
        self.assertEqual(transport, "curl")

    def test_auto_transport_falls_back_to_urllib_without_curl(self):
        transport = MODULE.select_transport("auto", platform_name="nt", curl_path=None)
        self.assertEqual(transport, "urllib")

    def test_curl_command_does_not_contain_api_key(self):
        command, config = MODULE.build_curl_request(
            "POST",
            "https://toapi.xyz/v1/images/generations",
            "sk-test-secret",
            {"model": "gpt-image-2", "prompt": "test", "stream": False},
            timeout=300,
            stream=False,
            curl_path=shutil.which("curl") or "curl.exe",
        )
        self.assertNotIn("sk-test-secret", " ".join(command))
        self.assertIn("Authorization: Bearer sk-test-secret", config)
        self.assertIn("Accept: application/json", config)

    def test_parse_curl_response_extracts_http_status_and_json(self):
        raw = '{"data":[{"url":"https://images.example/final.png"}]}\n__NEWAPI_HTTP_CODE__:200'
        parsed = MODULE.parse_curl_response(
            raw,
            "https://toapi.xyz/v1/images/generations",
            expect_stream=False,
        )
        self.assertEqual(parsed["data"][0]["url"], "https://images.example/final.png")


if __name__ == "__main__":
    unittest.main()


class ProxyFallbackTests(unittest.TestCase):
    def test_build_proxy_routes_explicit_proxy_only(self):
        routes = MODULE.build_proxy_routes("http://127.0.0.1:12002", False, False, None, None, "https://x/v1/models")
        self.assertEqual(routes, ("http://127.0.0.1:12002",))

    def test_build_proxy_routes_no_proxy_is_direct_only(self):
        routes = MODULE.build_proxy_routes(None, True, False, "http://127.0.0.1:12002", None, "https://x/v1/models")
        self.assertEqual(routes, (None,))

    def test_build_proxy_routes_direct_first_unless_prefer_proxy(self):
        routes = MODULE.build_proxy_routes(None, False, False, "http://p:1", None, "https://unreachable.invalid/v1/models")
        self.assertEqual(routes[0], None)
        self.assertIn("http://p:1", routes)
        prefered = MODULE.build_proxy_routes(None, False, True, "http://p:1", None, "https://unreachable.invalid/v1/models")
        self.assertEqual(prefered[-1], None)
        self.assertEqual(prefered[0], "http://p:1")

    def test_health_url_for_derives_models_endpoint(self):
        self.assertEqual(
            MODULE.health_url_for("https://api.toapi.xyz/v1/images/generations"),
            "https://api.toapi.xyz/v1/models",
        )

    def test_curl_request_includes_proxy_in_config_not_argv(self):
        command, config = MODULE.build_curl_request(
            "POST",
            "https://toapi.xyz/v1/images/generations",
            "sk-test-secret",
            {"model": "gpt-image-2", "prompt": "x"},
            curl_path="curl.exe",
            proxy="http://127.0.0.1:12002",
        )
        self.assertNotIn("12002", " ".join(command))
        self.assertIn('proxy = "http://127.0.0.1:12002"', config)

    def test_ratio_alias_maps_to_nearest_native_size(self):
        parser = MODULE.build_parser()
        args = parser.parse_args(["generate", "--prompt", "test", "--ratio", "16:9"])
        payload = MODULE.build_payload(args, "test")
        self.assertEqual(payload["size"], "1536x1024")

    def test_ratio_alias_square_keyword(self):
        parser = MODULE.build_parser()
        args = parser.parse_args(["generate", "--prompt", "test", "--ratio", "square"])
        payload = MODULE.build_payload(args, "test")
        self.assertEqual(payload["size"], "1024x1024")

    def test_explicit_size_wins_over_ratio(self):
        parser = MODULE.build_parser()
        args = parser.parse_args(["generate", "--prompt", "test", "--ratio", "9:16", "--size", "1024x1024"])
        payload = MODULE.build_payload(args, "test")
        self.assertEqual(payload["size"], "1024x1024")

    def test_transport_failure_is_raised_not_fatal_in_urllib_request(self):
        # request_json surfaces TransportFailed after retries so the caller can
        # switch routes; HTTP errors still die immediately.
        with self.assertRaises(MODULE.TransportFailed):
            MODULE.request_json(
                "GET",
                "https://mediagen-invalid.invalid/v1/models",
                "sk-test",
                retries=1,
                timeout=2,
            )
