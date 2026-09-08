"""Supplier-risk engine (SKY-86 / INV-AI-004).

Slice layout: ``loader`` pulls the supplier master + performance facts from
core over its inventory REST API, ``scorer`` is the pure deterministic risk
formula (weighted risk dimensions -> 0-1 score -> low|medium|high band ->
confidence + human-readable reason), ``service`` orchestrates compute+upsert,
and ``db.supplier_risk_repository`` persists the grade into ai_supplier_risk.
The band feeds the v2 restock lead-time adjustment. Pure computation - NO LLM.
"""
