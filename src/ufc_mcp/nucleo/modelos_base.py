"""Camada de compatibilidade de modelos Pydantic usada por todo o projeto.

O projeto requer Pydantic v2 (`pydantic>=2.7`), então este módulo apenas
reexporta a API oficial. O `ConfigDict` mantém `validate_by_name=True` como
padrão para aceitar tanto nomes de campo quanto aliases.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict, Field


class BaseModel(_PydanticBaseModel):
    """BaseModel do projeto: aceita nomes de campo e aliases por padrão."""

    model_config: ClassVar[ConfigDict] = ConfigDict(validate_by_name=True)


__all__ = ["BaseModel", "ConfigDict", "Field"]
