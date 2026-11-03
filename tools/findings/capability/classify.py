# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Classify and queue findings by forbidden outcome."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

from findings.capability.taxonomy import (
    AXIS_LABEL,
    BANDS,
    BOUNDARIES,
    CLASS_FIELDS,
    COOPERATIONS,
    DISPOSITIONS,
    DURABILITIES,
    EFFECTS,
    ENUM_IDS,
    EXPOSURES,
    GATES,
    OPTION_LIST,
    SCOPES,
    Axis,
    Boundary,
    Cooperation,
    Durability,
    Effect,
    FindingClass,
    Gate,
    PolicyId,
    Scope,
    effect_band,
    label_for,
    policy_order,
    rank_for,
)

FIELD_OPTIONS = {
    "disposition": DISPOSITIONS,
    "exposure": EXPOSURES,
    "gate": GATES,
    "cooperation": COOPERATIONS,
    "boundary": BOUNDARIES,
    "effect": EFFECTS,
    "scope": SCOPES,
    "durability": DURABILITIES,
}


def class_key(finding: FindingClass) -> str:
    return ".".join(
        [
            "forbidden" if finding["forbidden"] else "permitted",
            finding["disposition"],
            finding["exposure"],
            finding["gate"],
            finding["cooperation"],
            finding["effect"],
            finding["boundary"],
            finding["scope"],
            finding["durability"],
        ]
    )


def short_class(finding: FindingClass | Dict[str, Any] | None) -> str:
    """Compact display label for tables: effect/boundary or empty."""
    if not isinstance(finding, dict):
        return ""
    effect = finding.get("effect")
    boundary = finding.get("boundary")
    if isinstance(effect, str) and effect and isinstance(boundary, str) and boundary:
        return f"{effect}/{boundary}"
    if isinstance(effect, str) and effect:
        return effect
    return ""


BELONGING: Dict[Boundary, str] = {
    "self": "belonging to the caller",
    "service": "belonging to the application itself",
    "other-principal": "belonging to another principal at the same level",
    "higher-principal": "belonging to a more privileged principal",
    "other-tenant": "belonging to another tenant",
    "host": "belonging to the host or a different system",
}

IMPERSONATE: Dict[Boundary, str] = {
    "self": "act only as the caller",
    "service": "act as the application",
    "other-principal": "act as another principal at the same level",
    "higher-principal": "act as a more privileged principal",
    "other-tenant": "act as a principal in another tenant",
    "host": "act as the host or a service account",
}

AUTHORITY: Dict[Boundary, str] = {
    "self": "of the caller",
    "service": "of the application",
    "other-principal": "of another principal at the same level",
    "higher-principal": "of a more privileged principal",
    "other-tenant": "of another tenant",
    "host": "of the host or a different system",
}

WHO: Dict[Gate, str] = {
    "none": "someone with no account",
    "any-account": "any signed-in account",
    "privileged": "a privileged account",
    "chained": "someone who already exploited something else",
}

SCOPE_TAIL: Dict[Scope, str] = {
    "one-object": "limited to one object",
    "one-principal": "limited to one principal",
    "tenant": "across one tenant",
    "cross-tenant": "across tenants",
    "fleet": "across the fleet",
}

DURABILITY_CLAUSE: Dict[Durability, str] = {
    "once": "The effect happens once",
    "persists": "The effect stays until someone removes it",
    "reexecutes": "The effect runs again for later users or deploys",
}

COOPERATION_CLAUSE: Dict[Cooperation, str] = {
    "aimed": "and each victim has to be steered into it",
    "ambient": "and it does not depend on steering a victim",
}


