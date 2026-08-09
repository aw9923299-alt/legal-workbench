from legal_workbench.integrations.feishu_personal_capabilities import (
    PERSONAL_CAPABILITY_KEYS,
    _first_document_token,
    build_unavailable_report,
)


def test_capability_report_never_claims_success_without_live_execution() -> None:
    report = build_unavailable_report(reason="missing_real_credentials")

    assert {item.capability for item in report.results} == set(PERSONAL_CAPABILITY_KEYS)
    assert {item.status for item in report.results} == {"unsupported"}
    assert "not_executed" not in report.model_dump_json()
    assert report.real_feishu is False
    assert report.identity_source == "unavailable"
    assert report.cli_token_used is False
    assert set(report.operational_readiness) == {
        "Identity",
        "Messages",
        "Chat discovery",
        "Documents",
    }
    rendered = report.model_dump_json().lower()
    assert "access_token" not in rendered
    assert "refresh_token" not in rendered


def test_capability_report_has_all_real_closure_probes() -> None:
    assert set(PERSONAL_CAPABILITY_KEYS) == {
        "oauth_pkce",
        "refresh_rotation",
        "known_p2p_history",
        "known_group_history",
        "group_discovery",
        "p2p_discovery",
        "unread_state",
        "personal_attachment",
        "document_search",
        "document_markdown",
        "thread_reply",
        "local_feishu_discovery",
        "local_api_duplicate_idempotency",
    }


def test_document_markdown_probe_can_reuse_a_search_result_without_exposing_it() -> None:
    value = (({"doc_token": "safe-existing-token", "title": "not exported"},), None)

    assert _first_document_token(value) == "safe-existing-token"
    assert _first_document_token(((), None)) is None
