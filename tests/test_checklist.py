import pytest

from logic.checklist import MAX_ITEMS, ChecklistError, get_checklist_for_type, load_checklist_config

CONFIG = load_checklist_config()


@pytest.mark.parametrize("outlet_type", ["General Trade", "Mobile Specialist", "Premium Reseller", "Multi-Yard"])
def test_every_real_outlet_type_has_at_most_five_items(outlet_type):
    items = get_checklist_for_type(outlet_type, CONFIG)
    assert 1 <= len(items) <= MAX_ITEMS


def test_unknown_outlet_type_falls_back_to_universal_items_not_a_crash():
    items = get_checklist_for_type("Some New Type Nobody Configured", CONFIG)
    assert len(items) == len(CONFIG["universal_items"])


def test_max_items_cap_is_enforced_in_code():
    bad_config = {
        "universal_items": [{"key": f"u{i}", "label": "x", "type": "action"} for i in range(3)],
        "outlet_types": {"Bloated": {"items": [{"key": f"t{i}", "label": "x", "type": "blocker", "options": ["a"]} for i in range(4)]}},
    }
    with pytest.raises(ChecklistError):
        get_checklist_for_type("Bloated", bad_config)


def test_universal_items_present_in_every_type():
    universal_keys = {item["key"] for item in CONFIG["universal_items"]}
    for outlet_type in CONFIG["outlet_types"]:
        items = get_checklist_for_type(outlet_type, CONFIG)
        keys = {item["key"] for item in items}
        assert universal_keys.issubset(keys)
