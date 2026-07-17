from scripts.codex_mcp_namespace_proxy import (
    expand_namespace_tools,
    restore_tool_namespaces,
    transform_response_body,
)


def test_expands_namespace_tools_to_flat_functions() -> None:
    payload = {
        "model": "MiniMax-M3",
        "tools": [
            {"type": "function", "name": "shell", "parameters": {}},
            {
                "type": "namespace",
                "name": "mcp__minimax",
                "tools": [
                    {
                        "name": "web_search",
                        "description": "Search",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ],
            },
        ],
    }

    transformed = expand_namespace_tools(payload)

    assert transformed["tools"] == [
        {"type": "function", "name": "shell", "parameters": {}},
        {
            "type": "function",
            "name": "minimax_web_search",
            "description": "Search",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "strict": False,
        },
    ]


def test_restores_namespace_on_nested_function_call() -> None:
    payload = {
        "type": "response.output_item.done",
        "item": {
            "type": "function_call",
            "name": "minimax_web_search",
            "arguments": '{"query":"Xi 2020"}',
        },
    }

    transformed = restore_tool_namespaces(payload)

    assert transformed["item"]["namespace"] == "mcp__minimax"
    assert transformed["item"]["name"] == "web_search"


def test_transforms_server_sent_event_data() -> None:
    body = (
        b'data: {"type":"response.output_item.done","item":'
        b'{"type":"function_call","name":"minimax_web_search"}}\n\n'
        b"data: [DONE]\n\n"
    )

    transformed = transform_response_body(body, "text/event-stream")

    assert b'"namespace":"mcp__minimax"' in transformed
    assert b'"name":"web_search"' in transformed
    assert b"data: [DONE]" in transformed


def test_restores_unambiguous_research_tool_aliases() -> None:
    transformed = restore_tool_namespaces(
        [
            {"type": "function_call", "name": "parallel_web_search"},
            {"type": "function_call", "name": "parallel_web_fetch"},
            {"type": "function_call", "name": "brave_web_search"},
        ]
    )

    assert transformed == [
        {
            "type": "function_call",
            "namespace": "mcp__parallel",
            "name": "web_search",
        },
        {
            "type": "function_call",
            "namespace": "mcp__parallel",
            "name": "web_fetch",
        },
        {
            "type": "function_call",
            "namespace": "mcp__brave",
            "name": "brave_web_search",
        },
    ]


def test_routes_bare_names_to_the_selected_parallel_server() -> None:
    transformed = restore_tool_namespaces(
        [
            {"type": "function_call", "name": "web_search"},
            {"type": "function_call", "name": "web_fetch"},
        ]
    )

    assert transformed == [
        {
            "type": "function_call",
            "namespace": "mcp__parallel",
            "name": "web_search",
        },
        {
            "type": "function_call",
            "namespace": "mcp__parallel",
            "name": "web_fetch",
        },
    ]


def test_repairs_minimax_singleton_wrapper_for_parallel_list_arguments() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "parallel_web_search",
            "arguments": '{"objective":"x","search_queries":{"item":["a","b"]}}',
        }
    )

    assert transformed["namespace"] == "mcp__parallel"
    assert transformed["name"] == "web_search"
    assert transformed["arguments"] == '{"objective":"x","search_queries":["a","b"]}'


def test_repairs_minimax_scalar_wrapper_for_parallel_fetch_urls() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "web_fetch",
            "arguments": {
                "objective": "x",
                "urls": {"item": "https://example.test/source"},
            },
        }
    )

    assert transformed["arguments"]["urls"] == ["https://example.test/source"]


def test_sse_transform_repairs_wrapped_parallel_arguments() -> None:
    body = (
        b'data: {"type":"response.output_item.done","item":'
        b'{"type":"function_call","name":"web_search","arguments":'
        b'"{\\"search_queries\\":{\\"item\\":\\"query\\"}}"}}\n\n'
    )

    transformed = transform_response_body(body, "text/event-stream")

    assert b'\\"search_queries\\":[\\"query\\"]' in transformed
    assert b'"namespace":"mcp__parallel"' in transformed


def test_invalid_parallel_wrapper_is_preserved_for_normal_validation() -> None:
    arguments = {"search_queries": {"item": ["valid"], "extra": "invalid"}}

    transformed = restore_tool_namespaces(
        {"type": "function_call", "name": "web_search", "arguments": arguments}
    )

    assert transformed["arguments"] == arguments


def test_removes_brave_freshness_filter_from_research_search() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "brave_web_search",
            "arguments": '{"query":"Argentina 2000","freshness":"py","count":10}',
        }
    )

    assert transformed["namespace"] == "mcp__brave"
    assert transformed["name"] == "brave_web_search"
    assert transformed["arguments"] == '{"query":"Argentina 2000","count":10}'


def test_repairs_minimax_malformed_flat_namespace_name() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "mcp__parallelweb_search",
            "arguments": {"search_queries": ["Argentina 2000"]},
        }
    )

    assert transformed["namespace"] == "mcp__parallel"
    assert transformed["name"] == "web_search"


def test_routes_fetch_url_alias() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "fetch_url",
            "arguments": {"url": "https://example.test/report"},
        }
    )

    assert transformed["namespace"] == "mcp__fetch"
    assert transformed["name"] == "fetch"


def test_routes_native_fetch_alias() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "fetch",
            "arguments": {"url": "https://example.test/report"},
        }
    )

    assert transformed["namespace"] == "mcp__fetch"
    assert transformed["name"] == "fetch"


def test_explicit_current_mode_preserves_brave_freshness() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "brave_web_search",
            "arguments": {"query": "Argentina 2026", "freshness": "py"},
        },
        strip_search_freshness=False,
    )

    assert transformed["arguments"]["freshness"] == "py"


def test_removes_historical_freshness_from_namespaced_call() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "namespace": "mcp__brave",
            "name": "brave_web_search",
            "arguments": {"query": "Argentina 2000", "freshness": "py"},
        }
    )

    assert "freshness" not in transformed["arguments"]


def test_historical_mode_removes_freshness_without_year_in_query() -> None:
    transformed = restore_tool_namespaces(
        {
            "type": "function_call",
            "name": "brave_web_search",
            "arguments": {"query": "de la Rua press freedom", "freshness": "py"},
        }
    )

    assert "freshness" not in transformed["arguments"]
