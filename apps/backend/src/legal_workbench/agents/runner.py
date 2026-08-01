import structlog

from legal_workbench.config import get_settings

logger = structlog.get_logger(__name__)


def main() -> None:
    settings = get_settings()
    if not settings.enable_real_codex:
        logger.warning(
            "codex_runner_disabled",
            reason="Set LEGAL_WORKBENCH_ENABLE_REAL_CODEX=true only after runner implementation and review.",
        )
        return

    raise NotImplementedError("Codex runner execution loop is not implemented yet.")


if __name__ == "__main__":
    main()
