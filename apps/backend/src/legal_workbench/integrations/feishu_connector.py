import structlog

from legal_workbench.config import get_settings

logger = structlog.get_logger(__name__)


def main() -> None:
    settings = get_settings()
    if not settings.enable_real_feishu:
        logger.warning(
            "feishu_connector_disabled",
            reason=(
                "The connector profile is scaffolding only; "
                "real event intake is not implemented."
            ),
        )
        return

    raise NotImplementedError("Feishu connector event loop is not implemented yet.")


if __name__ == "__main__":
    main()
