from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from legal_workbench.domain.errors import DomainValidationError


class FeishuCapability(StrEnum):
    CORE_IDENTITY = "core_identity"
    MESSAGE_HISTORY = "message_history"
    CHAT_DISCOVERY = "chat_discovery"
    DOCUMENT_READ = "document_read"
    DRIVE_SEARCH = "drive_search"
    ATTACHMENT_READ = "attachment_read"


class FeishuCapabilityStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    PERMISSION_MISSING = "permission_missing"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    satisfied_status: FeishuCapabilityStatus = FeishuCapabilityStatus.READY

    @property
    def scope_universe(self) -> frozenset[str]:
        return frozenset((*self.all_of, *self.any_of))


@dataclass(frozen=True, slots=True)
class CapabilityProjection:
    capability: FeishuCapability
    status: FeishuCapabilityStatus
    granted_scopes: tuple[str, ...]
    missing_scopes: tuple[str, ...]


CAPABILITY_REQUIREMENTS: Mapping[FeishuCapability, CapabilityRequirement] = (
    MappingProxyType(
        {
            FeishuCapability.CORE_IDENTITY: CapabilityRequirement(
                all_of=("offline_access", "contact:user.base:readonly"),
            ),
            FeishuCapability.MESSAGE_HISTORY: CapabilityRequirement(
                all_of=(
                    "im:message:readonly",
                    "im:message.p2p_msg:get_as_user",
                    "im:message.group_msg:get_as_user",
                ),
            ),
            FeishuCapability.CHAT_DISCOVERY: CapabilityRequirement(
                any_of=("im:chat:read", "im:chat:readonly"),
            ),
            FeishuCapability.DOCUMENT_READ: CapabilityRequirement(
                all_of=("docs:document.content:read",),
            ),
            FeishuCapability.DRIVE_SEARCH: CapabilityRequirement(
                all_of=("drive:drive.search:readonly",),
                any_of=(
                    "drive:drive.metadata:readonly",
                    "drive:drive:readonly",
                ),
            ),
            FeishuCapability.ATTACHMENT_READ: CapabilityRequirement(
                all_of=("im:message:readonly",),
                any_of=(
                    "im:message.p2p_msg:get_as_user",
                    "im:message.group_msg:get_as_user",
                ),
                satisfied_status=FeishuCapabilityStatus.PARTIAL,
            ),
        }
    )
)

CAPABILITY_LABELS: Mapping[FeishuCapability, str] = MappingProxyType(
    {
        FeishuCapability.CORE_IDENTITY: "Identity",
        FeishuCapability.MESSAGE_HISTORY: "Messages",
        FeishuCapability.CHAT_DISCOVERY: "Chat discovery",
        FeishuCapability.DOCUMENT_READ: "Documents",
        FeishuCapability.DRIVE_SEARCH: "Drive",
        FeishuCapability.ATTACHMENT_READ: "Attachments",
    }
)

REQUESTED_USER_SCOPES = tuple(
    dict.fromkeys(
        scope
        for capability in FeishuCapability
        for scope in (
            *CAPABILITY_REQUIREMENTS[capability].all_of,
            *CAPABILITY_REQUIREMENTS[capability].any_of,
        )
    )
)

CORE_IDENTITY_SCOPES = CAPABILITY_REQUIREMENTS[
    FeishuCapability.CORE_IDENTITY
].all_of

# Initial authorization is deliberately limited to the capabilities required for
# Personal Message Sync. Optional document and drive permissions can be granted
# later without making the base user authorization unusable.
INITIAL_OAUTH_SCOPES = tuple(
    dict.fromkeys(
        (
            *CORE_IDENTITY_SCOPES,
            *CAPABILITY_REQUIREMENTS[FeishuCapability.MESSAGE_HISTORY].all_of,
            "im:chat:read",
        )
    )
)


def project_capabilities(
    granted_scopes: set[str] | frozenset[str] | tuple[str, ...] | list[str],
) -> dict[FeishuCapability, CapabilityProjection]:
    granted = frozenset(granted_scopes)
    projections: dict[FeishuCapability, CapabilityProjection] = {}
    for capability, requirement in CAPABILITY_REQUIREMENTS.items():
        missing_all = tuple(
            scope for scope in requirement.all_of if scope not in granted
        )
        any_satisfied = not requirement.any_of or bool(
            granted.intersection(requirement.any_of)
        )
        if not missing_all and any_satisfied:
            status = requirement.satisfied_status
        elif granted.intersection(requirement.scope_universe):
            status = FeishuCapabilityStatus.PARTIAL
        else:
            status = FeishuCapabilityStatus.PERMISSION_MISSING
        missing_any = () if any_satisfied else requirement.any_of
        projections[capability] = CapabilityProjection(
            capability=capability,
            status=status,
            granted_scopes=tuple(
                scope
                for scope in REQUESTED_USER_SCOPES
                if scope in granted and scope in requirement.scope_universe
            ),
            missing_scopes=tuple(dict.fromkeys((*missing_all, *missing_any))),
        )
    return projections


def authorization_is_usable(
    projections: Mapping[FeishuCapability, CapabilityProjection],
) -> bool:
    return (
        projections[FeishuCapability.CORE_IDENTITY].status
        == FeishuCapabilityStatus.READY
    )


def require_capability(
    granted_scopes: tuple[str, ...] | list[str] | set[str] | frozenset[str],
    capability: FeishuCapability,
    *,
    allow_partial: bool = False,
) -> CapabilityProjection:
    projection = project_capabilities(granted_scopes)[capability]
    allowed = {FeishuCapabilityStatus.READY}
    if allow_partial:
        allowed.add(FeishuCapabilityStatus.PARTIAL)
    if projection.status not in allowed:
        raise DomainValidationError(
            f"Feishu capability {capability.value} is unavailable.",
            details={
                "capability": capability.value,
                "status": projection.status.value,
                "missingScopes": list(projection.missing_scopes),
            },
        )
    return projection
