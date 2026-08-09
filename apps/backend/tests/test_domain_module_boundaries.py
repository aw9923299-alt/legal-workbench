from __future__ import annotations

import ast
import importlib
from pathlib import Path

import legal_workbench.domain.entities as facade

DOMAIN_CONTEXTS: dict[str, tuple[str, ...]] = {
    "audit": ("AuthenticatedActorId", "AuditEvent", "OutboxEvent", "IdempotencyRecord"),
    "candidates": ("MessageCandidate",),
    "matters": ("LegalMatter", "ProposalFieldDecision", "MatterUpdateProposal"),
    "work_items": ("WorkItem", "PriorityConfirmation", "Deadline", "WorkItemDependency"),
    "reviews": ("ReviewPackage", "ReviewRecord", "Communication"),
    "agents": (
        "ContextSnapshot",
        "AgentRunStatusChange",
        "CandidateRevision",
        "AgentDefinition",
        "AgentAttemptLease",
        "AgentRunAttempt",
        "AgentRun",
        "AgentRunSource",
        "DraftArtifact",
    ),
    "feishu": (
        "FeishuRawEvent",
        "IntegrationConnection",
        "FeishuOAuthAttempt",
        "FeishuUserAuthorization",
        "FeishuSyncCheckpoint",
        "FeishuMessageVersion",
        "MessageAttachment",
        "FeishuMessage",
    ),
    "documents": (
        "ExtractedSegment",
        "ExtractedDocument",
        "DocumentVersion",
        "DocumentExtraction",
        "DocumentSegment",
        "FeishuDocument",
        "FeishuDocumentSubscription",
    ),
    "evaluations": ("EvaluationCase", "EvaluationRun", "EvaluationResult"),
    "setup": ("SystemSetting", "IntegrationCredential", "IntegrationScope", "IntegrationCheckRun"),
}


def test_entities_facade_reexports_context_owned_types() -> None:
    for context, names in DOMAIN_CONTEXTS.items():
        module = importlib.import_module(f"legal_workbench.domain.{context}")
        for name in names:
            assert getattr(facade, name) is getattr(module, name)


def test_domain_contexts_do_not_depend_on_outer_layers() -> None:
    root = Path(__file__).parents[1] / "src" / "legal_workbench" / "domain"
    forbidden = (
        "legal_workbench.application",
        "legal_workbench.api",
        "legal_workbench.infrastructure",
        "legal_workbench.integrations",
        "legal_workbench.workers",
    )
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text())
        from_imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        direct_imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        imports = [*from_imports, *direct_imports]
        assert not [value for value in imports if value.startswith(forbidden)], path.name


def test_ports_are_a_context_package_with_compatibility_exports() -> None:
    application_root = Path(__file__).parents[1] / "src" / "legal_workbench" / "application"
    assert not (application_root / "ports.py").exists()
    ports = importlib.import_module("legal_workbench.application.ports")
    for module_name in (
        "agents",
        "matters",
        "reviews",
        "feishu",
        "documents",
        "evaluations",
        "setup",
        "infrastructure",
    ):
        module = importlib.import_module(f"legal_workbench.application.ports.{module_name}")
        for name in module.__all__:
            assert getattr(ports, name) is getattr(module, name)
