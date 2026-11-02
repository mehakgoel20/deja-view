"""AI remediation engine (feature 6).

Proposes immediate, corrective, preventive and configuration actions, drawing
first on what actually fixed similar incidents in the gold set, then on
mechanism playbooks, then on the model.

Execution stays human: every action carries requires_approval, and this module
has no apply path at all. `approve()` only records a decision for audit.

    from remediation import build_plan, approve
    plan = build_plan(text, cause=cause, neighbours=nb, use_llm=False)
    approve(plan, 0, approver="mehak", decision="approved")
"""
from .engine import (HORIZON_CONFIG, HORIZON_CORRECTIVE, HORIZON_IMMEDIATE,
                     HORIZON_PREVENTIVE, PLAYBOOKS, RISK_HIGH, RISK_LOW,
                     RISK_MEDIUM, Action, approve, build_plan)

__all__ = ["build_plan", "approve", "Action", "PLAYBOOKS",
           "HORIZON_IMMEDIATE", "HORIZON_CORRECTIVE", "HORIZON_PREVENTIVE",
           "HORIZON_CONFIG", "RISK_LOW", "RISK_MEDIUM", "RISK_HIGH"]
