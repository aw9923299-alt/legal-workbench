from legal_workbench.integrations.feishu_personal_capabilities import (
    PERSONAL_CAPABILITY_KEYS,
    build_not_executed_report,
)


def test_capability_report_never_claims_success_without_live_execution() -> None:
    report = build_not_executed_report(reason="missing_real_credentials")

    assert {item.capability for item in report.results} == set(PERSONAL_CAPABILITY_KEYS)
    assert {item.status for item in report.results} == {"not_executed"}
    assert report.real_feishu is False
    assert "token" not in report.model_dump_json().lower()
