"""Authenticated JSON-RPC client and secret storage helpers for MCP servers."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken


TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SERVER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
TOOL_REFERENCE_PATTERN = re.compile(r"^([a-z][a-z0-9_]{0,63})@([a-z][a-z0-9_-]{0,63})$")


class McpError(RuntimeError):
    """Base error raised for remote MCP failures."""


class McpUnauthorized(McpError):
    """Raised when a remote MCP server rejects its Bearer token."""


class TokenCipher:
    """Encrypt reversible MCP tokens at rest using the application's server secret."""

    def __init__(self, secret: str):
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as error:
            raise McpError("stored MCP token cannot be decrypted") from error


def normalize_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Base URL 必须是字符串")
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(normalized) > 500
    ):
        raise ValueError("Base URL 必须是有效的 HTTP(S) 地址，且不能包含账号、查询参数或片段")
    return normalized


class HttpMcpClient:
    """Small synchronous client for the MCP JSON-RPC HTTP endpoint."""

    def __init__(self, base_url: str, token: str, timeout: float = 6.0):
        self.endpoint = normalize_base_url(base_url) + "/mcp"
        self.token = token
        self.timeout = timeout
        self._request_id = 0

    def _call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        try:
            response = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}},
                timeout=self.timeout,
            )
        except httpx.HTTPError as error:
            raise McpError(f"MCP server is unreachable: {error.__class__.__name__}") from error
        if response.status_code == 401:
            raise McpUnauthorized("MCP server rejected the Bearer token")
        if response.status_code >= 400:
            raise McpError(f"MCP server returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise McpError("MCP server returned invalid JSON") from error
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise McpError("MCP server returned an invalid JSON-RPC response")
        if "error" in payload:
            rpc_error = payload.get("error") or {}
            raise McpError(str(rpc_error.get("message") or "MCP JSON-RPC error"))
        result = payload.get("result")
        if not isinstance(result, dict):
            raise McpError("MCP response result must be an object")
        return result

    def initialize(self) -> dict[str, Any]:
        return self._call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "campusclaw-freebird", "version": "6.0.0"},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self._call("tools/list").get("tools")
        if not isinstance(tools, list):
            raise McpError("tools/list did not return a tools array")
        validated: list[dict[str, Any]] = []
        for item in tools:
            if not isinstance(item, dict) or not TOOL_NAME_PATTERN.fullmatch(str(item.get("name", ""))):
                raise McpError("tools/list returned an invalid tool name")
            schema = item.get("inputSchema", {"type": "object"})
            if not isinstance(schema, dict):
                raise McpError("tools/list returned an invalid input schema")
            validated.append(
                {
                    "name": item["name"],
                    "description": str(item.get("description", ""))[:1000],
                    "inputSchema": schema,
                }
            )
        return validated

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content")
        if not isinstance(content, list):
            raise McpError("tools/call did not return content")
        texts = [str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text"]
        text = "\n".join(part for part in texts if part).strip()
        if not text:
            raise McpError("tools/call returned no text content")
        return text[:4000]
