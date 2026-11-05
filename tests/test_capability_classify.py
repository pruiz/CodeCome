from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from findings.capability.classify import (
    compare_queue,
    decide,
    decision_for,
    describe_finding,
    parse_capability_block,
    to_capability_yaml,
)
from findings.capability.taxonomy import FindingClass


EXAMPLES: dict[str, FindingClass] = {
    "ci-script-injection": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "build",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "execute-on-host",
        "boundary": "host",
        "scope": "fleet",
        "durability": "reexecutes",
    },
    "stored-xss-admin": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "execute-in-app",
        "boundary": "higher-principal",
        "scope": "tenant",
        "durability": "reexecutes",
    },
    "ssrf-metadata": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "read-secrets",
        "boundary": "host",
        "scope": "fleet",
        "durability": "once",
    },
    "path-traversal-env": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "read-secrets",
        "boundary": "host",
        "scope": "tenant",
        "durability": "once",
    },
    "sqli-write-role": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "write-security",
        "boundary": "higher-principal",
        "scope": "one-principal",
        "durability": "persists",
    },
    "idor-password-hashes": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "read-secrets",
        "boundary": "other-principal",
        "scope": "tenant",
        "durability": "once",
    },
    "sqli-read-rows": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "read-sensitive",
        "boundary": "other-principal",
        "scope": "tenant",
        "durability": "once",
    },
    "unauth-record-write": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "write-data",
        "boundary": "other-principal",
        "scope": "one-object",
        "durability": "persists",
    },
    "unauth-comment": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "write-data",
        "boundary": "service",
        "scope": "one-object",
        "durability": "persists",
    },
    "internet-status": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "read-public",
        "boundary": "service",
        "scope": "one-object",
        "durability": "once",
    },
    "local-parser-rce": {
        "forbidden": True,
        "disposition": "live",
        "exposure": "local",
        "gate": "none",
        "cooperation": "aimed",
        "effect": "execute-on-host",
        "boundary": "self",
        "scope": "one-principal",
        "durability": "once",
    },
    "debug-shell-dormant": {
        "forbidden": True,
        "disposition": "dormant",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "execute-on-host",
        "boundary": "host",
        "scope": "fleet",
        "durability": "reexecutes",
    },
    "unreleased-rce": {
        "forbidden": True,
        "disposition": "not-shipped",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "execute-on-host",
        "boundary": "host",
        "scope": "fleet",
        "durability": "reexecutes",
    },
    "self-xss": {
        "forbidden": False,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "execute-in-app",
        "boundary": "self",
        "scope": "one-principal",
        "durability": "once",
    },
    "admin-intended-delete": {
        "forbidden": False,
        "disposition": "live",
        "exposure": "internet",
        "gate": "privileged",
        "cooperation": "ambient",
        "effect": "destroy",
        "boundary": "service",
        "scope": "one-object",
        "durability": "persists",
    },
}


def worse(winner_id: str, loser_id: str, policy: str) -> None:
    winner = EXAMPLES[winner_id]
    loser = EXAMPLES[loser_id]
    assert compare_queue(winner, loser, policy) < 0, (
        f"{winner_id} should outrank {loser_id} on the {policy} queue"
    )


def test_service_queue_examples() -> None:
    worse("idor-password-hashes", "unauth-comment", "service")
    worse("sqli-read-rows", "unauth-comment", "service")
    worse("unauth-record-write", "sqli-read-rows", "service")
    worse("stored-xss-admin", "idor-password-hashes", "service")
    worse("path-traversal-env", "stored-xss-admin", "service")
    worse("sqli-write-role", "idor-password-hashes", "service")
    worse("ci-script-injection", "stored-xss-admin", "service")
    worse("internet-status", "debug-shell-dormant", "service")
    worse("debug-shell-dormant", "unreleased-rce", "service")
    worse("internet-status", "admin-intended-delete", "service")
    worse("internet-status", "self-xss", "service")
    worse("internet-status", "local-parser-rce", "service")


def test_service_queue_tension() -> None:
    decision = decide(EXAMPLES["internet-status"], EXAMPLES["local-parser-rce"], "service")
    assert decision["winner"] == "a"
    assert decision["axis"] == "exposure"
    assert decision["tension"]
    assert "specific outcome" in decision["tension"] or "kind of power" in decision["tension"]


def test_local_program_queue() -> None:
    worse("local-parser-rce", "internet-status", "local-program")
    worse("internet-status", "unreleased-rce", "local-program")


