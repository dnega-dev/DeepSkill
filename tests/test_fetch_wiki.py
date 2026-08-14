import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "deepwiki-harvester" / "scripts" / "fetch_wiki.py"
SPEC = importlib.util.spec_from_file_location("fetch_wiki", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FetchWikiTests(unittest.TestCase):
    def test_accepts_owner_repo(self):
        self.assertEqual(MODULE.validate_repo("modelcontextprotocol/servers"), "modelcontextprotocol/servers")

    def test_rejects_urls_and_partial_names(self):
        for value in ("servers", "https://github.com/a/b", "a/b/c", "../a/b"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MODULE.validate_repo(value)

    def test_decodes_json_response(self):
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        self.assertEqual(
            MODULE.decode_mcp_body("application/json", json.dumps(payload).encode()),
            payload,
        )

    def test_decodes_sse_response(self):
        body = b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n'
        self.assertEqual(
            MODULE.decode_mcp_body("text/event-stream", body),
            {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}},
        )

    def test_extracts_text_content(self):
        result = {"content": [{"type": "text", "text": "alpha"}, {"type": "text", "text": "beta"}]}
        self.assertEqual(MODULE.extract_text(result), "alpha\nbeta")


if __name__ == "__main__":
    unittest.main()
