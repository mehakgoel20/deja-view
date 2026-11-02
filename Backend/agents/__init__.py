"""Multi-agent RCA system (feature 2).

Specialist agents gather evidence concurrently, an investigator judges it, and
a remediation stage proposes fixes:

    from agents import investigate, render
    report = investigate("Checkout 500s since the 13:00 release", use_llm=False)
    print(render(report))

Stage 1 (parallel): log_analysis, metrics_analysis, historical_incident,
dependency_analysis. Stage 2: root_cause_investigator. Stage 3: remediation.
Pass use_llm=False for a fully deterministic run.
"""
from .base import (FINDING_GAP, FINDING_HYPOTHESIS, FINDING_OBSERVATION,
                   FINDING_RECOMMENDATION, Agent, Context, Finding)
from .investigator import RootCauseInvestigator
from .orchestrator import (build_context, default_agents, investigate, render)
from .specialists import (DependencyAgent, HistoricalIncidentAgent,
                          LogAnalysisAgent, MetricsAnalysisAgent)

__all__ = ["investigate", "render", "build_context", "default_agents",
           "Agent", "Context", "Finding", "LogAnalysisAgent",
           "MetricsAnalysisAgent", "HistoricalIncidentAgent",
           "DependencyAgent", "RootCauseInvestigator", "FINDING_OBSERVATION",
           "FINDING_HYPOTHESIS", "FINDING_RECOMMENDATION", "FINDING_GAP"]
