from __future__ import annotations

import pytest

from legal_workbench.application.feishu_capabilities import (
    INITIAL_OAUTH_SCOPES,
    FeishuCapability,
    FeishuCapabilityStatus,
    authorization_is_usable,
    project_capabilities,
)

CORE = {"offline_access", "contact:user.base:readonly"}
MESSAGES = {
    "im:message:readonly",
    "im:message.p2p_msg:get_as_user",
    "im:message.group_msg:get_as_user",
}


@pytest.mark.parametrize("chat_scope", ["im:chat:read", "im:chat:readonly"])
def test_chat_discovery_accepts_either_official_read_scope(chat_scope: str) -> None:
    projections = project_capabilities(CORE | MESSAGES | {chat_scope})

    assert (
        projections[FeishuCapability.CHAT_DISCOVERY].status
        == FeishuCapabilityStatus.READY
    )


def test_missing_document_and_drive_permissions_do_not_disable_messages() -> None:
    projections = project_capabilities(CORE | MESSAGES | {"im:chat:readonly"})

    assert (
        projections[FeishuCapability.MESSAGE_HISTORY].status
        == FeishuCapabilityStatus.READY
    )
    assert (
        projections[FeishuCapability.DOCUMENT_READ].status
        == FeishuCapabilityStatus.PERMISSION_MISSING
    )
    assert (
        projections[FeishuCapability.DRIVE_SEARCH].status
        == FeishuCapabilityStatus.PERMISSION_MISSING
    )
    assert authorization_is_usable(projections) is True


def test_missing_message_permissions_disable_only_message_features() -> None:
    projections = project_capabilities(
        CORE
        | {
            "im:chat:readonly",
            "docs:document.content:read",
            "drive:drive.search:readonly",
            "drive:drive.metadata:readonly",
        }
    )

    assert (
        projections[FeishuCapability.MESSAGE_HISTORY].status
        == FeishuCapabilityStatus.PERMISSION_MISSING
    )
    assert (
        projections[FeishuCapability.DOCUMENT_READ].status
        == FeishuCapabilityStatus.READY
    )
    assert authorization_is_usable(projections) is True


def test_missing_core_identity_makes_authorization_unusable() -> None:
    projections = project_capabilities(MESSAGES | {"im:chat:readonly"})

    assert (
        projections[FeishuCapability.CORE_IDENTITY].status
        == FeishuCapabilityStatus.PERMISSION_MISSING
    )
    assert authorization_is_usable(projections) is False


def test_attachment_read_is_partial_even_with_message_scopes() -> None:
    projections = project_capabilities(CORE | MESSAGES)

    assert (
        projections[FeishuCapability.ATTACHMENT_READ].status
        == FeishuCapabilityStatus.PARTIAL
    )


def test_initial_oauth_scope_does_not_require_optional_document_or_drive_scopes() -> None:
    assert "docs:document.content:read" not in INITIAL_OAUTH_SCOPES
    assert "drive:drive.search:readonly" not in INITIAL_OAUTH_SCOPES
    assert "drive:drive:readonly" not in INITIAL_OAUTH_SCOPES
    assert "im:chat:read" in INITIAL_OAUTH_SCOPES
    assert "im:chat:readonly" not in INITIAL_OAUTH_SCOPES
