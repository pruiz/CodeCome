# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Capability taxonomy: the forbidden outcome for a finding.

Critical / High / Medium / Low are not classes. A CVSS score is not a class.
The queue order is a separate, replaceable policy. It is not stored on the finding.
"""

from __future__ import annotations

from typing import Dict, List, Literal, TypedDict, Union

PolicyId = Literal["service", "local-program"]

Axis = Literal[
    "forbidden",
    "disposition",
    "exposure",
    "effectBand",
    "boundary",
    "effect",
    "gate",
    "scope",
    "durability",
    "cooperation",
]

Disposition = Literal["not-shipped", "dormant", "live"]
Exposure = Literal["local", "adjacent", "internet", "build"]
Gate = Literal["chained", "privileged", "any-account", "none"]
Cooperation = Literal["aimed", "ambient"]
Boundary = Literal[
    "self",
    "service",
    "other-principal",
    "higher-principal",
    "other-tenant",
    "host",
]
Effect = Literal[
    "none",
    "read-public",
    "read-sensitive",
    "write-data",
    "deny",
    "destroy",
    "read-secrets",
    "write-security",
    "bypass-control",
    "impersonate",
    "actuate",
    "execute-in-app",
    "execute-on-host",
]

DecisionId = Literal["fix-now", "plan"]
Scope = Literal["one-object", "one-principal", "tenant", "cross-tenant", "fleet"]
Durability = Literal["once", "persists", "reexecutes"]

CLASS_FIELDS = (
    "forbidden",
    "disposition",
    "exposure",
    "gate",
    "cooperation",
    "boundary",
    "effect",
    "scope",
    "durability",
)

STORED_AXES = (
    "disposition",
    "exposure",
    "gate",
    "cooperation",
    "boundary",
    "effect",
    "scope",
    "durability",
)


class FindingClass(TypedDict):
    forbidden: bool
    disposition: Disposition
    exposure: Exposure
    gate: Gate
    cooperation: Cooperation
    boundary: Boundary
    effect: Effect
    scope: Scope
    durability: Durability


class Option(TypedDict):
    id: str
    label: str
    hint: str
    rank: int


POLICIES: Dict[PolicyId, Dict[str, str]] = {
    "service": {
        "id": "service",
        "label": "Internet-facing service",
        "summary": (
            "Production reach comes first, then whether an outsider can get there, "
            "then what kind of power they gain. Use this for a service you deploy."
        ),
    },
    "local-program": {
        "id": "local-program",
        "label": "Local program",
        "summary": (
            "Production reach comes first, then what the bug lets someone do, "
            "then where they must be. Use this when the product's job is opening "
            "files or running on the operator's machine."
        ),
    },
}

SERVICE_ORDER: List[Axis] = [
    "forbidden",
    "disposition",
    "exposure",
    "effectBand",
    "boundary",
    "effect",
    "gate",
    "scope",
    "durability",
    "cooperation",
]

LOCAL_ORDER: List[Axis] = [
    "forbidden",
    "disposition",
    "effectBand",
    "boundary",
    "effect",
    "exposure",
    "gate",
    "scope",
    "durability",
    "cooperation",
]


def policy_order(policy: PolicyId) -> List[Axis]:
    return SERVICE_ORDER if policy == "service" else LOCAL_ORDER


DISPOSITIONS: List[Option] = [
    {
        "id": "live",
        "label": "Live in production",
        "hint": "A request, job, or tool that production runs enters this code. An obscure route is live.",
        "rank": 2,
    },
    {
        "id": "dormant",
        "label": "Shipped, not entered",
        "hint": "Present in the artifact. Nothing that runs can enter it. A registered route is not dormant.",
        "rank": 1,
    },
    {
        "id": "not-shipped",
        "label": "Not in the release",
        "hint": "Absent from the production artifact. Dead source, tests, or a feature that was not built.",
        "rank": 0,
    },
]

EXPOSURES: List[Option] = [
    {
        "id": "build",
        "label": "Build, install, or CI",
        "hint": "Runs while the artifact is produced or installed. The output is what you deploy.",
        "rank": 3,
    },
    {
        "id": "internet",
        "label": "Internet",
        "hint": "Reachable from the public network.",
        "rank": 2,
    },
    {
        "id": "adjacent",
        "label": "Private network or same host",
        "hint": "Localhost, a private network, link-local, or another process on the same machine.",
        "rank": 1,
    },
    {
        "id": "local",
        "label": "Local only",
        "hint": "Only a person already running the program on that machine.",
        "rank": 0,
    },
]

GATES: List[Option] = [
    {
        "id": "none",
        "label": "No account",
        "hint": "No session and no earlier bug.",
        "rank": 3,
    },
    {
        "id": "any-account",
        "label": "Any account",
        "hint": "The lowest signed-in principal is enough.",
        "rank": 2,
    },
    {
        "id": "privileged",
        "label": "Privileged account",
        "hint": "Only a role that already holds broad power inside the product.",
        "rank": 1,
    },
    {
        "id": "chained",
        "label": "Needs another vulnerability",
        "hint": "This step does nothing until some other bug is used first.",
        "rank": 0,
    },
]

COOPERATIONS: List[Option] = [
    {
        "id": "ambient",
        "label": "Whoever uses the path",
        "hint": "No extra click, paste, or visit to an attacker-chosen link.",
        "rank": 1,
    },
    {
        "id": "aimed",
        "label": "Each victim must be steered",
        "hint": "Someone must open a link, paste a value, or be signed in at the moment you choose.",
        "rank": 0,
    },
]

BOUNDARIES: List[Option] = [
    {
        "id": "host",
        "label": "Host or another system",
        "hint": "The machine, the cluster, or a different system such as the cloud API.",
        "rank": 5,
    },
    {
        "id": "other-tenant",
        "label": "Another tenant",
        "hint": "A customer or tenant the caller does not belong to.",
        "rank": 4,
    },
    {
        "id": "higher-principal",
        "label": "A more privileged principal",
        "hint": "A role with more authority than the caller.",
        "rank": 3,
    },
    {
        "id": "other-principal",
        "label": "Another principal, same level",
        "hint": "Another user who is not above the caller.",
        "rank": 2,
    },
    {
        "id": "service",
        "label": "The application's own state",
        "hint": "Shared cache, config, logs, or other data that is not one person's record.",
        "rank": 1,
    },
    {
        "id": "self",
        "label": "The caller only",
        "hint": "Only the caller's own data or session. If they could already do it, it is permitted.",
        "rank": 0,
    },
]

EFFECTS: List[Option] = [
    {
        "id": "execute-on-host",
        "label": "Run code on the host or another system",
        "hint": "A shell, a deserializer, a container escape, or a pivot onto a different machine.",
        "rank": 10,
    },
    {
        "id": "execute-in-app",
        "label": "Run instructions inside the application",
        "hint": "SQL, a template, a command, or a stored script in the application's origin. Not an ordinary field edit.",
        "rank": 9,
    },
    {
        "id": "actuate",
        "label": "Cause an action outside the software",
        "hint": "A payment, a sent message, a device, or anything the software does to the world.",
        "rank": 8,
    },
    {
        "id": "impersonate",
        "label": "Act as someone else",
        "hint": (
            "Use another identity without possessing their secret. "
            "Includes forging a token or signature that the system treats as that identity."
        ),
        "rank": 7,
    },
    {
        "id": "bypass-control",
        "label": "Disable or skip a security control",
        "hint": (
            "Auth, MFA, authorization, audit, rate limits, kill-switches, or guardrails "
            "stop enforcing — without needing a role edit or code execution."
        ),
        "rank": 6,
    },
    {
        "id": "write-security",
        "label": "Change permissions, identity, or the audit record",
        "hint": "A role, a password, a grant, or the record of what happened.",
        "rank": 6,
    },
    {
        "id": "read-secrets",
        "label": "Read credentials or keys",
        "hint": "Passwords, tokens, session cookies, private keys, or cloud credentials.",
        "rank": 5,
    },
    {
        "id": "destroy",
        "label": "Delete or corrupt the source of truth",
        "hint": "Information is gone or untrustworthy. Not a temporary outage.",
        "rank": 4,
    },
    {
        "id": "deny",
        "label": "Deny the service",
        "hint": "Availability only. The service will not serve; the source of truth may still be intact.",
        "rank": 3,
    },
    {
        "id": "write-data",
        "label": "Create or change ordinary information",
        "hint": "A normal record. Not a permission, not code, not a payment.",
        "rank": 3,
    },
    {
        "id": "read-sensitive",
        "label": "Read private information",
        "hint": "Data that should stay private and that does not itself grant a further action.",
        "rank": 2,
    },
    {
        "id": "read-public",
        "label": "Read something already meant to be visible",
        "hint": "A version string, a public page, or other data that grants nothing further.",
        "rank": 1,
    },
    {
        "id": "none",
        "label": "No security property broken",
        "hint": "Nothing becomes possible that was forbidden.",
        "rank": 0,
    },
]

SCOPES: List[Option] = [
    {
        "id": "fleet",
        "label": "The fleet",
        "hint": "Every customer, or every deploy of this component.",
        "rank": 7,
    },
    {
        "id": "cross-tenant",
        "label": "More than one tenant",
        "hint": "Crosses tenant boundaries, short of the whole fleet.",
        "rank": 5,
    },
    {
        "id": "tenant",
        "label": "One tenant",
        "hint": "Everyone inside a single tenant.",
        "rank": 3,
    },
    {
        "id": "one-principal",
        "label": "One principal",
        "hint": "A single account.",
        "rank": 1,
    },
    {
        "id": "one-object",
        "label": "One object",
        "hint": "One record, file, or request.",
        "rank": 0,
    },
]

DURABILITIES: List[Option] = [
    {
        "id": "reexecutes",
        "label": "Runs again later",
        "hint": "A later visitor, job, or deploy runs it again. Stored script, backdoor, poisoned artifact.",
        "rank": 2,
    },
    {
        "id": "persists",
        "label": "Stays until removed",
        "hint": "The change remains, and it does not run itself again.",
        "rank": 1,
    },
    {
        "id": "once",
        "label": "Once",
        "hint": "One response or one action, then it is gone.",
        "rank": 0,
    },
]

BANDS: List[Dict[str, Union[int, str, List[str]]]] = [
    {
        "rank": 4,
        "label": "Run attacker-chosen code on the host or another system",
        "effects": ["execute-on-host"],
    },
    {
        "rank": 3,
        "label": (
            "Run instructions in the application, take a credential or permission, "
            "bypass a control, take an identity, or cause an outside action"
        ),
        "effects": [
            "execute-in-app",
            "actuate",
            "impersonate",
            "bypass-control",
            "write-security",
            "read-secrets",
        ],
    },
    {
        "rank": 2,
        "label": "Read private data, change ordinary data, destroy data, or deny service",
        "effects": ["destroy", "deny", "write-data", "read-sensitive"],
    },
    {
        "rank": 1,
        "label": "Read something already visible",
        "effects": ["read-public"],
    },
    {
        "rank": 0,
        "label": "No security property",
        "effects": ["none"],
    },
]

# Effects that are fix-now on their own when the code is in the artifact.
FIX_NOW_EFFECTS = frozenset(
    {
        "execute-on-host",
        "execute-in-app",
        "actuate",
        "impersonate",
        "bypass-control",
        "write-security",
        "read-secrets",
    }
)

# Wide data destruction is fix-now even though destroy is not in FIX_NOW_EFFECTS.
FIX_NOW_DESTROY_SCOPES = frozenset({"tenant", "cross-tenant", "fleet"})

# Mass sensitive reads from reachable surfaces are fix-now.
FIX_NOW_SENSITIVE_SCOPES = frozenset({"cross-tenant", "fleet"})
FIX_NOW_SENSITIVE_EXPOSURES = frozenset({"internet", "build"})

AXIS_LABEL: Dict[Axis, str] = {
    "forbidden": "whether the outcome is forbidden",
    "disposition": "whether production runs the code",
    "exposure": "where an attacker can reach it",
    "effectBand": "what kind of power this adds",
    "boundary": "whose asset or authority is affected",
    "effect": "the specific outcome",
    "gate": "what the attacker must already have",
    "scope": "how much is affected",
    "durability": "whether it sticks or runs again",
    "cooperation": "whether a victim must be steered",
}

OPTION_LIST: Dict[str, List[Option]] = {
    "disposition": DISPOSITIONS,
    "exposure": EXPOSURES,
    "boundary": BOUNDARIES,
    "effect": EFFECTS,
    "gate": GATES,
    "scope": SCOPES,
    "durability": DURABILITIES,
    "cooperation": COOPERATIONS,
}

ENUM_IDS: Dict[str, frozenset[str]] = {
    key: frozenset(option["id"] for option in options)
    for key, options in OPTION_LIST.items()
}


def effect_band(effect: str) -> int:
    for band in BANDS:
        effects = band["effects"]
        if isinstance(effects, list) and effect in effects:
            rank = band["rank"]
            return int(rank) if isinstance(rank, int) else 0
    return 0


def band_label(effect: str) -> str:
    for band in BANDS:
        effects = band["effects"]
        if isinstance(effects, list) and effect in effects:
            label = band["label"]
            return str(label)
    return "No security property"


def label_for(axis: Axis, finding: FindingClass) -> str:
    if axis == "forbidden":
        return "Forbidden" if finding["forbidden"] else "Already permitted"
    if axis == "effectBand":
        return band_label(finding["effect"])
    options = OPTION_LIST[axis]
    value = finding[axis]  # type: ignore[literal-required]
    for option in options:
        if option["id"] == value:
            return option["label"]
    return str(value)


def rank_for(axis: Axis, finding: FindingClass) -> int:
    if axis == "forbidden":
        return 1 if finding["forbidden"] else 0
    if axis == "effectBand":
        return effect_band(finding["effect"])
    options = OPTION_LIST[axis]
    value = finding[axis]  # type: ignore[literal-required]
    for option in options:
        if option["id"] == value:
            return option["rank"]
    return 0
