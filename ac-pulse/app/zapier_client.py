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
) -> list[dict[str, Any]]:
    """Call Zapier MCP's snowflake_execute_sql tool and return the row list.

    Opens a fresh streamable HTTP session per call. Per-call cost is the
    session initialize handshake (~100-300ms) plus the SQL execution
    time. For workloads that need lower overhead we'd cache the session,
    but for dedupe lookups the simplicity of "open/use/close" outweighs
    the session-reuse complexity (and is what the Zapier docs ship).

    Args:
      server_url: Zapier MCP server URL for the tenant.
      token: Bearer token for the MCP server.
      statement: Full SQL string. Email/domain interpolation must happen
        upstream; this function does no string substitution.
      output_hint: REQUIRED by Zapier. Natural-language description of
        the columns to return. To preserve every column, list them all
        explicitly — Zapier's filter otherwise drops anything you didn't
        explicitly name.
      instructions: Optional natural-language context for the call.

    Returns:
      List of row dicts (one per result row). Empty list when the SQL
      returned no rows.

    Raises:
      ZapierMCPError: when the call fails or the result can't be parsed.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with streamablehttp_client(server_url, headers=headers) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "snowflake_execute_sql",
                    arguments={
                        "statement": statement,
                        "output_hint": output_hint,
                        "instructions": instructions,
                    },
                )
    except Exception as exc:
        logger.exception("zapier_mcp_call_failed")
        raise ZapierMCPError(f"MCP call failed: {exc}") from exc

    # MCP tool results carry content as a list of blocks. Zapier wraps
    # the SQL response in a single text block whose payload is JSON.
    if getattr(result, "isError", False):
        raise ZapierMCPError(f"tool returned error: {result.content!r}")

    rows = _parse_tool_content(result.content)
    return rows


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
    if "results" in payload and isinstance(payload["results"], dict):
        results = payload["results"]
        if "rows" in results and isinstance(results["rows"], list):
            return [r for r in results["rows"] if isinstance(r, dict)]
    if "data" in payload and isinstance(payload["data"], list):
        return [r for r in payload["data"] if isinstance(r, dict)]
    return None
