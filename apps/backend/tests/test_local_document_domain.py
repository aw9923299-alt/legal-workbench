from __future__ import annotations

from uuid import uuid4

import pytest

from legal_workbench.domain.documents import (
    DocumentVersion,
    LocalDocumentObservation,
    LocalDocumentSource,
)
from legal_workbench.domain.enums import LocalDocumentSourceStatus
from legal_workbench.domain.errors import DomainValidationError


def test_local_document_source_keeps_only_a_relative_provenance_path() -> None:
    source = LocalDocumentSource(
        id=uuid4(),
        source_root_key="codex_obs_legal",
        relative_path="法规/民法典.pdf",
        display_name="民法典.pdf",
    )

    assert source.relative_path == "法规/民法典.pdf"
    assert source.status == LocalDocumentSourceStatus.ACTIVE


@pytest.mark.parametrize(
    "relative_path",
    ["/Users/legal/secret.pdf", "../secret.pdf", "法规/../secret.pdf"],
)
def test_local_document_source_rejects_path_disclosure_and_traversal(relative_path: str) -> None:
    with pytest.raises(DomainValidationError, match="relative path"):
        LocalDocumentSource(
            id=uuid4(),
            source_root_key="codex_obs_legal",
            relative_path=relative_path,
            display_name="secret.pdf",
        )


def test_local_observation_validates_sha_and_size() -> None:
    source_id = uuid4()
    observation = LocalDocumentObservation(
        id=uuid4(),
        local_source_id=source_id,
        scan_id=uuid4(),
        content_sha256="a" * 64,
        size=42,
        modified_at_ns=123,
    )

    assert observation.local_source_id == source_id

    with pytest.raises(DomainValidationError, match="observation"):
        LocalDocumentObservation(
            id=uuid4(),
            local_source_id=source_id,
            scan_id=uuid4(),
            content_sha256="bad",
            size=-1,
            modified_at_ns=123,
        )


def test_document_version_accepts_exactly_one_local_source() -> None:
    version = DocumentVersion(
        id=uuid4(),
        attachment_id=None,
        feishu_document_id=None,
        local_source_id=uuid4(),
        version=1,
        content_sha256="b" * 64,
        file_name="policy.md",
        mime_type="text/markdown",
        size=10,
        local_path="controlled-cache/digest.md",
    )

    assert version.local_source_id is not None

    with pytest.raises(DomainValidationError, match="exactly one source"):
        DocumentVersion(
            id=uuid4(),
            attachment_id=uuid4(),
            feishu_document_id=None,
            local_source_id=uuid4(),
            version=1,
            content_sha256="b" * 64,
            file_name="policy.md",
            mime_type="text/markdown",
            size=10,
            local_path="controlled-cache/digest.md",
        )
