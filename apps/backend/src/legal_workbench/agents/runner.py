import structlog

from legal_workbench.config import get_settings

logger = structlog.get_logger(__name__)


def main() -> None:
    get_settings()
    logger.warning(
        "standalone_codex_runner_retired",
        reason="Celery feishu.process_message now invokes the controlled CodexCliRuntime.",
    )


if __name__ == "__main__":
    main()
