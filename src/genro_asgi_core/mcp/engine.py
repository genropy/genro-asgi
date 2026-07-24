# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""McpEngine — MCP (JSON-RPC 2.0) core over a genro-routes Router.

The engine turns a Router's ``@route`` entries into MCP tools and serves the
protocol methods ``initialize`` / ``tools/list`` / ``tools/call``. It is
transport- and app-agnostic: it holds a Router and a channel to filter on and
never touches HTTP concerns (headers, Origin, 202-for-notifications belong to
the host application). ``dispatch`` receives the parsed JSON-RPC message and
returns the RESULT object — envelope bookkeeping (``id``, ``jsonrpc``) stays
with the transport; protocol failures raise :class:`McpError` carrying the
JSON-RPC code for the transport to render. A list payload is rejected with
-32600: JSON-RPC batching entered the MCP spec in 2025-03-26 and was removed
in 2025-06-18.

Protocol (2025-11-25, the current revision):

- ``initialize`` negotiates the version: the client's requested version is
  echoed when it appears in ``SUPPORTED_VERSIONS``, anything else is answered
  with the latest supported revision.
- ``tools/list`` walks ``router.nodes(forbidden=False, channel_channel=...)``
  so only the entries reachable on the engine's channel are advertised. Tool
  names join the router path with ``tool_separator`` (default ``"."``, a
  character illegal in Python identifiers, so ``sub.ping`` <-> ``sub/ping``
  round-trips losslessly). Descriptors read ONLY the neutral blocks cached by
  genro-routes' pydantic plugin at decoration time: ``inputSchema`` from the
  entry's ``params.schema`` (aggregate ``request_schema``; fallback: an object
  schema assembled from ``params.fields``), ``outputSchema`` from
  ``result.schema`` (``response_schema``). Nothing is derived from the
  callable and pydantic is never imported here.
