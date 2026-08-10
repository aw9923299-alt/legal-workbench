from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from legal_workbench.domain.agents import AgentPlanStep
from legal_workbench.domain.enums import AgentPlanStepStatus
from legal_workbench.domain.errors import DomainValidationError


@dataclass(slots=True)
class DependencyResult:
    step_id: str
    run_id: UUID | None
    status: AgentPlanStepStatus
    output_payload: dict[str, object] | None
    source_refs: frozenset[str] = frozenset()
    internal_precedent_refs: frozenset[str] = frozenset()
    source_authorities: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DependencyContext:
    upstream_outputs: dict[str, object]
    source_refs: frozenset[str]
    internal_precedent_refs: frozenset[str]
    source_authorities: dict[str, dict[str, object]]
    dependency_run_ids: tuple[UUID, ...]


class DependencyContextAssembler:
    VALID_STATUSES = frozenset(
        {
            AgentPlanStepStatus.COMPLETED,
            AgentPlanStepStatus.NEEDS_INFORMATION,
        }
    )

    def build(
        self,
        step: AgentPlanStep,
        available_results: dict[str, DependencyResult],
    ) -> DependencyContext:
        upstream_outputs: dict[str, object] = {}
        source_refs: set[str] = set()
        precedent_refs: set[str] = set()
        source_authorities: dict[str, dict[str, object]] = {}
        dependency_run_ids: list[UUID] = []
        for dependency_id in dict.fromkeys(step.depends_on):
            dependency = available_results.get(dependency_id)
            if dependency is None:
                raise DomainValidationError(
                    f"Dependency {dependency_id} has no persisted result."
                )
            if dependency.status not in self.VALID_STATUSES:
                raise DomainValidationError(
                    f"Dependency {dependency_id} is not valid for downstream execution."
                )
            if dependency.run_id is None or dependency.output_payload is None:
                raise DomainValidationError(
                    f"Dependency {dependency_id} has no latest valid Run output."
                )
            upstream_outputs[dependency_id] = dependency.output_payload
            source_refs.update(dependency.source_refs)
            precedent_refs.update(dependency.internal_precedent_refs)
            source_authorities.update(dependency.source_authorities)
            dependency_run_ids.append(dependency.run_id)
        return DependencyContext(
            upstream_outputs=upstream_outputs,
            source_refs=frozenset(source_refs),
            internal_precedent_refs=frozenset(precedent_refs),
            source_authorities=source_authorities,
            dependency_run_ids=tuple(dependency_run_ids),
        )
