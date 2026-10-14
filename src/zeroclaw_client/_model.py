"""The base of every type the gateway sends or accepts, and JSON decoding."""

from __future__ import annotations

from collections.abc import Hashable
from functools import lru_cache
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ._errors import DecodeError

__all__ = ["Model", "decode", "encode"]

T = TypeVar("T")


class Model(BaseModel):
    """A gateway type.

    Fields mirror the gateway's JSON names. Unknown fields from a newer
    gateway are ignored; optional and newer fields default to ``None``, so an
    older gateway still decodes.
    """

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())


@lru_cache(maxsize=512)
def _adapter(tp: Any) -> TypeAdapter[Any]:
    return TypeAdapter(tp)


def decode(data: Any, tp: type[T]) -> T:
    """Validate decoded JSON ``data`` as ``tp``, raising :class:`DecodeError`."""
    try:
        result: T = _adapter(cast(Hashable, tp)).validate_python(data)
    except ValidationError as exc:
        raise DecodeError(f"unexpected gateway response: {exc}") from exc
    return result


def encode(value: Any) -> Any:
    """Turn a request body into JSON-ready data: models drop their unset (``None``) fields."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [encode(v) for v in value]
    return value
