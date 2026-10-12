"""
TimescaleDB Persistence Layer
===============================
Stores per-timestep output records in a TimescaleDB hypertable for
durable historical storage.  Historical API queries read from here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Text,
    create_engine,
    text,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings
from src.p2p.models import MARKET_OPTIONAL_FIELDS
from src.monitoring.temperature import TEMPERATURE_OPTIONAL_FIELDS

OPTIONAL_FIELDS = MARKET_OPTIONAL_FIELDS + TEMPERATURE_OPTIONAL_FIELDS

logger = logging.getLogger(__name__)


# -- SQLAlchemy ORM -----------------------------------------------------------

class Base(DeclarativeBase):
    pass


class OutputRecordRow(Base):
    """Maps to the ``output_records`` hypertable in TimescaleDB."""

    __tablename__ = "output_records"

    timestamp = Column(String, primary_key=True)
    coverage_ratio = Column(Float, nullable=False)
    coverage_status = Column(String(10), nullable=False)
    active_actions = Column(Text, nullable=False, default="")
    tier_1_protected = Column(Boolean, nullable=False)
    battery_soc = Column(Float, nullable=False)
    grid_power = Column(Float, nullable=False)
    p2p_energy = Column(Float, nullable=False)
    anomaly_flag = Column(Boolean, nullable=False)
    anomaly_source = Column(String, nullable=True)
    scenario_label = Column(String, nullable=False, default="normal", primary_key=True)
    p2p_import = Column(Float, nullable=True)
    p2p_export = Column(Float, nullable=True)
    p2p_trades = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    p2p_savings = Column(Float, nullable=True)
    cost = Column(Float, nullable=True)
    revenue = Column(Float, nullable=True)
    energy_price = Column(Float, nullable=True)
    sell_price = Column(Float, nullable=True)
    p2p_price = Column(Float, nullable=True)
    temperatures = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    temperature_alerts = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    temperature_status = Column(String(8), nullable=True)
    temperature_limits = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    neighbors = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    demand_kw = Column(Float, nullable=True)
    pv_power = Column(Float, nullable=True)


# -- Engine & init ------------------------------------------------------------

_engine = None
_SessionLocal = None


def get_engine(url: str | None = None):
    """Return (and lazily create) the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(url or settings.timescale_url, pool_pre_ping=True)
    return _engine


def init_db(url: str | None = None) -> None:
    """Create tables (idempotent).  Attempts to enable TimescaleDB
    hypertable if the extension is available, falls back gracefully to
    plain PostgreSQL otherwise."""
    global _SessionLocal
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for name in ("003_p2p.sql", "004_temperature.sql", "005_dashboard.sql"):
                migration = Path(__file__).with_name("migrations") / name
                conn.execute(text(migration.read_text(encoding="utf-8")))
    _SessionLocal = sessionmaker(bind=engine)

    # Try to make the table a hypertable (no-op if already done or if
    # the timescaledb extension isn't loaded).
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            conn.execute(
                text(
                    "SELECT create_hypertable('output_records', 'timestamp', "
                    "if_not_exists => TRUE)"
                )
            )
            conn.commit()
        logger.info("TimescaleDB hypertable created/verified.")
    except Exception as exc:
        logger.warning("Hypertable setup skipped (non-fatal): %s", exc)


def get_session() -> Session:
    """Return a new DB session."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


# -- Store class ---------------------------------------------------------------

class TimescaleStore:
    """Read/write helpers for the output_records hypertable."""

    def __init__(self, url: str | None = None) -> None:
        init_db(url)

    def write_record(self, record_dict: dict, scenario_label: str = "normal") -> None:
        """Persist one output record."""
        session = get_session()
        try:
            row = OutputRecordRow(
                timestamp=record_dict["timestamp"],
                coverage_ratio=record_dict["coverage_ratio"],
                coverage_status=record_dict["coverage_status"],
                active_actions=json.dumps(record_dict.get("active_actions", [])),
                tier_1_protected=record_dict["tier_1_protected"],
                battery_soc=record_dict["battery_soc"],
                grid_power=record_dict["grid_power"],
                p2p_energy=record_dict["p2p_energy"],
                anomaly_flag=record_dict["anomaly_flag"],
                anomaly_source=record_dict.get("anomaly_source"),
                scenario_label=scenario_label,
                **{key: record_dict.get(key) for key in OPTIONAL_FIELDS},
            )
            session.merge(row)  # upsert
            session.commit()
        finally:
            session.close()

    def write_records_bulk(
        self, records: list[dict], scenario_label: str = "normal"
    ) -> int:
        """Bulk-insert a list of output records.  Returns count written."""
        session = get_session()
        try:
            for rec in records:
                row = OutputRecordRow(
                    timestamp=rec["timestamp"],
                    coverage_ratio=rec["coverage_ratio"],
                    coverage_status=rec["coverage_status"],
                    active_actions=json.dumps(rec.get("active_actions", [])),
                    tier_1_protected=rec["tier_1_protected"],
                    battery_soc=rec["battery_soc"],
                    grid_power=rec["grid_power"],
                    p2p_energy=rec["p2p_energy"],
                    anomaly_flag=rec["anomaly_flag"],
                    anomaly_source=rec.get("anomaly_source"),
                    scenario_label=scenario_label,
                    **{key: rec.get(key) for key in OPTIONAL_FIELDS},
                )
                session.merge(row)
            session.commit()
            return len(records)
        finally:
            session.close()

    def query_range(
        self,
        start: str,
        end: str,
        scenario_label: str = "normal",
    ) -> list[dict]:
        """Query records in a time range, returns list of dicts."""
        session = get_session()
        try:
            rows = (
                session.query(OutputRecordRow)
                .filter(
                    OutputRecordRow.timestamp >= start,
                    OutputRecordRow.timestamp <= end,
                    OutputRecordRow.scenario_label == scenario_label,
                )
                .order_by(OutputRecordRow.timestamp)
                .all()
            )
            return [self._row_to_dict(r) for r in rows]
        finally:
            session.close()

    def query_latest(self, scenario_label: str = "normal") -> dict | None:
        """Return the most recent record."""
        session = get_session()
        try:
            row = (
                session.query(OutputRecordRow)
                .filter(OutputRecordRow.scenario_label == scenario_label)
                .order_by(OutputRecordRow.timestamp.desc())
                .first()
            )
            return self._row_to_dict(row) if row else None
        finally:
            session.close()

    def query_all(self, scenario_label: str = "normal") -> list[dict]:
        """Return all records for a scenario."""
        session = get_session()
        try:
            rows = (
                session.query(OutputRecordRow)
                .filter(OutputRecordRow.scenario_label == scenario_label)
                .order_by(OutputRecordRow.timestamp)
                .all()
            )
            return [self._row_to_dict(r) for r in rows]
        finally:
            session.close()

    @staticmethod
    def _row_to_dict(row: OutputRecordRow) -> dict:
        return {
            "timestamp": row.timestamp,
            "coverage_ratio": row.coverage_ratio,
            "coverage_status": row.coverage_status,
            "active_actions": json.loads(row.active_actions),
            "tier_1_protected": row.tier_1_protected,
            "battery_soc": row.battery_soc,
            "grid_power": row.grid_power,
            "p2p_energy": row.p2p_energy,
            "anomaly_flag": row.anomaly_flag,
            "anomaly_source": row.anomaly_source,
            **{key: getattr(row, key) for key in OPTIONAL_FIELDS
               if getattr(row, key) is not None},
        }
