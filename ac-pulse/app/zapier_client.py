import json
from typing import Any

import structlog
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = structlog.get_logger(__name__)


class ZapierMCPError(Exception):
    """Raised when a Zapier MCP call fails or returns an unparseable result."""


async def execute_snowflake_sql(
    server_url: str,
    token: str,
    statement: str,
    *,
    output_hint: str,
    instructions: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Call Zapier MCP's snowflake_execute_sql tool.

    Returns (parsed_rows, debug_info). debug_info contains the first 500
    chars of the raw response and block counts — surfaced through the
    /lookup endpoint when ?debug=1 is passed so we can see what Zapier
    actually sent back without scraping container logs.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with (
            streamablehttp_client(server_url, headers=headers) as (
                read_stream,
                write_stream,
                _,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(
                "snowflake_execute_sql",
                arguments={
                    "statement": statement,
                    "output_hint": output_hint,
                    "instructions": instructions,
                },
            )
    except BaseException as exc:
        detail = _format_exception_chain(exc)
        logger.exception("zapier_mcp_call_failed", detail=detail)
        raise ZapierMCPError(f"MCP call failed: {detail}") from exc

    if getattr(result, "isError", False):
        raise ZapierMCPError(f"tool returned error: {result.content!r}")

    debug_info: dict[str, Any] = {
        "block_count": len(result.content) if result.content else 0,
        "block_types": [getattr(b, "type", "?") for b in (result.content or [])],
        "raw_text_preview": _preview_raw_text(result.content),
    }
    rows = _parse_tool_content(result.content)
    debug_info["parsed_row_count"] = len(rows)
    return rows, debug_info


def _preview_raw_text(content: Any) -> str:
    """First 800 chars of concatenated text-block payloads, for /lookup
    debug output. Truncates so we don't leak large datasets into HTTP
    responses but keep enough to see Zapier's response shape."""
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    joined = "\n---\n".join(parts)
    if len(joined) > 800:
        return joined[:800] + f"... [truncated, total {len(joined)} chars]"
    return joined


def _format_exception_chain(exc: BaseException, depth: int = 0) -> str:
    """Flatten BaseExceptionGroup / ExceptionGroup hierarchies into a
    readable list. anyio's TaskGroup wraps real failures one or two
    levels deep, and str(eg) yields only the generic "unhandled errors
    in a TaskGroup" message.
    """
    if depth > 4:
        return f"{type(exc).__name__}: <max-depth>"

    inner: list[BaseException] | None = getattr(exc, "exceptions", None)
    if inner:
        children = "; ".join(_format_exception_chain(e, depth + 1) for e in inner)
        return f"{type(exc).__name__}[{children}]"

    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return f"{type(exc).__name__}({exc}) ← {_format_exception_chain(cause, depth + 1)}"

    return f"{type(exc).__name__}: {exc}"


def _parse_tool_content(content: Any) -> list[dict[str, Any]]:
    """Extract row dicts from an MCP tool result's content blocks.

    Zapier's snowflake_execute_sql wraps its result as text content
    containing JSON like:
      {"results": {"row_count": N, "rows": [{...}, ...]}}
    We tolerate a few variant shapes (top-level array, top-level rows)
    so this function isn't overly brittle to format drift.
    """
    if not content:
        return []
    # `content` may be a list of TextContent / ImageContent / etc.
    # The SQL result we care about is a text block.
    text_blocks: list[str] = []
    for block in content:
        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if block_type == "text" and isinstance(text, str):
            text_blocks.append(text)

    for raw in text_blocks:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        rows = _extract_rows(payload)
        if rows is not None:
            return rows

    logger.warning("zapier_mcp_unparseable_response", text_blocks_count=len(text_blocks))
    return []


def _extract_rows(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return None
    if "rows" in payload and isinstance(payload["rows"], list):
        return [r for r in payload["rows"] if isinstance(r, dict)]
    # Zapier returns SQL results as {"results": [{...}, ...]} — a list
    # directly under "results", not a nested {"rows": [...]} dict.
    # Tolerate both shapes for resilience to format drift.
    if "results" in payload:
        inner = payload["results"]
        if isinstance(inner, list):
            return [r for r in inner if isinstance(r, dict)]
        if isinstance(inner, dict) and isinstance(inner.get("rows"), list):
            return [r for r in inner["rows"] if isinstance(r, dict)]
    if "data" in payload and isinstance(payload["data"], list):
        return [r for r in payload["data"] if isinstance(r, dict)]
    return None