- ``tools/call`` resolves the tool through ``router.node(path, ...)`` and
  reads the ``node.error`` STRING CODE (the stable genro-routes contract —
  resolution never raises): ``not_found``/``not_available`` -> -32601,
  ``not_authorized``/``not_authenticated`` -> -32000, any other code ->
  -32603. Execution is delegated to the ``invoke`` callback so a host app can
  interpose parameter adaptation and pool dispatch; the default calls the
  node directly and the engine awaits an awaitable result (async handlers),
  nothing more. Input-validation failures are TOOL EXECUTION errors —
  ``{"isError": true, "content": [...]}`` results, not JSON-RPC protocol
  errors (SEP-1303, enables model self-correction). Validation runs INSIDE
  genro-routes (the pydantic plugin validates at call time; the engine never
  re-validates). Since genro-routes 0.28.0 every bad-argument error — a
  ``pydantic.ValidationError`` or an unbindable-argument ``TypeError`` alike —
  is channelled through the node's ``errors={"validation_error": ...}`` seam
  to a local marker, so this module needs no pydantic import; the bare
  ``TypeError`` catch remains for an async handler body raising at await time
  (a sync body's TypeError is already folded into the marker upstream). Both
  become ``isError`` results. ``ping`` answers an empty result (spec MUST).
  A dict result is returned BOTH as ``structuredContent`` and as its JSON
  text rendering (the unstructured content SHOULD match the declared
  ``outputSchema``); any other result stays text-only.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from genro_routes import Router, RouterNode

__all__ = [
    "JSONRPC_INTERNAL_ERROR",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_NOT_AUTHORIZED",
    "McpEngine",
    "McpError",
]

JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_NOT_AUTHORIZED = -32000


class McpError(Exception):
    """Carries a JSON-RPC error code + message for the transport to render."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _ToolArgumentsInvalid(Exception):
    """Marker raised by the node's ``validation_error`` exception mapping.

    genro-routes re-raises an escaping ``pydantic.ValidationError`` as the
    class mapped to the ``validation_error`` code, with the original error as
    ``__cause__`` — the engine catches bad tool arguments through this class
    without importing pydantic.
    """


class McpEngine:
    """MCP JSON-RPC core over a router.

    Args:
        router: The genro-routes Router whose entries are exposed as tools.
        name / version: server identity returned by ``initialize``.
        tool_separator: joins router/method segments into a flat tool name.
        channel: channel to filter entries on (visibility per channel).
        invoke: callback ``(node, arguments) -> result`` running a resolved
            node; the engine awaits an awaitable result. Host applications
            pass their own to interpose parameter adaptation (e.g.
            ``spread_over_params``) and pool dispatch for sync handlers; the
            default calls the node directly.
    """

    SUPPORTED_VERSIONS: tuple[str, ...] = ("2025-11-25", "2025-06-18", "2025-03-26")

    def __init__(
        self,
        router: Router | None = None,
        *,
        name: str = "genro-mcp",
        version: str = "1.0.0",
        tool_separator: str = ".",
        channel: str = "mcp",
        invoke: Callable[[Any, dict], Any] | None = None,
    ) -> None:
        self.router = router
        self.name = name
        self.version = version
        self.tool_separator = tool_separator
        self.channel = channel
        self._invoke = invoke or self._default_invoke

    def _default_invoke(self, node: RouterNode, arguments: dict) -> Any:
        """Raw invocation, no parameter adaptation; ``dispatch`` awaits it."""
        return node(**arguments)

    async def dispatch(self, payload: Any, auth_tags: Any = None) -> dict:
        """Route a parsed JSON-RPC message to its MCP handler.

        Returns the JSON-RPC RESULT object; the transport owns the envelope.

        Raises:
            McpError: invalid message shape (-32600, batching included) or
                unknown method (-32601); ``tools/call`` resolution failures
                bubble up from :meth:`handle_tools_call`.
        """
        if isinstance(payload, list):
            raise McpError(JSONRPC_INVALID_REQUEST, "JSON-RPC batching is not supported")
        if not isinstance(payload, dict):
            raise McpError(JSONRPC_INVALID_REQUEST, "Invalid JSON-RPC message")
        method = payload.get("method")
        if not isinstance(method, str):
            raise McpError(JSONRPC_INVALID_REQUEST, "Missing method")
        params = payload.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise McpError(JSONRPC_INVALID_REQUEST, "params must be an object")
        if method == "ping":
            return {}
        if method == "initialize":
            return self.handle_initialize(params)
        if method == "tools/list":
            return self.handle_tools_list()
        if method == "tools/call":
            return await self.handle_tools_call(params, auth_tags)
        raise McpError(JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")

    def handle_initialize(self, params: dict) -> dict:
        """Negotiate the protocol version and return the server capabilities.

        The client's requested version is echoed when supported; any other
        request is answered with the latest supported revision (spec
        negotiation rule).
        """
        requested = params.get("protocolVersion")
        version = requested if requested in self.SUPPORTED_VERSIONS else self.SUPPORTED_VERSIONS[0]
        return {
            "protocolVersion": version,
            # experimental.push: the host transport's SSE progress channel
            # (GET + Mcp-Session-Id); the engine itself stays transport-blind.
            "capabilities": {"tools": {}, "experimental": {"push": {}}},
            "serverInfo": {"name": self.name, "version": self.version},
        }

    def handle_tools_list(self) -> dict:
        """Enumerate the tools visible on this channel.

        ``forbidden=False`` excludes entries the channel does not expose, so
        the tool list carries only what is reachable on this channel.
        """
        if self.router is None:
            return {"tools": []}
        nodes = self.router.nodes(forbidden=False, channel_channel=self.channel)
        tools: list[dict] = []
        self._collect_tools(nodes, "", tools)
        return {"tools": tools}

    def _collect_tools(self, nodes: dict, prefix: str, tools: list) -> None:
        """Recursively collect tool descriptors from router nodes."""
        sep = self.tool_separator
        for name, info in nodes.get("entries", {}).items():
            tool_name = name if not prefix else f"{prefix}{sep}{name}"
            tools.append(self._build_tool_descriptor(tool_name, info))
        for router_name, sub_nodes in nodes.get("routers", {}).items():
            sub_prefix = router_name if not prefix else f"{prefix}{sep}{router_name}"
            self._collect_tools(sub_nodes, sub_prefix, tools)

    def _build_tool_descriptor(self, tool_name: str, info: dict) -> dict:
        """Build an MCP tool descriptor from a nodes() entry info.

        Reads only the neutral blocks: ``inputSchema`` from the ``params``
        block, ``outputSchema`` from the ``result`` block (present when the
        pydantic plugin captured a return-type schema).
        """
        metadata = info.get("metadata") or {}
        description = metadata.get("meta", {}).get("description") or info.get("doc") or tool_name
        descriptor: dict = {
            "name": tool_name,
            "description": description,
            "inputSchema": self._input_schema(info),
        }
        output_schema = (info.get("result") or {}).get("schema")
        if output_schema is not None:
            descriptor["outputSchema"] = output_schema
        return descriptor

    def _input_schema(self, info: dict) -> dict:
        """Tool inputSchema from the neutral ``params`` block, never the callable.

        Primary source: the aggregate ``request_schema`` the pydantic plugin
        cached (copied before the ``type`` default so the cache is never
        mutated). Fallback: an object schema assembled from the cached
        per-parameter ``fields`` (untyped and var-parameters carry no schema
        and are skipped). No captured params -> empty object schema.
        """
        params_block = info.get("params") or {}
        schema = params_block.get("schema")
        if schema is not None:
            schema = dict(schema)
            schema.setdefault("type", "object")
            return schema
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in params_block.get("fields") or []:
            field_schema = field.get("schema")
            if field_schema is None:
                continue
            properties[field["name"]] = field_schema
            if field.get("required"):
                required.append(field["name"])
        assembled: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            assembled["required"] = required
        return assembled

    async def handle_tools_call(self, params: dict, auth_tags: Any = None) -> dict:
        """Resolve a tool name to its router node, invoke it, wrap the result.

        Bad tool arguments come back as ``isError`` results — genro-routes
        0.28.0 folds validation failures AND unbindable arguments into the
        ``validation_error`` mapping, while the ``TypeError`` catch covers an
        async handler body raising at await time; resolution failures read
        ``node.error`` and raise :class:`McpError`.

        Raises:
            McpError: no router configured (-32603), unknown/unavailable tool
                (-32601), not authorized/authenticated (-32000), any other
                resolution code (-32603).
        """
        if self.router is None:
            raise McpError(JSONRPC_INTERNAL_ERROR, "No router configured")
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        # Reverse of _collect_tools: separator between segments -> path separator.
        path = name.replace(self.tool_separator, "/")
        node = self.router.node(
            path,
            errors={"validation_error": _ToolArgumentsInvalid},
            auth_tags=",".join(auth_tags) if isinstance(auth_tags, list) else auth_tags,
            channel_channel=self.channel,
        )
        if node.error in ("not_found", "not_available"):
            raise McpError(JSONRPC_METHOD_NOT_FOUND, f"Tool not found: {name}")
        if node.error in ("not_authorized", "not_authenticated"):
            raise McpError(JSONRPC_NOT_AUTHORIZED, "Not authorized")
        if node.error:
            raise McpError(JSONRPC_INTERNAL_ERROR, f"Router error: {node.error}")
        try:
            result = self._invoke(node, arguments)
            if inspect.isawaitable(result):
                result = await result
        except (_ToolArgumentsInvalid, TypeError) as exc:
            detail = exc.__cause__ or exc
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Invalid tool arguments: {detail}"}],
            }
        return self._tool_result(result)

    def _tool_result(self, result: Any) -> dict:
        """Wrap a handler result as a ``tools/call`` result object.

        A dict rides BOTH as ``structuredContent`` and as JSON text content;
        anything else is text-only.
        """
        payload: dict[str, Any] = {
            "content": [{"type": "text", "text": self._serialize_result(result)}]
        }
        if isinstance(result, dict):
            payload["structuredContent"] = result
        return payload

    def _serialize_result(self, result: Any) -> str:
        """Serialize a result to the text content string."""
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)


if __name__ == "__main__":
    import asyncio

    from genro_routes import RoutingClass, route

    class Demo(RoutingClass):
        """Demo service exposing one MCP tool."""

        def __init__(self) -> None:
            self.route.plug("pydantic")
            self.route.plug("channel")

        @route(channel_channels="mcp")
        def add(self, x: int, y: int = 0) -> dict:
            """Add two numbers."""
            return {"sum": x + y}

    engine = McpEngine(Demo().route, name="demo")
    init = asyncio.run(engine.dispatch({"method": "initialize", "params": {}}))
    assert init["protocolVersion"] == "2025-11-25"
    tools = asyncio.run(engine.dispatch({"method": "tools/list"}))
    assert [tool["name"] for tool in tools["tools"]] == ["add"]
    call = asyncio.run(
        engine.dispatch(
            {"method": "tools/call", "params": {"name": "add", "arguments": {"x": 2, "y": 3}}}
        )
    )
    assert call["structuredContent"] == {"sum": 5}
    bad = asyncio.run(
        engine.dispatch(
            {"method": "tools/call", "params": {"name": "add", "arguments": {"x": "nope"}}}
        )
    )
    assert bad["isError"] is True
