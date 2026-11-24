"""枚举字典及不可变历史版本（M-05）。"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class EnumDictionary(Base):
    __tablename__ = "enum_dictionary"
    __table_args__ = (CheckConstraint("revision > 0", name="ck_enum_revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    label_i18n: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    definition_i18n: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    entries: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class EnumDictionaryRevision(Base):
    __tablename__ = "enum_dictionary_revision"
    __table_args__ = (CheckConstraint("revision > 0", name="ck_enum_history_revision"),)

    dictionary_id: Mapped[int] = mapped_column(
        ForeignKey("enum_dictionary.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
