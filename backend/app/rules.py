from copy import deepcopy

from pydantic import BaseModel, Field, model_validator

BRANCHES = ["NV", "LN", "AR", "RO", "IK"]
LOCATIONS = BRANCHES + ["HO", "CZ"]
MATERIALS = ["gold", "natural_diamond", "lab_diamond"]

DEFAULT_RULES = {
    "targets": {"NV": 24, "LN": 16, "AR": 19, "RO": 19, "IK": 22},
    "age_days": 180,
    "annual_turns": 4,
    "weights": {
        "availability": 5,
        "profitability": 3,
        "reactivation": 4,
        "stock_balance": 2,
        "aged_balance": 4,
    },
    "allow_branch_exchange": False,
    "target_basis": {
        "gold": "weight_g",
        "natural_diamond": "cost",
        "lab_diamond": "cost",
    },
    "master_controls": {},
    "masters": {
        "items": [],
        "karatages": [],
        "varieties": [],
        "suppliers": [],
        "lmh": [],
    },
    "margins": [
        {
            "material": "gold",
            "karatage": "22KT",
            "variety": "plain",
            "percent": 1.25,
            "basis": "net_sale_value",
            "confirmed": True,
        },
        {
            "material": "gold",
            "karatage": "18KT",
            "variety": "plain",
            "percent": 2.5,
            "basis": "net_sale_value",
            "confirmed": True,
        },
        {
            "material": "gold",
            "karatage": "*",
            "variety": "Antique",
            "percent": 15,
            "basis": "net_sale_value",
            "confirmed": True,
        },
        {
            "material": "gold",
            "karatage": "*",
            "variety": "Jadau",
            "percent": 30,
            "basis": "net_sale_value",
            "confirmed": True,
        },
    ],
    "stone_economics": {
        "natural_diamond_cost_per_carat": 15000,
        "lab_diamond_cost_per_carat": 7000,
        "confirmed": False,
        "notes": "User-supplied provisional buying costs; exported label costs take precedence. Stone profit basis remains unconfirmed.",
    },
    "notes": "Initial planning assumptions. Masters and economics require business confirmation.",
}


class Margin(BaseModel):
    material: str
    karatage: str
    variety: str
    percent: float = Field(ge=0, lt=100)
    basis: str | None = None
    confirmed: bool = False

    @model_validator(mode="after")
    def basis_confirmed(self):
        if self.material not in MATERIALS:
            raise ValueError("Unknown material in margin")
        if self.basis not in (None, "cost_markup", "revenue_margin", "net_sale_value"):
            raise ValueError(
                "Margin basis must be cost_markup, revenue_margin or net_sale_value"
            )
        if self.confirmed and self.basis is None:
            raise ValueError("Confirm a margin basis before using profit")
        return self


class Rules(BaseModel):
    targets: dict[str, float]
    age_days: int = Field(ge=1, le=3650)
    annual_turns: float = Field(gt=0, le=100)
    weights: dict[str, int]
    allow_branch_exchange: bool = False
    target_basis: dict[str, str] = Field(
        default_factory=lambda: deepcopy(DEFAULT_RULES["target_basis"])
    )
    master_controls: dict = Field(default_factory=dict)
    masters: dict[str, list]
    margins: list[Margin]
    stone_economics: dict
    notes: str = ""

    @model_validator(mode="after")
    def validate_rules(self):
        if (
            set(self.targets) != set(BRANCHES)
            or any(v <= 0 for v in self.targets.values())
            or abs(sum(self.targets.values()) - 100) > 0.0001
        ):
            raise ValueError("Targets must cover NV/LN/AR/RO/IK and sum to 100%")
        if (
            set(self.weights) != set(DEFAULT_RULES["weights"])
            or any(v < 0 or v > 100 for v in self.weights.values())
            or not any(self.weights.values())
        ):
            raise ValueError(
                "Specify all five objective weights in 0..100, with at least one positive"
            )
        if set(self.masters) != set(DEFAULT_RULES["masters"]):
            raise ValueError(
                "Masters require items, karatages, varieties, suppliers and lmh"
            )
        for key in ("items", "karatages", "varieties", "suppliers"):
            if any(
                not isinstance(v, str) or not v.strip() for v in self.masters[key]
            ) or len(set(self.masters[key])) != len(self.masters[key]):
                raise ValueError(f"Invalid {key} master values")
        for r in self.masters["lmh"]:
            if not isinstance(r, dict) or not r.get("item"):
                raise ValueError("L/M/H rules require an item")
            if "light_max_g" in r or "medium_max_g" in r:
                if (
                    not 0
                    < float(r.get("light_max_g", 0))
                    < float(r.get("medium_max_g", 0))
                ):
                    raise ValueError(
                        "L/M/H weight bands require 0 < light_max_g < medium_max_g"
                    )
            elif r.get("class") not in ("L", "M", "H"):
                raise ValueError(
                    "L/M/H rule requires weight bands or a class L, M or H"
                )
        if set(self.target_basis) != set(MATERIALS) or any(
            v not in ("cost", "weight_g") for v in self.target_basis.values()
        ):
            raise ValueError("Specify cost or weight_g target basis for each material")
        return self


def fresh_defaults():
    return deepcopy(DEFAULT_RULES)
