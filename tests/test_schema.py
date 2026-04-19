import json
from importlib.resources import files

import pytest

from visiter import viter

jsonschema = pytest.importorskip("jsonschema")
from jsonschema import Draft202012Validator  # noqa: E402


def _schema(version="1"):
    resource = files("visiter").joinpath(f"schemas/v{version}/graph.schema.json")
    with resource.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_bundled_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(_schema())


def test_build_output_declares_schema_version():
    g = (viter([1], max_nodes=5)
         .default(lambda x: x + 1, label="+1")
         .build())
    assert g["schema_version"] == "1"


def test_build_output_validates_against_schema():
    g = (viter(range(1, 30), max_depth=8,
               tags={"highlight": lambda x: x > 0 and (x & (x - 1)) == 0})
         .case(lambda x: x % 3 == 0, lambda x: x // 3, label="÷3")
         .default(lambda x: x + 2, label="+2")
         .build())
    Draft202012Validator(_schema()).validate(g)


def test_schema_rejects_wrong_version():
    g = (viter([1], max_nodes=2)
         .default(lambda x: x, label="id")
         .build())
    g["schema_version"] = "2"
    errs = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errs, "schema_version='2' must fail v1 validation"


def test_build_emits_key_type_integer_for_integer_seeds():
    g = (viter(range(1, 5))
         .case(lambda x: x % 2 == 0, lambda x: x // 2, label="÷2")
         .default(lambda x: x + 1, label="+1")
         .build())
    for key, info in g["nodes"].items():
        assert info["key_type"] == "integer", f"node {key}: {info}"


def test_build_emits_key_type_string_for_string_seeds():
    vowels = set("aeiou")
    g = (viter(["banana", "garage"])
         .case(lambda s: len(s) > 0 and s[-1] in vowels,
               lambda s: s[:-1], label="drop-vowel")
         .build())
    for key, info in g["nodes"].items():
        assert info["key_type"] == "string"


def test_build_emits_key_type_array_for_tuple_seeds():
    # JSON has no tuple type; tuples map to the "array" JSON primitive.
    g = (viter([(0, 0)])
         .case(lambda p: p[0] < 2, lambda p: (p[0] + 1, p[1]),
               label="right", bound=lambda p: p[0] + 1 <= 2)
         .build())
    for key, info in g["nodes"].items():
        assert info["key_type"] == "array"


def test_build_emits_key_type_boolean_not_integer():
    # bool is a subclass of int in Python — the JSON mapping must
    # dispatch bool BEFORE int so booleans show as "boolean".
    g = viter([True]).build()
    assert g["nodes"]["True"]["key_type"] == "boolean"


def test_schema_restricts_key_type_to_json_primitives():
    g = (viter([1], max_nodes=3)
         .default(lambda x: x + 1, label="+1")
         .build())
    # A Python-specific name like "int" must NOT validate.
    for info in g["nodes"].values():
        info["key_type"] = "int"
    errors = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errors, "key_type='int' (Python name) must fail validation"


def test_schema_requires_key_type_on_every_node():
    # An otherwise-valid doc without key_type must fail validation.
    g = (viter([1], max_nodes=3)
         .default(lambda x: x + 1, label="+1")
         .build())
    # Strip key_type to simulate a doc missing the field.
    for info in g["nodes"].values():
        del info["key_type"]
    errors = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errors, "schema should reject nodes without key_type"


def test_schema_requires_schema_version_at_top_level():
    g = (viter([1], max_nodes=3)
         .default(lambda x: x + 1, label="+1")
         .build())
    del g["schema_version"]
    errors = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errors, "schema should reject docs without schema_version"


def test_string_valued_build_validates_against_schema():
    # Iterate on strings: drop trailing vowel until none remain.
    vowels = set("aeiou")
    g = (viter(["banana", "garage"])
         .case(lambda s: len(s) > 0 and s[-1] in vowels,
               lambda s: s[:-1], label="drop-vowel")
         .build())
    Draft202012Validator(_schema()).validate(g)


def test_tuple_valued_build_validates_against_schema_after_json_roundtrip():
    # Iterate on 2D grid coordinates (tuples are hashable, str()-able).
    # The schema applies to the JSON wire form — round-trip via json.dump
    # with default=str (matching CLI behaviour) before validating.
    g = (viter([(0, 0)])
         .case(lambda p: p[0] < 2, lambda p: (p[0] + 1, p[1]),
               label="right", bound=lambda p: p[0] + 1 <= 2)
         .build())
    wire = json.loads(json.dumps(g, default=str))
    Draft202012Validator(_schema()).validate(wire)


def test_schema_rejects_unknown_top_level_property():
    g = (viter([1], max_nodes=2)
         .default(lambda x: x, label="id")
         .build())
    g["surprise"] = True
    errs = list(Draft202012Validator(_schema()).iter_errors(g))
    assert errs
