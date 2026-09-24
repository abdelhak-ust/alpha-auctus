"""Entity — a feature/area/component the project talks about; drives area tagging and, in
later phases, impact reasoning (architecture.md's "Core data model"). Minimal this pass: just
enough for ingestion to tag extracted items/decisions consistently.
"""

from sqlalchemy import ARRAY, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
