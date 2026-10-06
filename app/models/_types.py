"""Shared column types for ORM models."""
from __future__ import annotations

import enum

from sqlalchemy import Enum


def str_enum(enum_cls: type[enum.Enum], length: int = 40) -> Enum:
    """
    Stores a Python str-Enum as a plain VARCHAR of its *values* rather than a
    native Postgres ENUM type — state machines like the order FSM gain states
    over time, and VARCHAR avoids painful `ALTER TYPE ... ADD VALUE` migrations.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
