# services/__init__.py
from .statement_service import process_uploaded_statement, validate_upload
from .categorization_service import (
    normalize_payee,
    get_amount_bucket,
    extract_features,
    generate_synthetic_dataset,
    train_model,
    get_or_load_model,
    route_status_from_confidence,
    categorize_transaction,
    categorize_transactions,
    CATEGORIES,
    MODEL_PATH,
)

from .forecasting_service import (
    forecast_daily_spending,
    calculate_cash_flow_runway,
    simulate_whatif_adjustments,
)

from .goal_service import (
    calculate_goal_metrics,
    contribute_to_goal,
    check_goal_progress_and_suggest_cut,
    TRIMMABLE_CATEGORIES,
)

__all__ = [
    "process_uploaded_statement",
    "validate_upload",
    "normalize_payee",
    "get_amount_bucket",
    "extract_features",
    "generate_synthetic_dataset",
    "train_model",
    "get_or_load_model",
    "route_status_from_confidence",
    "categorize_transaction",
    "categorize_transactions",
    "CATEGORIES",
    "MODEL_PATH",
    "forecast_daily_spending",
    "calculate_cash_flow_runway",
    "simulate_whatif_adjustments",
    "calculate_goal_metrics",
    "contribute_to_goal",
    "check_goal_progress_and_suggest_cut",
    "TRIMMABLE_CATEGORIES",
]
