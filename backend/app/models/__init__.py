"""ORM models.

Full set per architecture.md "Core data model": Item, TaskContract, DecisionRecord, Entity,
Agent, Edge, Verdict — filled in phase by phase (P1 Task Contract, P2-P8 add Run/
Review/RequirementCoverage/Delivery/PR/registry profiles/ChangeProposal/AuditLog).

P6 (ingestion, plans/ingestion.md) adds the first real models: Source, Chunk, Entity,
DecisionRecord, IngestCandidate. Every model must be imported here (not just defined in its
own file) so `from app.models import *` in migrations/env.py registers it on Base.metadata —
otherwise Alembic autogenerate silently won't see it.
"""

from app.models.decision_record import DecisionRecord
from app.models.entity import Entity
from app.models.ingest_candidate import IngestCandidate
from app.models.source import Chunk, Source

__all__ = ["Source", "Chunk", "Entity", "DecisionRecord", "IngestCandidate"]
