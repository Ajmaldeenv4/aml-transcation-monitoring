"""SHAP-based explainability: turn model output into analyst-readable reasons."""

from __future__ import annotations

import numpy as np

# Human phrasing for each feature when it pushes risk UP.
_PHRASES = {
    "severity_ord": "high rule severity",
    "num_triggering_txns": "many triggering transactions",
    "total_amount": "large total value",
    "max_amount": "large single transaction",
    "mean_amount": "high average transaction value",
    "entity_txn_count": "high overall account activity",
    "entity_total_volume": "high account volume",
    "entity_cross_border_ratio": "frequent cross-border activity",
    "high_risk_geo_hits": "exposure to high-risk jurisdictions",
    "cash_ratio": "predominantly cash transactions",
    "round_amount_ratio": "round-value transfers",
    "first_txn_hour": "unusual transaction timing",
}


def build_reasons(
    model, x: np.ndarray, feature_names: list[str], top_k: int = 3
) -> list[list[str]]:
    """Return the top-k risk-increasing feature reasons for each row.

    Uses SHAP if available; falls back to model feature_importances_ weighting so
    scoring never hard-fails on a SHAP/runtime quirk.
    """
    try:
        import shap

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(x)
        values = _normalise_shap(shap_values)
    except Exception:
        # Fallback: weight standardised features by global importance.
        importances = getattr(model, "feature_importances_", np.ones(x.shape[1]))
        col_mean = x.mean(axis=0)
        values = (x - col_mean) * importances

    reasons: list[list[str]] = []
    for row in values:
        order = np.argsort(row)[::-1]  # most positive contribution first
        picked: list[str] = []
        for idx in order:
            if row[idx] <= 0:
                break
            name = feature_names[idx]
            phrase = _PHRASES.get(name)
            if phrase is None and name.startswith("typology_"):
                phrase = f"{name.removeprefix('typology_').replace('_', ' ')} typology"
            if phrase and phrase not in picked:
                picked.append(phrase)
            if len(picked) >= top_k:
                break
        reasons.append(picked or ["model risk indicators"])
    return reasons


def _normalise_shap(shap_values) -> np.ndarray:
    """SHAP returns various shapes across versions; coerce to (n_samples, n_features)."""
    arr = np.asarray(shap_values)
    if arr.ndim == 3:  # (n_classes, n_samples, n_features) or (n_samples, n_features, n_classes)
        # Take the positive class.
        if arr.shape[0] == 2:
            return arr[1]
        return arr[..., -1]
    return arr
