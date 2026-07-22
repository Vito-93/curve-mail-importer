import imaplib
import logging
import signal
import sys
import time

from pathlib import Path

from curve_importer.batch import process_batch
from curve_importer.config import Settings
from curve_importer.destinations import load_destination_config
from curve_importer.firefly import FireflyClient
from curve_importer.imap import ImapGateway
from curve_importer.parser import CurveParseError, parse_curve_email

logger = logging.getLogger("curve_importer")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s, shutting down...", signum)
    _shutdown = True


_destinations = None


def _poll_once(imap: ImapGateway, firefly: FireflyClient, settings: Settings) -> None:
    emails = imap.fetch_unseen(settings.imap_folder)
    if not emails:
        logger.debug("No unseen emails")
        return

    receipts = []
    processed_uids = []
    for raw in emails:
        try:
            receipt = parse_curve_email(raw.body)
            receipts.append(receipt)
            processed_uids.append(raw.uid)
        except CurveParseError as e:
            logger.warning("Skipping email (subject=%r): %s", raw.subject, e)
            processed_uids.append(raw.uid)

    if receipts:
        result = process_batch(receipts, firefly, settings.firefly_source_account, _destinations)
        logger.info(
            "Batch: created=%d updated=%d skipped=%d errors=%d",
            result.created, result.updated, result.skipped, result.errors,
        )

    if processed_uids:
        imap.mark_seen(processed_uids)


def main() -> None:
    settings = Settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    firefly = FireflyClient(
        base_url=settings.firefly_base_url,
        access_token=settings.firefly_access_token,
    )
    imap = ImapGateway(
        host=settings.imap_host,
        port=settings.imap_port,
        user=settings.imap_user,
        password=settings.imap_password,
    )

    global _destinations
    _destinations = load_destination_config(Path(settings.destination_rules_path))
    logger.info(
        "Starting curve-mail-importer (poll every %ds, %d destination rules, default=%s)",
        settings.poll_interval_seconds, len(_destinations.rules), _destinations.default,
    )

    try:
        imap.connect()
        while not _shutdown:
            try:
                _poll_once(imap, firefly, settings)
            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as e:
                logger.warning("Connection lost (%s), will reconnect", e)
                try:
                    imap.reconnect()
                except Exception:
                    logger.exception("Reconnect failed, will retry next cycle")
            except Exception:
                logger.exception("Error during poll cycle")
            for _ in range(settings.poll_interval_seconds):
                if _shutdown:
                    break
                time.sleep(1)
    finally:
        imap.disconnect()
        firefly.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