def _outcome(effect: Effect, boundary: Boundary) -> str:
    if effect == "none":
        return "break no security property"
    if effect == "read-public":
        return "read information that is already meant to be visible"
    if effect == "read-sensitive":
        return f"read private information {BELONGING[boundary]}"
    if effect == "write-data":
        return f"create or change ordinary information {BELONGING[boundary]}"
    if effect == "destroy":
        return f"delete information or deny service {BELONGING[boundary]}"
    if effect == "read-secrets":
        return f"read credentials or keys {BELONGING[boundary]}"
    if effect == "write-security":
        return f"change permissions, identity, or the audit record {BELONGING[boundary]}"
    if effect == "impersonate":
        return IMPERSONATE[boundary]
    if effect == "actuate":
        return (
            "cause a payment, a message, a device action, or another effect "
            f"outside the software {BELONGING[boundary]}"
        )
    if effect == "execute-in-app":
        return (
            "run their own instructions inside the application, "
            f"with the authority {AUTHORITY[boundary]}"
        )
    if effect == "execute-on-host":
        return f"run their own code on the host or in another system, {BELONGING[boundary]}"
    return "break no security property"


def _action(finding: FindingClass, modal: Literal["can", "could"]) -> str:
    who = WHO[finding["gate"]]
    what = f"{_outcome(finding['effect'], finding['boundary'])}, {SCOPE_TAIL[finding['scope']]}"
    exposure = finding["exposure"]
    if exposure == "local":
        return f"On the machine where the program is already running, {who} {modal} {what}."
    if exposure == "adjacent":
        return f"From a private network, localhost, or the same host, {who} {modal} {what}."
    if exposure == "internet":
        return f"From the internet, {who} {modal} {what}."
    return f"From the build, install, or CI pipeline, {who} {modal} {what}."


def describe_finding(finding: FindingClass) -> str:
    if not finding["forbidden"]:
        return (
            "This is not a vulnerability under this classification. "
            "The caller who can reach it is already allowed to do this. "
            "Keep it only if that role must not cross into another tenant, "
            "the host, or another system."
        )

    tail = (
        f"{DURABILITY_CLAUSE[finding['durability']]}, "
        f"{COOPERATION_CLAUSE[finding['cooperation']]}."
    )

    if finding["disposition"] == "live":
        return f"Production runs this code. {_action(finding, 'can')} {tail}"

    presence = (
        "This code ships, and nothing that runs enters it today."
        if finding["disposition"] == "dormant"
        else "This code is not in the production artifact."
    )
    return (
        f"{presence} It sits below outcomes production can already enter. "
        f"If that changed: {_action(finding, 'could')} {tail}"
    )


def queue_key(finding: FindingClass, policy: PolicyId) -> List[int]:
    return [rank_for(axis, finding) for axis in policy_order(policy)]


def compare_queue(a: FindingClass, b: FindingClass, policy: PolicyId) -> int:
    """Negative when `a` is worse (sorts first)."""
    ka = queue_key(a, policy)
    kb = queue_key(b, policy)
    for left, right in zip(ka, kb):
        if left != right:
            return right - left
    return 0


class Decision(TypedDict):
    winner: Literal["a", "b", "tie"]
    axis: Optional[Axis]
    headline: str
    tension: Optional[str]


TENSION_GAP = 2


def decide(a: FindingClass, b: FindingClass, policy: PolicyId) -> Decision:
    order = policy_order(policy)
    ka = queue_key(a, policy)
    kb = queue_key(b, policy)

    for index, axis in enumerate(order):
        if ka[index] == kb[index]:
            continue

        winner: Literal["a", "b"] = "a" if ka[index] > kb[index] else "b"
        winner_finding = a if winner == "a" else b
        loser_finding = b if winner == "a" else a
        headline = (
            f"{label_for(axis, winner_finding)} outranks "
            f"{label_for(axis, loser_finding).lower()} on {AXIS_LABEL[axis]}."
        )

        tension: Optional[str] = None
        strongest_gap = 0
        strongest_axis: Optional[Axis] = None

        for later in order[index + 1 :]:
            winner_rank = rank_for(later, winner_finding)
            loser_rank = rank_for(later, loser_finding)
            gap = loser_rank - winner_rank
            if gap >= TENSION_GAP and gap > strongest_gap:
                strongest_gap = gap
                strongest_axis = later

        if strongest_axis is not None:
            tension = (
                f"The other finding is worse on {AXIS_LABEL[strongest_axis]}: "
                f"{label_for(strongest_axis, loser_finding).lower()}, against "
                f"{label_for(strongest_axis, winner_finding).lower()}. "
                "The queue stopped before that. Read both sentences."
            )

        return {
            "winner": winner,
            "axis": axis,
            "headline": headline,
            "tension": tension,
        }

    return {
        "winner": "tie",
        "axis": None,
        "headline": "These two findings are the same class under this queue.",
        "tension": None,
    }


