"""The JSON the language models write: a strict-structured-output view of the spec inside a reply envelope.

Strict structured output (Claude ``output_config.format``, Kimi ``json_schema``, DeepSeek strict tools)
accepts a subset of JSON Schema: every object closed (``additionalProperties: false``) with all properties
required, no recursion (Claude), no numeric or length bounds (Claude, DeepSeek), ``anyOf`` rather than
``oneOf``. The canonical schema (Pydantic, ``spec/schema.py``) breaks those rules in three ways, so the models
write a *transport form* that differs from the canonical spec in only two places:

* condition trees are unrolled to ``MAX_DEPTH`` levels of ``all``/``any``/``not`` instead of recursing;
* an indicator's ``params`` is a list of ``{"name", "value"}`` pairs instead of an open-ended map.

Optional fields are required-but-nullable, which Pydantic reads as "not set". Bounds and every semantic rule
are still enforced after the fact: replies are parsed with Pydantic and the spec validator, whose errors drive
the repair loop.

One envelope serves every task (generate, edit, explain, from_pine), so the schema — and with it the cached
request prefix — is byte-identical for every request to a provider.
"""

from __future__ import annotations

import copy
from functools import cache
from typing import Any

from strategy_lab.spec.indicators import CATALOGUE
from strategy_lab.spec.schema import StrategySpec
from strategy_lab.spec.validator import Issue

MAX_DEPTH = 3  # nesting levels of all/any/not above a comparison
_DROP = frozenset(
    {
        "title",
        "default",
        "discriminator",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)
_LEAVES = ("Compare", "Cross", "Between")
_GROUPS = ("AllOf", "AnyOf", "Not")
PARAM_NAMES = tuple(sorted({p.name for d in CATALOGUE.values() for p in d.params}))

ENVELOPE_FIELDS: dict[str, str] = {
    "questions": "generate only: at most 2 clarifying questions when the idea cannot be built without "
    "guessing something essential; otherwise []",
    "spec": "the strategy (generate, edit, from_pine); null for explain, questions or a refusal",
    "changes": "edit only: one short line per change made; otherwise []",
    "explanation": "explain: the explanation in plain English; otherwise null",
    "unsupported": "from_pine: Pine Script features that could not be translated; otherwise []",
    "assumptions": "choices you made that the user did not specify (defaults, interpretations)",
    "refusal": "one sentence when the request is outside backtesting (live trading, orders, accounts, keys, "
    "code); otherwise null",
}


def _ref(defs_key: str, name: str) -> dict[str, str]:
    return {"$ref": f"#/{defs_key}/{name}"}


def _is_condition_union(node: dict[str, Any]) -> bool:
    options = node.get("oneOf")
    if not isinstance(options, list):
        return False
    names = {str(o.get("$ref", "")).rsplit("/", 1)[-1] for o in options if isinstance(o, dict)}
    return names == {*_LEAVES, *_GROUPS}


def _clean(node: Any, defs_key: str, depth: int) -> Any:
    """Rewrite one Pydantic schema node into the strict subset (see the module docstring)."""
    if isinstance(node, list):
        return [_clean(item, defs_key, depth) for item in node]
    if not isinstance(node, dict):
        return node
    if _is_condition_union(node):
        return _ref(defs_key, f"Condition{depth}")
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROP:
            continue
        if key == "$ref":
            out.update(_ref(defs_key, value.rsplit("/", 1)[-1]))
        elif key == "const":
            out["enum"] = [value]
        elif key == "properties":
            out[key] = {name: _clean(sub, defs_key, depth) for name, sub in value.items()}
        elif key in ("oneOf", "anyOf"):
            options: list[Any] = []
            for option in _clean(value, defs_key, depth):
                nested = option.get("anyOf") if isinstance(option, dict) and len(option) == 1 else None
                options.extend(nested if isinstance(nested, list) else [option])
            out["anyOf"] = options
        else:
            out[key] = _clean(value, defs_key, depth)
    if out.get("type") == "object" and "properties" in out:
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    return out


PARAMS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "description": "indicator parameters as name/value pairs; omitted parameters take their defaults",
    "items": {
        "type": "object",
        "properties": {"name": {"type": "string", "enum": list(PARAM_NAMES)}, "value": {"type": "number"}},
        "required": ["name", "value"],
        "additionalProperties": False,
    },
}


