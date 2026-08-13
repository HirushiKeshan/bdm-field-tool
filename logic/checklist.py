"""
Loads checklists.yaml and enforces the 5-item cap in code, not just by
convention in the config file.
"""
from pathlib import Path

import yaml

CHECKLIST_PATH = Path(__file__).parent.parent / "checklists.yaml"
MAX_ITEMS = 5


class ChecklistError(Exception):
    pass


def load_checklist_config(path=CHECKLIST_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_checklist_for_type(outlet_type: str, config: dict = None) -> list:
    config = config or load_checklist_config()
    universal = config.get("universal_items", [])
    type_config = config.get("outlet_types", {}).get(outlet_type)
    if type_config is None:
        # Unknown/blank outlet type: still give the BDM something usable
        # rather than crashing the screen -- universal items only.
        items = list(universal)
    else:
        items = list(universal) + list(type_config.get("items", []))

    if len(items) > MAX_ITEMS:
        raise ChecklistError(
            f"Outlet type {outlet_type!r} resolves to {len(items)} checklist items, "
            f"max is {MAX_ITEMS}. Fix checklists.yaml."
        )
    return items
