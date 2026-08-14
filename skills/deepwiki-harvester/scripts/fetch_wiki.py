#!/usr/bin/env python3
"""Fetch public-repository documentation from DeepWiki's MCP server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib import error, request

DEFAULT_ENDPOINT = "https://mcp.deepwiki.com/mcp"
PROTOCOL_VERSION = "2025-03-26"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_repo(value: str) -> str:
    if not REPO_PATTERN.fullmatch(value):
        raise ValueError("repository must use owner/name format")
    return value


def decode_mcp_body(content_type: str, body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8")
    if "text/event-stream" in content_type:
        messages = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    messages.append(json.loads(data))
        if not messages:
            raise ValueError("MCP server returned no SSE data message")
        return messages[-1]
    if not text.strip():
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("MCP response must be a JSON object")
    return value


def extract_text(result: dict[str, Any]) -> str:
    blocks = result.get("content", [])
    texts = [
        block["text"]
        for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    if not texts:
        raise ValueError("DeepWiki returned no text content")
    return "\n".join(texts)


class MCPClient:
    def __init__(self, endpoint: str, timeout: float) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.session_id: str | None = None
        self.next_id = 1

    def _post(self, payload: dict[str, Any], expect_response: bool = True) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "DeepSkill-fetch-wiki/1.0",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self.session_id = session
                body = response.read()
                if not expect_response or not body:
                    return {}
                return decode_mcp_body(response.headers.get("Content-Type", ""), body)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepWiki HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"DeepWiki connection failed: {exc.reason}") from exc

    def initialize(self) -> None:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "DeepSkill-fetch-wiki", "version": "1.0"},
                },
            }
        )
        self.next_id += 1
        if "error" in response:
            raise RuntimeError(f"MCP initialize failed: {response['error']}")
        if "result" not in response:
            raise RuntimeError("MCP initialize returned no result")
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            expect_response=False,
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        self.next_id += 1
        if "error" in response:
            raise RuntimeError(f"{name} failed: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"{name} returned no result")
        if result.get("isError"):
            raise RuntimeError(f"{name} returned an error: {extract_text(result)}")
        return result


def harvest(repo: str, output_dir: Path, endpoint: str, timeout: float) -> None:
    client = MCPClient(endpoint, timeout)
    client.initialize()
    arguments = {"repoName": repo}
    structure = extract_text(client.call_tool("read_wiki_structure", arguments))
    contents = extract_text(client.call_tool("read_wiki_contents", arguments))

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "structure.md").write_text(structure.rstrip() + "\n", encoding="utf-8")
    (output_dir / "contents.md").write_text(contents.rstrip() + "\n", encoding="utf-8")
    metadata = {
        "repository": repo,
        "endpoint": endpoint,
        "protocol_version": PROTOCOL_VERSION,
        "tools": ["read_wiki_structure", "read_wiki_contents"],
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="public GitHub repository in owner/name form")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="destination (default: deepwiki_corpus/owner__repo)",
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        repo = validate_repo(args.repository)
        output = args.output_dir or Path("deepwiki_corpus") / repo.replace("/", "__")
        harvest(repo, output, args.endpoint, args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"fetch_wiki: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