@cache
def _spec_defs(defs_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(root StrategySpec schema, definitions) in the strict subset."""
    canonical = StrategySpec.model_json_schema()
    source = canonical.pop("$defs")
    defs: dict[str, Any] = {
        name: _clean(schema, defs_key, MAX_DEPTH) for name, schema in source.items() if name not in _GROUPS
    }
    defs["Indicator"]["properties"]["params"] = PARAMS_SCHEMA
    for depth in range(MAX_DEPTH + 1):
        options = [_ref(defs_key, leaf) for leaf in _LEAVES]
        if depth > 0:
            for group in _GROUPS:
                defs[f"{group}{depth}"] = _clean(source[group], defs_key, depth - 1)
                options.append(_ref(defs_key, f"{group}{depth}"))
        defs[f"Condition{depth}"] = {"anyOf": options}
    return _clean(canonical, defs_key, MAX_DEPTH), defs


def reply_schema(defs_key: str = "$defs") -> dict[str, Any]:
    """The envelope every model reply must match (``defs_key``: ``$defs``, or ``$def`` for DeepSeek)."""
    spec, defs = _spec_defs(defs_key)
    string_list = {"type": "array", "items": {"type": "string"}}
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    shapes: dict[str, Any] = {
        "questions": string_list,
        "spec": {"anyOf": [_ref(defs_key, "StrategySpec"), {"type": "null"}]},
        "changes": string_list,
        "explanation": nullable_string,
        "unsupported": string_list,
        "assumptions": string_list,
        "refusal": nullable_string,
    }
    return {
        "type": "object",
        "properties": {name: {**shapes[name], "description": text} for name, text in ENVELOPE_FIELDS.items()},
        "required": list(ENVELOPE_FIELDS),
        "additionalProperties": False,
        defs_key: {**copy.deepcopy(defs), "StrategySpec": copy.deepcopy(spec)},
    }


def wire_schema(schema: dict[str, Any], mode: str, defs_key: str) -> dict[str, Any]:
    """The schema as sent in a structured-output ``mode``: the same documents, in constructs that API accepts."""
    return typed_union_branches(schema, defs_key) if mode == "strict_tools" else schema


def typed_union_branches(schema: dict[str, Any], defs_key: str) -> dict[str, Any]:
    """``schema`` with every ``anyOf`` branch that is a bare ``$ref`` replaced by the definition it names.

    DeepSeek's strict function calling requires a ``type`` on every ``anyOf`` branch ("Invalid tool parameters
    schema : field `anyOf`: missing field `type`", HTTP 400 on the first real run) while it accepts ``$ref``
    elsewhere. A branch that is itself a union is flattened into its parent. The result accepts exactly the same
    documents; definitions no longer referenced are dropped.
    """
    defs: dict[str, Any] = schema[defs_key]

    def branches(option: dict[str, Any]) -> list[Any]:
        body = walk(defs[option["$ref"].rsplit("/", 1)[-1]] if option.keys() == {"$ref"} else option)
        return body["anyOf"] if "type" not in body and "anyOf" in body else [body]

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties":
                out[key] = {name: walk(sub) for name, sub in value.items()}
            elif key == "anyOf":
                out[key] = [branch for option in value for branch in branches(option)]
            elif key != defs_key:
                out[key] = walk(value)
        return out

    root = walk(schema)
    walked = {name: walk(body) for name, body in defs.items()}
    used: set[str] = set()
    pending = _refs(root)
    while pending:
        name = pending.pop()
        if name not in used:
            used.add(name)
            pending |= _refs(walked[name])
    kept = {name: body for name, body in walked.items() if name in used}
    return {**root, defs_key: kept} if kept else root


def _refs(node: Any) -> set[str]:
    if isinstance(node, list):
        return set().union(*(_refs(item) for item in node))
    if not isinstance(node, dict):
        return set()
    found = {node["$ref"].rsplit("/", 1)[-1]} if isinstance(node.get("$ref"), str) else set()
    return found.union(*(_refs(value) for value in node.values()))


def to_transport(spec: StrategySpec) -> dict[str, Any]:
    """Canonical spec → transport form (every field present; params as pairs)."""
    data = spec.model_dump(mode="json")
    for indicator in data["indicators"]:
        indicator["params"] = [{"name": k, "value": v} for k, v in indicator["params"].items()]
    return data


def from_transport(data: Any) -> tuple[Any, list[Issue]]:
    """Transport form → canonical dict for Pydantic. A canonical params map is accepted as well."""
    if not isinstance(data, dict):
        return data, []
    out = copy.deepcopy(data)
    issues: list[Issue] = []
    indicators = out.get("indicators")
    for i, indicator in enumerate(indicators if isinstance(indicators, list) else []):
        pairs = indicator.get("params") if isinstance(indicator, dict) else None
        if not isinstance(pairs, list):
            continue
        params: dict[str, Any] = {}
        for j, pair in enumerate(pairs):
            path = f"$.indicators[{i}].params[{j}]"
            if not (isinstance(pair, dict) and isinstance(pair.get("name"), str) and "value" in pair):
                issues.append(Issue("SCHEMA", path, 'each parameter must be {"name": ..., "value": ...}'))
            elif pair["name"] in params:
                issues.append(Issue("SCHEMA", path, f"parameter {pair['name']!r} is given twice"))
            else:
                params[pair["name"]] = pair["value"]
        indicator["params"] = params
    return out, issues