def test_describe_finding_sentences() -> None:
    sentence = describe_finding(EXAMPLES["sqli-read-rows"])
    assert "Production runs this code" in sentence
    assert "any signed-in account can read private information" in sentence
    assert "another principal at the same level" in sentence
    for word in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "CVSS"):
        assert word not in sentence

    dormant = describe_finding(EXAMPLES["debug-shell-dormant"])
    assert "nothing that runs enters it today" in dormant
    assert "If that changed" in dormant
    assert "could run their own code" in dormant

    permitted = describe_finding(EXAMPLES["admin-intended-delete"])
    assert "not a vulnerability" in permitted


def test_capability_yaml_round_trip() -> None:
    original = EXAMPLES["ssrf-metadata"]
    yaml_text = to_capability_yaml(original)
    block: dict = {"forbidden": True}
    for line in yaml_text.splitlines()[1:]:
        key, value = line.strip().split(":", 1)
        value = value.strip()
        if key == "forbidden":
            block[key] = value == "true"
        else:
            block[key] = value
    parsed = parse_capability_block(block)
    assert parsed["ok"] is True
    assert parsed["finding"] == original


def test_parse_capability_rejects_unknown_effect() -> None:
    parsed = parse_capability_block(
        {
            "forbidden": True,
            "disposition": "live",
            "exposure": "internet",
            "gate": "none",
            "cooperation": "ambient",
            "effect": "critical",
            "boundary": "host",
            "scope": "fleet",
            "durability": "once",
        }
    )
    assert parsed["ok"] is False
    assert "effect" in parsed["error"]


def test_parse_new_effects() -> None:
    for effect in ("deny", "bypass-control"):
        parsed = parse_capability_block(
            {
                "forbidden": True,
                "disposition": "live",
                "exposure": "internet",
                "gate": "none",
                "cooperation": "ambient",
                "effect": effect,
                "boundary": "service",
                "scope": "tenant",
                "durability": "once",
            }
        )
        assert parsed["ok"] is True
        assert parsed["finding"]["effect"] == effect


def test_decision_fix_now_takeover_effects() -> None:
    assert decision_for(EXAMPLES["path-traversal-env"]) == "fix-now"
    assert decision_for(EXAMPLES["stored-xss-admin"]) == "fix-now"
    assert decision_for(EXAMPLES["debug-shell-dormant"]) == "fix-now"


def test_decision_plan_not_shipped_and_mild() -> None:
    assert decision_for(EXAMPLES["unreleased-rce"]) == "plan"
    assert decision_for(EXAMPLES["internet-status"]) == "plan"
    assert decision_for(EXAMPLES["unauth-comment"]) == "plan"
    assert decision_for(EXAMPLES["admin-intended-delete"]) == "plan"
    assert decision_for(EXAMPLES["self-xss"]) == "plan"


def test_decision_wide_destroy_and_mass_sensitive_read() -> None:
    fleet_wipe: FindingClass = {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "destroy",
        "boundary": "other-tenant",
        "scope": "fleet",
        "durability": "persists",
    }
    one_row_destroy: FindingClass = {
        **fleet_wipe,
        "scope": "one-object",
        "boundary": "service",
    }
    mass_pii: FindingClass = {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "read-sensitive",
        "boundary": "other-tenant",
        "scope": "fleet",
        "durability": "once",
    }
    deny_only: FindingClass = {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "none",
        "cooperation": "ambient",
        "effect": "deny",
        "boundary": "service",
        "scope": "fleet",
        "durability": "once",
    }
    bypass: FindingClass = {
        "forbidden": True,
        "disposition": "live",
        "exposure": "internet",
        "gate": "any-account",
        "cooperation": "ambient",
        "effect": "bypass-control",
        "boundary": "service",
        "scope": "tenant",
        "durability": "persists",
    }

    assert decision_for(fleet_wipe) == "fix-now"
    assert decision_for(one_row_destroy) == "plan"
    assert decision_for(mass_pii) == "fix-now"
    assert decision_for(deny_only) == "plan"
    assert decision_for(bypass) == "fix-now"
    assert decision_for(EXAMPLES["sqli-read-rows"]) == "plan"


def test_destroy_sentence_no_longer_mentions_deny() -> None:
    sentence = describe_finding(
        {
            "forbidden": True,
            "disposition": "live",
            "exposure": "internet",
            "gate": "none",
            "cooperation": "ambient",
            "effect": "destroy",
            "boundary": "service",
            "scope": "one-object",
            "durability": "once",
        }
    )
    assert "delete or corrupt information" in sentence
    assert "deny service" not in sentence
