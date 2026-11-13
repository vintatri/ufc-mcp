"""Modelos de dados do Restaurante Universitário (RU) da UFC."""

from __future__ import annotations

from ufc_mcp.nucleo.modelos_base import BaseModel, Field

# IDs conforme o menu do site ufc2012.ufc.br/restaurante (Fortaleza é uma única unidade).
RESTAURANTES_UFC: dict[int, dict[str, str]] = {
    1: {"nome": "Restaurante Universitário de Fortaleza", "cidade": "Fortaleza"},
    3: {"nome": "Restaurante Universitário de Russas", "cidade": "Russas"},
    5: {"nome": "Restaurante Universitário de Quixadá", "cidade": "Quixadá"},
    6: {"nome": "Restaurante Universitário de Crateús", "cidade": "Crateús"},
    9: {"nome": "Restaurante Universitário de Sobral", "cidade": "Sobral"},
}

# Pici, Benfica, Porangabuçu e Labomar são refeitórios da unidade Fortaleza, sem cardápio próprio.
UNIDADES_RU: dict[str, dict[str, object]] = {
    "fortaleza": {
        "id": 1,
        "aliases": [
            "fortaleza",
            "pici",
            "pici 1",
            "pici 2",
            "pici fortaleza",
            "benfica",
            "porangabussu",
            "porangabucu",
            "labomar",
            "ru fortaleza",
            "restaurante universitario de fortaleza",
        ],
    },
    "russas": {
        "id": 3,
        "aliases": ["russas", "restaurante universitario de russas"],
    },
    "quixada": {
        "id": 5,
        "aliases": ["quixada", "restaurante universitario de quixada"],
    },
    "crateus": {
        "id": 6,
        "aliases": ["crateus", "restaurante universitario de crateus"],
    },
    "sobral": {
        "id": 9,
        "aliases": ["sobral", "restaurante universitario de sobral"],
    },
}


class PratoRu(BaseModel):
    categoria: str
    descricao: str
    contem_gluten: bool = False
    contem_lactose: bool = False


class RefeicaoRu(BaseModel):
    tipo: str  # "desjejum", "almoco", "jantar"
    pratos: list[PratoRu] = Field(default_factory=list)


class CardapioDia(BaseModel):
    data: str
    restaurante_id: int
    restaurante_nome: str
    tem_cardapio: bool
    refeicoes: list[RefeicaoRu] = Field(default_factory=list)
