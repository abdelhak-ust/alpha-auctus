"""Requirement-validation engine (hero #2, the wedge) — de-risk first.

Compares requirement <-> implementation (diff) <-> tests to produce
per-requirement coverage (met/partial/unmet/off-task/unverifiable) with dual
citations (code + requirement), plus the evidence-stack (CI test mapped to
each AC). This is the single biggest new backend dependency (ui_ux_design.md
§14) and phase P2 in the plan.
"""
