from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from legal_workbench.domain.enums import (
    AuthorityRole,
    AuthorityStatus,
    AuthorityType,
    KnowledgeMetadataStatus,
)
from legal_workbench.domain.errors import DomainValidationError
from legal_workbench.domain.knowledge import (
    KnowledgeDocument,
    authority_role_for_type,
)


def _document(**overrides: object) -> KnowledgeDocument:
    values: dict[str, object] = {
        "id": uuid4(),
        "source_type": "local_document",
        "source_id": "source-1",
        "title": "中华人民共和国民法典",
        "document_type": "law",
        "agent_types": ["contract"],
        "matter_types": ["contract"],
        "jurisdiction": "CN",
        "source_priority": 100,
        "internal_precedent": False,
        "confidentiality": "internal",
        "authority_type": AuthorityType.LAW,
        "authority_role": AuthorityRole.FORMAL_LEGAL_BASIS,
        "authority_status": AuthorityStatus.EFFECTIVE,
        "metadata_status": KnowledgeMetadataStatus.READY,
    }
    values.update(overrides)
    return KnowledgeDocument(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("authority_type", "expected_role"),
    [
        (AuthorityType.LAW, AuthorityRole.FORMAL_LEGAL_BASIS),
        (AuthorityType.ADMINISTRATIVE_REGULATION, AuthorityRole.FORMAL_LEGAL_BASIS),
        (AuthorityType.GUIDING_CASE, AuthorityRole.PERSUASIVE_AUTHORITY),
        (AuthorityType.CONTRACT, AuthorityRole.CONTRACTUAL_BASIS),
        (AuthorityType.COMPANY_POLICY, AuthorityRole.INTERNAL_BASIS),
        (AuthorityType.BUSINESS_RULE, AuthorityRole.INTERNAL_BASIS),
        (AuthorityType.LEGAL_OPINION, AuthorityRole.STRATEGY_REFERENCE),
        (AuthorityType.INTERNAL_PRECEDENT, AuthorityRole.STRATEGY_REFERENCE),
        (AuthorityType.UNKNOWN, None),
    ],
)
def test_authority_type_has_deterministic_role(
    authority_type: AuthorityType,
    expected_role: AuthorityRole | None,
) -> None:
    assert authority_role_for_type(authority_type) == expected_role


def test_company_policy_cannot_claim_formal_legal_basis() -> None:
    with pytest.raises(DomainValidationError, match="authority role"):
        _document(
            authority_type=AuthorityType.COMPANY_POLICY,
            authority_role=AuthorityRole.FORMAL_LEGAL_BASIS,
        )


def test_unknown_authority_requires_pending_metadata_and_no_role() -> None:
    document = _document(
        authority_type=AuthorityType.UNKNOWN,
        authority_role=None,
        authority_status=AuthorityStatus.UNKNOWN,
        metadata_status=KnowledgeMetadataStatus.PENDING_METADATA,
    )

    assert document.authority_role is None

    with pytest.raises(DomainValidationError, match="pending metadata"):
        _document(
            authority_type=AuthorityType.UNKNOWN,
            authority_role=None,
            metadata_status=KnowledgeMetadataStatus.READY,
        )


def test_repealed_formal_authority_is_not_currently_eligible() -> None:
    document = _document(authority_status=AuthorityStatus.REPEALED)

    assert document.is_current_formal_legal_basis(on_date=date(2026, 8, 9)) is False


def test_effective_formal_authority_honours_effective_dates() -> None:
    document = _document(
        effective_from=date(2021, 1, 1),
        effective_to=date(2026, 8, 8),
    )

    assert document.is_current_formal_legal_basis(on_date=date(2026, 8, 8)) is True
    assert document.is_current_formal_legal_basis(on_date=date(2026, 8, 9)) is False
