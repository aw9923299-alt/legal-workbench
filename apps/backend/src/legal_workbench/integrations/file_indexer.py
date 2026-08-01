import structlog

logger = structlog.get_logger(__name__)


def main() -> None:
    logger.warning(
        "file_indexer_not_implemented",
        reason="Document parsing and indexing will be implemented after metadata and retention policies.",
    )


if __name__ == "__main__":
    main()
