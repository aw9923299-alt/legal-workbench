from __future__ import annotations

from copy import deepcopy
from datetime import date

from pydantic import BaseModel

from legal_workbench.agents.definitions import (
    MESSAGE_JUDGEMENT_KEY,
    build_legal_agent_definitions,
    build_message_judgement_definition,
)
from legal_workbench.agents.legal_butler import (
    ButlerPlanningOutput,
    ButlerSynthesisOutput,
    validate_butler_synthesis_sources,
)
from legal_workbench.agents.legal_contracts import (
    LEGAL_OUTPUT_MODELS,
    LegalAgentInput,
    validate_legal_work_product_sources,
)
from legal_workbench.agents.message_judgement import (
    MessageJudgementInput,
    MessageJudgementResult,
    validate_confirmed_fact_sources,
    validate_message_judgement_business_rules,
)
from legal_workbench.agents.runtime import AgentExecutionContext
from legal_workbench.domain.entities import AgentDefinition, AgentRun
from legal_workbench.domain.errors import DomainValidationError


def _context_integer(value: object, *, default: int | None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


class LegalAgentContractRegistry:
    """Select and enforce the persisted contract for the existing Codex Runtime."""

    def __init__(self) -> None:
        self._legal_definitions = build_legal_agent_definitions()

    def validate_definition(self, definition: AgentDefinition) -> None:
        expected: AgentDefinition | None
        if definition.key == MESSAGE_JUDGEMENT_KEY:
            expected = build_message_judgement_definition(
                timeout_seconds=definition.timeout_seconds
            )
        else:
            expected = self._legal_definitions.get(definition.key)
        if expected is None or (
            definition.version != expected.version
            or definition.input_schema != expected.input_schema
            or definition.output_schema != expected.output_schema
        ):
            raise DomainValidationError("Agent schemas do not match a registered Runtime contract.")

    def prepare_input(
        self,
        definition: AgentDefinition,
        run: AgentRun,
        context: AgentExecutionContext,
    ) -> dict[str, object]:
        if definition.key != MESSAGE_JUDGEMENT_KEY:
            if context.input_payload is None:
                raise DomainValidationError(
                    "Legal Agent execution requires a deterministically prepared input payload."
                )
            return LegalAgentInput.model_validate(context.input_payload).model_dump(
                by_alias=True, mode="json"
            )
        payload: dict[str, object] = {
            "runId": str(run.id),
            "agentDefinition": {"key": definition.key, "version": definition.version},
            "objective": run.objective,
            "contextSnapshot": {
                "id": str(context.snapshot.id),
                "contentHash": context.snapshot.content_hash,
                "messageIds": context.snapshot.message_ids,
                "participantIds": context.snapshot.participant_ids,
                "attachmentIds": context.snapshot.attachment_ids,
                "includedSegments": context.snapshot.included_segments,
                "excludedSegments": context.snapshot.excluded_segments,
                "threadMetadata": context.snapshot.thread_metadata,
                "content": context.snapshot.content,
                "builderVersion": context.snapshot.builder_version,
                "selectionPolicyVersion": context.snapshot.selection_policy_version,
                "currentMessageVersion": context.snapshot.current_message_version,
                "attachmentVersionHash": context.snapshot.attachment_version_hash,
                "truncated": context.snapshot.truncated,
                "truncationReason": context.snapshot.truncation_reason,
                "originalSize": context.snapshot.original_size,
                "includedSize": context.snapshot.included_size,
            },
            "constraints": {
                "networkAccess": False,
                "databaseAccess": False,
                "repositoryAccess": False,
                "shellWriteAccess": False,
                "allowedMessageIds": context.snapshot.message_ids,
                "allowedAttachmentIds": [
                    str(value.get("attachmentId"))
                    for value in context.snapshot.included_segments
                    if value.get("attachmentId")
                ],
            },
        }
        return MessageJudgementInput.model_validate(payload).model_dump(by_alias=True, mode="json")

    def runtime_output_schema(
        self,
        definition: AgentDefinition,
        context: AgentExecutionContext,
    ) -> dict[str, object]:
        """Select one strict Butler phase schema because Codex forbids root oneOf."""

        if definition.key != "legal_butler":
            return deepcopy(definition.output_schema)
        phase = None if context.input_payload is None else context.input_payload.get("phase")
        variants = definition.output_schema.get("oneOf")
        if phase not in {"planning", "synthesis"} or not isinstance(variants, list):
            raise DomainValidationError("Butler runtime phase schema is unavailable.")
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            properties = variant.get("properties")
            if not isinstance(properties, dict):
                continue
            phase_schema = properties.get("phase")
            if isinstance(phase_schema, dict) and phase_schema.get("const") == phase:
                return deepcopy(variant)
        raise DomainValidationError("Butler runtime phase does not match a registered schema.")

    def validate_output(
        self,
        definition: AgentDefinition,
        payload: object,
        context: AgentExecutionContext,
    ) -> BaseModel:
        if definition.key == MESSAGE_JUDGEMENT_KEY:
            result = MessageJudgementResult.model_validate(payload)
            citations = {
                (
                    str(value.get("attachmentId") or ""),
                    str(value.get("fileName") or ""),
                    _context_integer(value.get("pageNumber"), default=None),
                    _context_integer(value.get("paragraphNumber"), default=0) or 0,
                    str(value.get("contentHash") or ""),
                )
                for value in context.snapshot.included_segments
            }
            validate_confirmed_fact_sources(
                result,
                set(context.snapshot.message_ids),
                citations,
            )
            validate_message_judgement_business_rules(result)
            return result
        if definition.key == "legal_butler":
            phase = None if context.input_payload is None else context.input_payload.get("phase")
            if phase == "planning":
                return ButlerPlanningOutput.model_validate(payload)
            if phase == "synthesis":
                synthesis_result = ButlerSynthesisOutput.model_validate(payload)
                analysis_context = (
                    context.input_payload.get("authorizedContext", {})
                    if context.input_payload is not None
                    else {}
                )
                if not isinstance(analysis_context, dict):
                    analysis_context = {}
                historical_value = analysis_context.get("analysisHistoricalAsOf")
                historical_as_of = (
                    date.fromisoformat(historical_value)
                    if isinstance(historical_value, str) and historical_value
                    else None
                )
                synthesis_result = validate_butler_synthesis_sources(
                    synthesis_result,
                    authorized_source_refs=set(context.authorized_source_refs),
                    internal_precedent_refs=set(context.internal_precedent_refs),
                    source_metadata=context.source_authorities,
                    analysis_jurisdiction=str(
                        analysis_context.get("analysisJurisdiction") or ""
                    )
                    or None,
                    historical_as_of=historical_as_of,
                )
                return synthesis_result
            raise DomainValidationError("Butler input phase must be planning or synthesis.")
        output_model = LEGAL_OUTPUT_MODELS.get(definition.key)
        if output_model is None:
            raise DomainValidationError("Agent is not registered for structured legal output.")
        specialist_result = output_model.model_validate(payload)
        analysis_context = (
            context.input_payload.get("authorizedContext", {})
            if context.input_payload is not None
            else {}
        )
        if not isinstance(analysis_context, dict):
            analysis_context = {}
        effective_value = analysis_context.get("analysisEffectiveDate")
        historical_value = analysis_context.get("analysisHistoricalAsOf")
        validate_legal_work_product_sources(
            specialist_result,
            authorized_source_refs=set(context.authorized_source_refs),
            internal_precedent_refs=set(context.internal_precedent_refs),
            source_authorities=context.source_authorities,
            analysis_effective_date=(
                date.fromisoformat(effective_value)
                if isinstance(effective_value, str) and effective_value
                else None
            ),
            historical_as_of=(
                date.fromisoformat(historical_value)
                if isinstance(historical_value, str) and historical_value
                else None
            ),
        )
        return specialist_result
