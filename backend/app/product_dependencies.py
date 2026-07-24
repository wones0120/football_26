"""FastAPI dependency providers."""

from functools import lru_cache

from Database import NFLIngestionController, NFLDataSource

from .product_services.optimizer import OptimizerService
from .product_services.news_monitor import NewsMonitorService
from .product_services.ownership import OwnershipService
from .product_services.batch_import import DraftKingsBatchImportService
from .product_services.portfolio import PortfolioService
from .product_services.draftkings_export import DraftKingsExportService
from .product_services.slate import SlateDataService
from .product_services.predictions import PredictionsService
from .product_services.replay import ClassicCashStackReplayService
from .product_services.readiness import SlateReadinessService
from .product_services.data_quality import DataQualityService
from .product_services.beliefs import BeliefService
from .product_services.belief_impacts import BeliefImpactService
from .product_services.digital_twin_variants import DigitalTwinVariantService
from .product_services.thought_inbox import ThoughtInboxService
from .product_services.starters import StartingQBService
from .product_services.simulations import SimulationService


@lru_cache()
def get_ingestion_controller() -> NFLIngestionController:
    return NFLIngestionController()


@lru_cache()
def get_optimizer_service() -> OptimizerService:
    return OptimizerService()


@lru_cache()
def get_simulation_service() -> SimulationService:
    return SimulationService()


@lru_cache()
def get_classic_cash_stack_replay_service() -> ClassicCashStackReplayService:
    return ClassicCashStackReplayService()


@lru_cache()
def get_slate_readiness_service() -> SlateReadinessService:
    return SlateReadinessService()


@lru_cache()
def get_data_quality_service() -> DataQualityService:
    return DataQualityService()


@lru_cache()
def get_belief_service() -> BeliefService:
    return BeliefService()


@lru_cache()
def get_belief_impact_service() -> BeliefImpactService:
    return BeliefImpactService()


@lru_cache()
def get_digital_twin_variant_service() -> DigitalTwinVariantService:
    return DigitalTwinVariantService()


@lru_cache()
def get_thought_inbox_service() -> ThoughtInboxService:
    return ThoughtInboxService()


@lru_cache()
def get_slate_service() -> SlateDataService:
    return SlateDataService()


@lru_cache()
def get_data_source() -> NFLDataSource:
    return NFLDataSource()


@lru_cache()
def get_predictions_service() -> PredictionsService:
    return PredictionsService()


@lru_cache()
def get_starting_qb_service() -> StartingQBService:
    return StartingQBService()


@lru_cache()
def get_ownership_service() -> OwnershipService:
    return OwnershipService()


@lru_cache()
def get_batch_import_service() -> DraftKingsBatchImportService:
    return DraftKingsBatchImportService()


@lru_cache()
def get_portfolio_service() -> PortfolioService:
    return PortfolioService()


@lru_cache()
def get_draftkings_export_service() -> DraftKingsExportService:
    return DraftKingsExportService()


@lru_cache()
def get_news_monitor_service() -> NewsMonitorService:
    return NewsMonitorService()
