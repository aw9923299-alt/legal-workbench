from __future__ import annotations

from dataclasses import asdict, dataclass

from legal_workbench.agents.legal_butler import (
    ButlerPlanningOutput,
    ButlerSynthesisOutput,
)
from legal_workbench.agents.legal_contracts import LegalWorkProduct


def _ratio(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 1.0


def _contains_all(values: list[str], expected: tuple[str, ...]) -> float:
    combined = "\n".join(values).casefold()
    return _ratio([term.casefold() in combined for term in expected])


@dataclass(frozen=True, slots=True)
class LegalAgentQualityScores:
    schema_validity: float
    fact_grounding: float
    issue_coverage: float
    legal_basis_grounding: float
    citation_fidelity: float
    hallucination: float
    risk_identification: float
    actionability: float
    missing_information_detection: float
    draft_usefulness: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def score_legal_work_product(
    product: LegalWorkProduct,
    *,
    authorized_source_refs: frozenset[str],
    internal_precedent_refs: frozenset[str] = frozenset(),
    expected_issue_terms: tuple[str, ...] = (),
    expected_missing_information: tuple[str, ...] = (),
) -> LegalAgentQualityScores:
    facts_grounded = [
        bool(fact.source_refs)
        and all(ref in authorized_source_refs for ref in fact.source_refs)
        for fact in product.facts
    ]
    basis_grounded = [
        bool(item.source_refs)
        and all(
            ref in authorized_source_refs and ref not in internal_precedent_refs
            for ref in item.source_refs
        )
        for item in product.legal_basis
    ]
    citation_fidelity = [
        citation.source_ref in authorized_source_refs
        and citation.internal_precedent
        == (citation.source_ref in internal_precedent_refs)
        for citation in product.citations
    ]
    used_refs = {
        ref
        for fact in product.facts
        for ref in fact.source_refs
    } | {
        ref
        for item in product.legal_basis
        for ref in item.source_refs
    } | {
        ref
        for item in product.analysis
        for ref in item.support_refs
    } | {citation.source_ref for citation in product.citations}
    return LegalAgentQualityScores(
        schema_validity=1.0,
        fact_grounding=_ratio(facts_grounded),
        issue_coverage=_contains_all(product.issues, expected_issue_terms),
        legal_basis_grounding=_ratio(basis_grounded),
        citation_fidelity=_ratio(citation_fidelity),
        hallucination=float(used_refs <= authorized_source_refs),
        risk_identification=float(bool(product.risks)),
        actionability=float(bool(product.recommended_actions)),
        missing_information_detection=_contains_all(
            product.missing_information, expected_missing_information
        ),
        draft_usefulness=float(len(product.draft_response.strip()) >= 10),
    )


@dataclass(frozen=True, slots=True)
class ButlerQualityScores:
    routing_accuracy: float
    unnecessary_agent_calls: float
    missing_required_specialist: float
    dependency_correctness: float
    synthesis_completeness: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def score_butler_outputs(
    planning: ButlerPlanningOutput,
    synthesis: ButlerSynthesisOutput,
    *,
    required_specialists: frozenset[str],
    expected_dependencies: frozenset[tuple[str, str]] = frozenset(),
) -> ButlerQualityScores:
    routed = {step.agent_key for step in planning.steps}
    actual_dependencies = {
        (dependency, step.step_id)
        for step in planning.steps
        for dependency in step.depends_on
    }
    required_present = required_specialists <= routed
    only_required = routed <= required_specialists
    synthesis_sections = [
        synthesis.matter_assessment,
        *synthesis.core_facts,
        *synthesis.key_legal_issues,
        *synthesis.recommended_strategy,
        *synthesis.next_actions,
        synthesis.draft_response,
    ]
    return ButlerQualityScores(
        routing_accuracy=float(required_present and only_required),
        unnecessary_agent_calls=float(only_required),
        missing_required_specialist=float(required_present),
        dependency_correctness=float(actual_dependencies == expected_dependencies),
        synthesis_completeness=float(
            all(value.strip() for value in synthesis_sections)
            and required_specialists <= set(synthesis.participating_agents)
        ),
    )
