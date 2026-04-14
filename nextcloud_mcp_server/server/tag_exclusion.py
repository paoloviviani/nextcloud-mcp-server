"""Tag-based file exclusion for MCP file operations.

Resolves configured EXCLUDED_TAGS to a set of file paths that should be
hidden from MCP tools (list, read, search).  Uses Nextcloud's systemtags
WebDAV API: for each excluded tag name -> resolve tag ID -> fetch tagged
file paths via REPORT.

Tagging a **folder** excludes the folder itself *and* everything inside it
(recursive exclusion via path-prefix matching).
"""

import logging

from nextcloud_mcp_server.client.webdav import WebDAVClient
from nextcloud_mcp_server.config import get_settings

logger = logging.getLogger(__name__)


def get_excluded_tag_names() -> list[str]:
    """Return the list of excluded tag names from configuration."""
    settings = get_settings()
    raw = settings.excluded_tags
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


async def get_excluded_file_paths(webdav: WebDAVClient) -> set[str]:
    """Collect all file paths that carry an excluded tag.

    For tagged **directories** the normalised directory path is included,
    which causes ``is_path_excluded`` to block every child path as well
    (prefix match on ``<dir>/``).

    Args:
        webdav: An authenticated WebDAVClient instance.

    Returns:
        A set of normalised file paths (no leading/trailing ``/``) that
        should be hidden.
    """
    tag_names = get_excluded_tag_names()
    if not tag_names:
        return set()

    excluded: set[str] = set()

    for tag_name in tag_names:
        tag = await webdav.get_tag_by_name(tag_name)
        if tag is None:
            logger.debug("Excluded tag '%s' does not exist -- skipping", tag_name)
            continue

        files = await webdav.get_files_by_tag(tag["id"])
        for f in files:
            path = _normalise_path(f["path"])
            excluded.add(path)
            if f.get("is_directory"):
                logger.debug(
                    "Excluding directory '%s' (tag '%s') — children will be hidden",
                    path,
                    tag_name,
                )

    if excluded:
        logger.info(
            "Excluding %d path(s) matching tags: %s",
            len(excluded),
            ", ".join(tag_names),
        )

    return excluded


def is_path_excluded(path: str, excluded_paths: set[str]) -> bool:
    """Check whether *path* (or any of its parents) is excluded.

    A path is excluded when:
    - It matches an excluded path exactly, **or**
    - It is a child of an excluded directory (prefix match on ``<dir>/``).
    """
    if not excluded_paths:
        return False
    normalised = _normalise_path(path)
    # Direct match (file or directory itself)
    if normalised in excluded_paths:
        return True
    # Child of an excluded directory
    for exc in excluded_paths:
        if normalised.startswith(exc + "/"):
            return True
    return False


def _normalise_path(path: str) -> str:
    """Strip leading/trailing slashes for consistent comparison."""
    return path.strip("/")
