from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_SAFE_LOCAL_EVIDENCE_BASH = {
    "*": "deny",
    "leaders-db research local-evidence --*": "allow",
    "leaders-db research parallel-search --*": "allow",
}

EXPECTED_ALLOWED_WEB_PATH = {
    "discovery": "leaders-db research parallel-search",
    "known_url_fetch": "webfetch",
    "fallback_known_url_fetch": "webfetch",
}

EXPECTED_WEB_ALLOWS = {
    "webfetch": "allow",
}

EXPECTED_EXPLICIT_DENIES = {
    "edit",
    "write",
    "minimax_web_search",
    "minimax_understand_image",
    "websearch",
    "brave_search_brave_llm_context",
    "brave_search_brave_web_search",
    "brave_search_brave_news_search",
    "brave_search_brave_image_search",
    "brave_search_brave_video_search",
    "brave_search_brave_local_search",
    "brave_search_brave_place_search",
    "brave_search_brave_summarizer",
    "playwright_browser_navigate",
    "playwright_browser_click",
    "playwright_browser_type",
    "playwright_browser_fill_form",
    "playwright_browser_select_option",
    "playwright_browser_press_key",
    "playwright_browser_hover",
    "playwright_browser_drag",
    "playwright_browser_drop",
    "playwright_browser_file_upload",
    "playwright_browser_handle_dialog",
    "playwright_browser_evaluate",
    "playwright_browser_run_code_unsafe",
    "playwright_browser_network_requests",
    "playwright_browser_network_request",
    "playwright_browser_console_messages",
    "playwright_browser_snapshot",
    "playwright_browser_take_screenshot",
    "playwright_browser_wait_for",
    "playwright_browser_navigate_back",
    "playwright_browser_tabs",
    "playwright_browser_resize",
    "playwright_browser_close",
    "task",
    "question",
    "context7_resolve-library-id",
    "context7_query-docs",
    "github",
    "gh_grep_searchGitHub",
    "read",
    "grep",
    "glob",
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "read_mcp_resource",
    "skill",
    "todowrite",
    "apply_patch",
}


def test_internet_research_opencode_config_allows_only_safe_local_evidence_bash(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    permission = _opencode_config_permission(policy)

    assert permission["bash"] == EXPECTED_SAFE_LOCAL_EVIDENCE_BASH


def test_internet_research_agent_frontmatter_allows_only_safe_local_evidence_bash(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    metadata = policy["agent_frontmatter_template"]

    assert metadata["permission"]["bash"] == EXPECTED_SAFE_LOCAL_EVIDENCE_BASH


def test_internet_research_policy_is_deny_default(project_root: Path) -> None:
    policy = _load_tracked_policy(project_root)

    assert policy["default_posture"] == "deny"
    assert _restricted_contract(policy)["*"] == "deny"
    assert _opencode_config_permission(policy)["*"] == "deny"
    assert policy["agent_frontmatter_template"]["permission"]["*"] == "deny"


def test_internet_research_policy_templates_use_full_contract(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    contract = _restricted_contract(policy)

    assert _opencode_config_permission(policy) == contract
    assert policy["agent_frontmatter_template"]["permission"] == contract


def test_internet_research_policy_allows_only_approved_web_path(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    contract = _restricted_contract(policy)

    assert policy["allowed_web_path"] == EXPECTED_ALLOWED_WEB_PATH
    for tool_name, expected_permission in EXPECTED_WEB_ALLOWS.items():
        assert contract[tool_name] == expected_permission


def test_internet_research_policy_denies_disallowed_capabilities(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    contract = _restricted_contract(policy)

    obsolete_mcp_tools = set(policy["obsolete_mcp_tools_not_approved"])
    expected_denies = EXPECTED_EXPLICIT_DENIES | obsolete_mcp_tools
    missing_denies = expected_denies - contract.keys()

    assert missing_denies == set()
    for tool_name in expected_denies:
        assert contract[tool_name] == "deny"

    assert obsolete_mcp_tools == {
        "parallel_" + "search_web_search",
        "parallel_" + "search_web_fetch",
    }


def test_internet_research_policy_keeps_writes_explicitly_denied(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    contract = _restricted_contract(policy)

    assert contract["edit"] == "deny"
    assert contract["write"] == "deny"


def test_internet_research_policy_documents_parallel_api_key_location(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)

    assert policy["required_parallel_api"] == {
        "endpoint": "https://api.parallel.ai/v1/search",
        "api_key_environment_variable": "PARALLEL_API_KEY",
        "local_secret_file": ".env",
        "approved_cli": "leaders-db research parallel-search --*",
    }


def test_internet_research_policy_requires_run_profiling(project_root: Path) -> None:
    policy = _load_tracked_policy(project_root)
    profiling = policy["run_profiling_required"]

    assert profiling["enabled"] is True
    for field in (
        "started_at_utc",
        "completed_at_utc",
        "elapsed_seconds",
        "parallel_search_calls_attempted",
        "parallel_search_calls_succeeded",
        "parallel_search_calls_failed",
        "parallel_usage_reported_by_tool",
        "token_counts_reported_by_tool",
    ):
        assert field in profiling["minimum_fields"]
    assert "do not invent" in profiling["unknown_value_policy"].lower()


def test_internet_research_policy_requires_source_confidence_registry(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)

    registry = policy["source_confidence_registry"]

    assert registry["path"] == "docs/methodology/source-confidence-registry.json"
    assert registry["required"] is True
    assert registry["required_citation_profile_fields"] == [
        "source_confidence",
        "source_confidence_reason",
        "source_type",
        "final_evidence_use",
    ]
    assert "sole support" in registry["source_diversity_rule"].lower()


def test_internet_research_permission_policy_is_non_secret_template(
    project_root: Path,
) -> None:
    policy = _load_tracked_policy(project_root)
    policy_text = _policy_path(project_root).read_text(encoding="utf-8").lower()

    assert "opencode.json" in policy["local_files_not_committed"]
    assert (
        ".opencode/agent/internet-research.md" in policy["local_files_not_committed"]
    )
    assert "sk-" not in policy_text
    assert "ghp_" not in policy_text
    assert "github_pat_" not in policy_text
    assert "bearer " not in policy_text


def _load_tracked_policy(project_root: Path) -> dict[str, Any]:
    return json.loads(_policy_path(project_root).read_text(encoding="utf-8"))


def _restricted_contract(policy: dict[str, Any]) -> dict[str, Any]:
    return policy["restricted_worker_permission_contract"]


def _opencode_config_permission(policy: dict[str, Any]) -> dict[str, Any]:
    return policy["opencode_config_template"]["agent"]["internet-research"][
        "permission"
    ]


def _policy_path(project_root: Path) -> Path:
    return project_root / "docs/process/internet-research-opencode-policy.json"
