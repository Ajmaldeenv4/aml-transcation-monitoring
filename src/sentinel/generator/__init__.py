"""Synthetic transaction generator.

Produces documented, reproducible supplementary transactions so every typology in
PROJECT_BRIEF §3 has positive cases, plus benign noise. Ground-truth labels are
retained on the laundering transactions for honest ML evaluation.
"""

from sentinel.generator.generate import generate_dataset

__all__ = ["generate_dataset"]
