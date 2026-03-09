"""Utility functions for SSL handling."""

import logging
import ssl

logger = logging.getLogger("streamrip")

try:
    import certifi

    HAS_CERTIFI = True
except ImportError:
    logger.debug("certifi not found, falling back to system certificates")
    HAS_CERTIFI = False


def get_aiohttp_connector_kwargs(verify_ssl=True):
    """Get keyword arguments for aiohttp.TCPConnector with SSL settings."""
    if not verify_ssl:
        return {"verify_ssl": False}

    if HAS_CERTIFI:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        return {"ssl": ssl_context}
    else:
        return {"verify_ssl": True}
