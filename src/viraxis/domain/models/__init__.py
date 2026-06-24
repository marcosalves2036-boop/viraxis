"""Domain models — importar aqui garante que Base.metadata veja todos os models."""

from viraxis.domain.models.user import User
from viraxis.domain.models.office import Office
from viraxis.domain.models.niche_profile import NicheProfile
from viraxis.domain.models.content_decision import ContentDecision
from viraxis.domain.models.content_item import ContentItem
from viraxis.domain.models.trend_snapshot import TrendSnapshot
from viraxis.domain.models.social_account import SocialAccount
from viraxis.domain.models.performance_metric import PerformanceMetric
from viraxis.domain.models.agent_run_log import AgentRunLog
from viraxis.domain.models.raw_video import RawVideo

__all__ = [
    "User",
    "Office",
    "NicheProfile",
    "ContentDecision",
    "ContentItem",
    "TrendSnapshot",
    "SocialAccount",
    "PerformanceMetric",
    "AgentRunLog",
    "RawVideo",
]
