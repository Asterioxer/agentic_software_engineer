from __future__ import annotations

import logging
import os

from .base import ExecutionSandbox
from .docker import DockerSandbox
from .local import LocalSubprocessSandbox

logger = logging.getLogger("agent.sandbox")


def get_default_sandbox(prefer_container: bool | None = None) -> ExecutionSandbox:
    """Resolve the default sandbox based on configuration and host environment.

    By default, checks AGENT_SANDBOX_CONTAINER environment variable. If set or prefer_container=True,
    attempts to use DockerSandbox if Docker is available. Falls back gracefully to LocalSubprocessSandbox.
    """
    should_prefer = prefer_container
    if should_prefer is None:
        should_prefer = os.environ.get("AGENT_SANDBOX_CONTAINER", "").lower() in (
            "1",
            "true",
            "yes",
        )

    if should_prefer:
        docker_box = DockerSandbox()
        if docker_box.is_available():
            logger.info("Using containerized DockerSandbox for OS-level execution isolation.")
            return docker_box
        logger.warning(
            "Container sandbox requested but Docker is unavailable. Falling back to LocalSubprocessSandbox."
        )

    return LocalSubprocessSandbox()
