import json
from importlib.resources import files

import pytest

from visiter import Op, Rule, iterate

jsonschema = pytest.importorskip("jsonschema")
from jsonschema import Draft202012Validator  # noqa: E402


def _schema(version="1"):
    resource = files("visiter").joinpath(f"schemas/v{version}/graph.schema.json")
    with resource.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_bundled_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(_schema())


def test_iterate_output_declares_schema_version():
    g = iterate([1], rules=[], default=Op(lambda x: x + 1, "+1"), max_nodes=5,
                on_limit="stop")
    assert g["schema_version"] == "1"


def test_iterate_output_validates_against_schema():
    g = iterate(
        start=range(1, 30),
        rules=[Rule(lambda x: x % 3 == 0, Op(lambda x: x // 3, "÷3"))],
        default=Op(lambda x: x + 2, "+2"),
        max_depth=8,
        tags={"highlight": lambda x: x > 0 and (x & (x - 1)) == 0},
    )
    Draft202012Validator(_schema()).validate(g)


def test_schema_rejects_wrong_version():
    g = iterate([1], rules=[], default=Op(lambda x: x, "id"), max_nodes=2,
                on_limit="stop")
    g["schema_version"] = "2"
    errs = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errs, "schema_version='2' must fail v1 validation"


def test_string_valued_iterate_validates_against_schema():
    # Iterate on strings: drop trailing vowel until none remain.
    vowels = set("aeiou")
    g = iterate(
        start=["banana", "garage"],
        rules=[Rule(lambda s: len(s) > 0 and s[-1] in vowels,
                    Op(lambda s: s[:-1], "drop-vowel"))],
        default=None,
    )
    Draft202012Validator(_schema()).validate(g)


def test_tuple_valued_iterate_validates_against_schema_after_json_roundtrip():
    # Iterate on 2D grid coordinates (tuples are hashable, str()-able).
    # The schema applies to the JSON wire form — round-trip via json.dump
    # with default=str (matching CLI behaviour) before validating.
    g = iterate(
        start=[(0, 0)],
        rules=[Rule(lambda p: p[0] < 2,
                    Op(lambda p: (p[0] + 1, p[1]), "right"),
                    bound=lambda p: p[0] + 1 <= 2)],
        default=None,
    )
    wire = json.loads(json.dumps(g, default=str))
    Draft202012Validator(_schema()).validate(wire)


def test_schema_rejects_unknown_top_level_property():
    g = iterate([1], rules=[], default=Op(lambda x: x, "id"), max_nodes=2,
                on_limit="stop")
    g["surprise"] = True
    errs = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errs
