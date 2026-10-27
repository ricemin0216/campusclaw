"""Course MCP demo server with two deterministic learning tools."""

from __future__ import annotations

import hmac
import os
import re
from typing import Any

from flask import Flask, jsonify, request


TOOLS = [
    {
        "name": "formula_hint",
        "description": "根据学生的数学问题给出下一步公式或列式提示，不直接代替学生完成整题。",
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "学生提出的数学问题"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unit_convert",
        "description": "识别常见长度单位换算问题，并返回换算过程或下一步提示。",
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "包含数值和单位的换算问题"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
]


def _formula_hint(question: str) -> str:
    if "方程" in question or "=" in question:
        return "先把含未知数的项放在等号一边、常数项放在另一边；移动一项时要改变它的符号。"
    if "面积" in question:
        return "先确认图形类型和已知边长，再写出对应面积公式并统一长度单位。"
    if "比例" in question:
        return "先找出两组对应量，写成相等的两个比，再检查内项积是否等于外项积。"
    return "先列出已知量、未知量和它们之间的数量关系，再选择对应公式；暂时不要直接计算最终结果。"


def _unit_convert(question: str) -> str:
    factors = {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0, "毫米": 0.001, "厘米": 0.01, "米": 1.0, "千米": 1000.0}
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(mm|cm|km|m|毫米|厘米|千米|米).*?(mm|cm|km|m|毫米|厘米|千米|米)", question, re.I)
    if match is None:
        return "请先明确数值、原单位和目标单位；长度换算可以先统一换算成米，再换算为目标单位。"
    value, source, target = float(match.group(1)), match.group(2).lower(), match.group(3).lower()
    converted = value * factors[source] / factors[target]
    return f"{value:g} {source} = {converted:g} {target}。换算时先乘原单位对应的米制系数，再除以目标单位系数。"


TOOL_HANDLERS = {"formula_hint": _formula_hint, "unit_convert": _unit_convert}


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MCP_AUTH_TOKEN"] = (config or {}).get("MCP_AUTH_TOKEN") or os.environ.get("MCP_AUTH_TOKEN")
    if not app.config["MCP_AUTH_TOKEN"]:
        raise RuntimeError("MCP_AUTH_TOKEN must be set")

    def rpc_error(request_id: Any, code: int, message: str, status: int = 200):
        return jsonify(jsonrpc="2.0", id=request_id, error={"code": code, "message": message}), status

    @app.get("/health")
    def health():
        return jsonify(status="healthy")

    @app.post("/mcp")
    def mcp():
        expected = f"Bearer {app.config['MCP_AUTH_TOKEN']}"
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, expected):
            return jsonify(error="authentication_required"), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return rpc_error(None, -32600, "Invalid Request: JSON object required")
        request_id = payload.get("id")
        if payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str):
            return rpc_error(request_id, -32600, "Invalid Request: jsonrpc 2.0 and method are required")
        params = payload.get("params", {})
        if not isinstance(params, dict):
            return rpc_error(request_id, -32602, "Invalid params: object required")
        method = payload["method"]
        if method == "initialize":
            return jsonify(
                jsonrpc="2.0",
                id=request_id,
                result={
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "campus-tools", "version": "1.0.0"},
                },
            )
        if method == "tools/list":
            return jsonify(jsonrpc="2.0", id=request_id, result={"tools": TOOLS})
        if method == "tools/call":
            name, arguments = params.get("name"), params.get("arguments")
            if name not in TOOL_HANDLERS or not isinstance(arguments, dict):
                return rpc_error(request_id, -32602, "Invalid params: unknown tool or arguments object missing")
            question = arguments.get("question")
            if not isinstance(question, str) or not question.strip() or len(question) > 500:
                return rpc_error(request_id, -32602, "Invalid params: question must contain 1 to 500 characters")
            text = TOOL_HANDLERS[name](question.strip())
            return jsonify(jsonrpc="2.0", id=request_id, result={"content": [{"type": "text", "text": text}], "isError": False})
        return rpc_error(request_id, -32601, f"Method not found: {method}")

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8090)
