# agent/__init__.py
# Financial Crime Investigation Agent — Package Initialization
#
# This package implements a LangGraph-based multi-step investigation workflow
# that mirrors the process used by Financial Crimes Units (FCUs) at major banks.
#
# Regulatory basis: Bank Secrecy Act (BSA), 31 U.S.C. § 5318
# FinCEN guidance: FIN-2014-G001, SAR Activity Review publications
# FATF Recommendation 20: Reporting of suspicious transactions

from agent.graph import build_investigation_graph
from agent.state import InvestigationState

__all__ = ["build_investigation_graph", "InvestigationState"]
