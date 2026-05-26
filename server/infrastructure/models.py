"""
SQLAlchemy ORM 表定义（五表）

映射 M2 需求文档 4.3 节的表结构设计：
  - player_account：局外玩家账号
  - dead_registry：死亡因果记录
  - immortal_hall：飞升名人堂
  - active_session：活跃会话快照（断线重连）
  - heaven_overlord_pool：全服怨念候选池
"""

from datetime import datetime

from sqlalchemy import String, Integer, Float, DateTime, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PlayerAccountModel(Base):
    __tablename__ = "player_account"

    player_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    wechat_openid: Mapped[str] = mapped_column(String(64), default="")
    player_name: Mapped[str] = mapped_column(String(64), default="无名修士")
    avatar_url: Mapped[str] = mapped_column(String(256), default="")
    heaven_points: Mapped[int] = mapped_column(Integer, default=0)
    deafness_protocol: Mapped[int] = mapped_column(Integer, default=0)
    karma_shield: Mapped[int] = mapped_column(Integer, default=0)
    pending_sin_reset: Mapped[bool] = mapped_column(Integer, default=0)  # 功德洗白券标记
    talent_bonus: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DeadRegistryModel(Base):
    __tablename__ = "dead_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32))
    player_name: Mapped[str] = mapped_column(String(64))
    realm: Mapped[str] = mapped_column(String(32))
    realm_code: Mapped[int] = mapped_column(Integer)
    dead_title: Mapped[str] = mapped_column(String(256))
    sin_value: Mapped[int] = mapped_column(Integer, default=0)
    survived_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ImmortalHallModel(Base):
    __tablename__ = "immortal_hall"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32))
    player_name: Mapped[str] = mapped_column(String(64))
    ascension_title: Mapped[str] = mapped_column(String(128))
    total_heaven_points: Mapped[int] = mapped_column(Integer, default=0)
    ascended_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LeaderboardEntryModel(Base):
    __tablename__ = "leaderboard_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leaderboard_type: Mapped[str] = mapped_column(String(32))
    player_id: Mapped[str] = mapped_column(String(32))
    player_name: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    score: Mapped[int] = mapped_column(Integer, default=0)
    realm: Mapped[str] = mapped_column(String(32), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class KarmaTraceModel(Base):
    __tablename__ = "karma_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_player_id: Mapped[str] = mapped_column(String(32))
    source_player_name: Mapped[str] = mapped_column(String(64))
    source_run_id: Mapped[str] = mapped_column(String(64), default="")
    trace_type: Mapped[str] = mapped_column(String(16))  # trap / gift
    effect_type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    toxicity_score: Mapped[int] = mapped_column(Integer, default=0)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)
    harm_score: Mapped[int] = mapped_column(Integer, default=0)
    death_caused_count: Mapped[int] = mapped_column(Integer, default=0)
    is_approved: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ActiveSessionModel(Base):
    __tablename__ = "active_session"

    player_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_json: Mapped[str] = mapped_column(JSON)
    stage: Mapped[str] = mapped_column(String(32))
    trigger_json: Mapped[str | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class HeavenOverlordPoolModel(Base):
    __tablename__ = "heaven_overlord_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dead_registry_id: Mapped[int] = mapped_column(Integer)
    player_name: Mapped[str] = mapped_column(String(64))
    dead_title: Mapped[str] = mapped_column(String(256))
    realm_code: Mapped[int] = mapped_column(Integer)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_selected: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
