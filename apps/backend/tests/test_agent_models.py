import pytest
from pydantic import ValidationError

from legal_workbench.agents.models import AgentDefinition, AgentRole


def test_agent_definition_rejects_unbounded_timeout() -> None:
    with pytest.raises(ValidationError):
        AgentDefinition(
            id="contract",
            name="合同 Agent",
            role=AgentRole.PROFESSIONAL,
            description="Contract review",
            version="1.0.0",
            prompt_version="1.0.0",
            input_schema_version="1.0",
            output_schema_version="1.0",
            timeout_seconds=7200,
            max_retries=2,
            concurrency_limit=1,
        )
