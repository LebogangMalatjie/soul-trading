"""News Event Bias Engine (additive, confirm-gated).

A parallel, opt-in path around high-impact economic events. It never trades
until the user clicks CONFIRM in the dashboard, and the global kill switch
overrides everything here. Purely additive: it does not modify the existing
technical strategies, trailing stops, or the legacy news front-running path.
"""
from __future__ import annotations
