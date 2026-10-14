"""The Campus Customs Multi-Agent Operations team: one module per role."""

from . import accounting, boss, customer_service, facilities, inventory  # noqa: F401  (registers each agent)
from .base import REGISTRY, run_agent

__all__ = ["REGISTRY", "run_agent"]
