"""ML risk-scoring layer: feature engineering, a gradient-boosting classifier,
SHAP explainability, and honest false-positive-reduction evaluation.

The ML layer *ranks* the rules-generated alert queue by risk — it never replaces
the rules or the mandatory human disposition. See PROJECT_BRIEF §6.3.
"""

from sentinel.scoring.features import FEATURE_NAMES, alert_label, build_feature_row
from sentinel.scoring.model import (
    DEFAULT_MODEL_PATH,
    load_model,
    score_alerts,
    train_model,
)

__all__ = [
    "FEATURE_NAMES",
    "alert_label",
    "build_feature_row",
    "train_model",
    "load_model",
    "score_alerts",
    "DEFAULT_MODEL_PATH",
]
