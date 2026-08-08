from legal_workbench.integrations.feishu_personal_capabilities import (
    PERSONAL_CAPABILITY_KEYS,
    build_unavailable_report,
)


def test_capability_report_never_claims_success_without_live_execution() -> None:
    report = build_unavailable_report(reason="missing_real_credentials")

    assert {item.capability for item in report.results} == set(PERSONAL_CAPABILITY_KEYS)
    assert {item.status for item in report.results} == {"unsupported"}
    assert "not_executed" not in report.model_dump_json()
    assert report.real_feishu is False
    assert "token" not in report.model_dump_json().lower()


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
