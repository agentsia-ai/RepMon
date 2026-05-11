"""IMAP polling stub for DMARC aggregate attachments.

Deployments implement mailbox-specific fetch; this module documents the
intended hook: poll `monitoring.dmarc_report_inbox`, unzip/gzip attachments,
then call `repmon.sources.dmarc_parser.ingest_report_file`.
"""

from __future__ import annotations

import logging

from repmon.config.loader import RepMonConfig

logger = logging.getLogger(__name__)


async def poll_dmarc_inbox_stub(config: RepMonConfig) -> None:
    """No-op placeholder — wire aiosmtplib/IMAP in your deployment."""
    if not config.monitoring.dmarc_report_inbox:
        return
    logger.debug(
        "dmarc_email_fetcher: would poll inbox %s (not implemented in engine)",
        config.monitoring.dmarc_report_inbox,
    )
