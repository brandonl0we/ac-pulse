from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


def build_account_map_preview(
    *,
    portfolio: dict[str, Any],
    activecampaign_accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    ac_index = _index_activecampaign_accounts(activecampaign_accounts)
    matched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for account in portfolio.get("accounts", []):
        sf_account = _snowflake_account(account)
        keys = _snowflake_keys(account)
        candidates_by_id: dict[int, dict[str, Any]] = {}
        for key in keys:
            for candidate in ac_index.get(key, []):
                candidates_by_id[int(candidate["ac_account_id"])] = candidate

        candidates = sorted(
            candidates_by_id.values(),
            key=lambda row: (row.get("ac_account_name") or "", row["ac_account_id"]),
        )
        if len(candidates) == 1:
            candidate = candidates[0]
            matched.append(
                {
                    **sf_account,
                    **candidate,
                    "match_keys": sorted(keys & set(candidate["match_keys"])),
                    "confidence": "high",
                }
            )
        elif len(candidates) > 1:
            ambiguous.append(
                {
                    **sf_account,
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                }
            )
        else:
            unmatched.append({**sf_account, "match_keys": sorted(keys)})

    csv_rows = [
        "snowflake_account_id,ac_account_id",
        *[
            f"{row['snowflake_account_id']},{row['ac_account_id']}"
            for row in sorted(matched, key=lambda item: item["snowflake_account_id"])
        ],
    ]
    account_id_map = {
        str(row["snowflake_account_id"]): row["ac_account_id"]
        for row in sorted(matched, key=lambda item: item["snowflake_account_id"])
    }

    return {
        "mode": "read_only",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "rep_name": portfolio.get("success_rep_name"),
            "snowflake_accounts": len(portfolio.get("accounts", [])),
            "activecampaign_accounts": len(activecampaign_accounts),
            "activecampaign_indexed_accounts": len(
                {
                    int(candidate["ac_account_id"])
                    for candidates in ac_index.values()
                    for candidate in candidates
                }
            ),
        },
        "diagnostics": {
            "activecampaign_sample": _activecampaign_sample(activecampaign_accounts),
            "snowflake_sample": [
                {
                    **_snowflake_account(account),
                    "match_keys": sorted(_snowflake_keys(account)),
                }
                for account in portfolio.get("accounts", [])[:10]
            ],
        },
        "summary": {
            "matched": len(matched),
            "ambiguous": len(ambiguous),
            "unmatched": len(unmatched),
        },
        "matched": matched,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
        "account_id_map": account_id_map,
        "csv": "\n".join(csv_rows) + "\n",
    }


def _index_activecampaign_accounts(
    accounts: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for account in accounts:
        ac_account_id = _as_int(account.get("id"))
        if ac_account_id is None:
            continue

        match_keys = sorted(_activecampaign_keys(account))
        entry = {
            "ac_account_id": ac_account_id,
            "ac_account_name": account.get("name"),
            "ac_account_url": account.get("accountUrl") or account.get("account_url"),
            "match_keys": match_keys,
        }
        for key in match_keys:
            index[key].append(entry)
    return index


def _snowflake_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "snowflake_account_id": int(account["account_id"]),
        "snowflake_account_name": account.get("account_name"),
        "account_web_domain": account.get("account_web_domain"),
        "arr": account.get("arr"),
    }


def _snowflake_keys(account: dict[str, Any]) -> set[str]:
    return _identity_keys(account.get("account_name")) | _identity_keys(
        account.get("account_web_domain")
    )


def _activecampaign_keys(account: dict[str, Any]) -> set[str]:
    return _identity_keys(account.get("name")) | _identity_keys(
        account.get("accountUrl") or account.get("account_url")
    )


def _activecampaign_sample(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ac_account_id": _as_int(account.get("id")),
            "ac_account_name": account.get("name"),
            "ac_account_url": account.get("accountUrl") or account.get("account_url"),
            "raw_keys": sorted(str(key) for key in account),
            "match_keys": sorted(_activecampaign_keys(account)),
        }
        for account in accounts[:10]
    ]


def _identity_keys(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()

    keys = {_simple_key(text)}
    host = _host_key(text)
    if host:
        keys.add(host)
        if host.endswith(".activehosted.com"):
            keys.add(host.removesuffix(".activehosted.com"))
    return {key for key in keys if key}


def _simple_key(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _host_key(value: str) -> str | None:
    text = value.strip().casefold()
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    host = host.strip().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