def to_capability_yaml(finding: FindingClass) -> str:
    lines = [
        "capability:",
        f"  forbidden: {'true' if finding['forbidden'] else 'false'}",
        f"  disposition: {finding['disposition']}",
        f"  exposure: {finding['exposure']}",
        f"  gate: {finding['gate']}",
        f"  cooperation: {finding['cooperation']}",
        f"  effect: {finding['effect']}",
        f"  boundary: {finding['boundary']}",
        f"  scope: {finding['scope']}",
        f"  durability: {finding['durability']}",
    ]
    return "\n".join(lines)


class ParseOk(TypedDict):
    ok: Literal[True]
    finding: FindingClass


class ParseErr(TypedDict):
    ok: Literal[False]
    error: str


ParseResult = Union[ParseOk, ParseErr]


def _as_boolean(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value in ("true", "yes"):
        return True
    if value in ("false", "no"):
        return False
    return None


def parse_capability_block(block: Dict[str, Any]) -> ParseResult:
    """Parse a capability mapping into a FindingClass."""
    missing: List[str] = []
    invalid: List[str] = []
    finding: Dict[str, Any] = {}

    for field in CLASS_FIELDS:
        raw = block.get(field)
        if raw is None or raw == "":
            missing.append(field)
            continue
        if field == "forbidden":
            bool_value = _as_boolean(raw)
            if bool_value is None:
                invalid.append(f"{field} must be true or false")
            else:
                finding["forbidden"] = bool_value
            continue
        if not isinstance(raw, str):
            invalid.append(f"{field} must be a string")
            continue
        options = FIELD_OPTIONS[field]
        match = next((option for option in options if option["id"] == raw), None)
        if match is None:
            allowed = ", ".join(option["id"] for option in options)
            invalid.append(f"{field} must be one of {allowed}")
            continue
        finding[field] = match["id"]

    if missing or invalid:
        parts: List[str] = []
        if missing:
            parts.append(f"Missing: {', '.join(missing)}.")
        if invalid:
            parts.append(" ".join(invalid))
        return {"ok": False, "error": " ".join(parts)}

    return {"ok": True, "finding": finding}  # type: ignore[return-value]


def try_finding_class(capability: Any) -> Optional[FindingClass]:
    """Return a FindingClass when capability is fully populated, else None."""
    if not isinstance(capability, dict):
        return None
    parsed = parse_capability_block(capability)
    if not parsed["ok"]:
        return None
    return parsed["finding"]


def is_capability_complete(capability: Any) -> bool:
    return try_finding_class(capability) is not None


def band_summary() -> str:
    ordered = sorted(BANDS, key=lambda band: int(band["rank"]), reverse=True)  # type: ignore[arg-type]
    return " · ".join(str(band["label"]) for band in ordered)


def empty_capability() -> Dict[str, Any]:
    return {
        "forbidden": True,
        "disposition": "",
        "exposure": "",
        "gate": "",
        "cooperation": "",
        "boundary": "",
        "effect": "",
        "scope": "",
        "durability": "",
    }


def capability_enum_ids(field: str) -> frozenset[str]:
    return ENUM_IDS.get(field, frozenset())


def options_for(axis: str) -> List[Dict[str, Any]]:
    return list(OPTION_LIST.get(axis, []))


__all__ = [
    "band_summary",
    "class_key",
    "compare_queue",
    "decide",
    "describe_finding",
    "effect_band",
    "empty_capability",
    "is_capability_complete",
    "parse_capability_block",
    "queue_key",
    "short_class",
    "to_capability_yaml",
    "try_finding_class",
]
