"""Immutable source facts, immutable rule versions, simulations and execution ledger."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    blob_path: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    as_of: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="preview")
    mapping: Mapped[dict] = mapped_column(JSON)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    reconciliation: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceRow(Base):
    __tablename__ = "source_rows"
    __table_args__ = (UniqueConstraint("snapshot_id", "row_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSON)
    facts: Mapped[dict] = mapped_column(JSON)


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("rule_versions.id"))
    name: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(20), default="draft")
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    sales_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshots.id"))
    rule_id: Mapped[int] = mapped_column(ForeignKey("rule_versions.id"))
    status: Mapped[str] = mapped_column(String(30))
    assumptions: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    comparison: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Transfer(Base):
    __tablename__ = "transfers"
    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id"))
    group_key: Mapped[str] = mapped_column(String(255))
    labels: Mapped[list] = mapped_column(JSON)
    route: Mapped[list] = mapped_column(JSON)
    purpose: Mapped[str] = mapped_column(String(30))
    leg: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="proposed")


class MovementEvent(Base):
    __tablename__ = "movement_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfers.id"))
    action: Mapped[str] = mapped_column(String(20))
    leg: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(160))
    actor: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(160))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
