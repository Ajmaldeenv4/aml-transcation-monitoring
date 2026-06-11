"""Shared enumerations expressing AML domain vocabulary."""

from __future__ import annotations

from enum import Enum


class Typology(str, Enum):
    """Money-laundering typologies detected by the rules engine (PROJECT_BRIEF §3).

    Each value is the canonical ``rule_id`` used across alerts, config, and the UI.
    """

    STRUCTURING = "structuring"
    RAPID_MOVEMENT = "rapid_movement"
    ROUND_AMOUNT = "round_amount"
    THRESHOLD_AVOIDANCE = "threshold_avoidance"
    HIGH_RISK_GEOGRAPHY = "high_risk_geography"
    VELOCITY_SPIKE = "velocity_spike"
    NETWORK_RING = "network_ring"

    @property
    def label(self) -> str:
        """Human-readable label for dashboards and SAR narratives."""
        return {
            Typology.STRUCTURING: "Structuring / Smurfing",
            Typology.RAPID_MOVEMENT: "Rapid Movement of Funds (pass-through)",
            Typology.ROUND_AMOUNT: "Round-Amount Layering",
            Typology.THRESHOLD_AVOIDANCE: "Threshold Avoidance",
            Typology.HIGH_RISK_GEOGRAPHY: "High-Risk Geography",
            Typology.VELOCITY_SPIKE: "Velocity Spike",
            Typology.NETWORK_RING: "Network / Mule Ring",
        }[self]
