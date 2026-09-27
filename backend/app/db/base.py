"""Declarative base for all ORM models.

P1+ models (Item / TaskContract / DecisionRecord / Entity / Agent / Edge /
Verdict — see architecture.md "Core data model") import `Base` from here so
Alembic autogenerate can discover them via app.db.base.metadata.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
