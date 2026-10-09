from __future__ import annotations

import pytest

from samuel.core.acceptance import (
    AcceptanceApproval,
    AcceptanceContract,
    PlanningSourceSnapshot,
    PlanRevocation,
    canonical_acceptance_source,
    latest_active_plan,
    parse_acceptance_contract,
    parse_grep_criterion_argument,
    parse_test_criterion_argument,
    render_plan_revocation,
    render_planning_source,
    text_digest,
)
from samuel.core.types import Comment

PLAN = """## Plan

### Änderungsscope
Scope-Schema: 1
- [FILE] `samuel/core/types.py`
Architecture-Expansion: disabled

### Akzeptanzkriterien
- [ ] [DIFF] samuel/core/types.py — Datei geändert
- [x] [MANUAL] Dashboard gegenprüfen
"""


def test_contract_has_stable_ids_revision_modes_and_checkbox_independent_hash():
    contract = parse_acceptance_contract(PLAN)
    manipulated = parse_acceptance_contract(PLAN.replace("[ ]", "[x]").replace("[x]", "[X]"))

    assert contract.schema_version == 2
    assert contract.scope is not None
    assert contract.scope.entries[0].value == "samuel/core/types.py"
    assert contract.revision == "1"
    assert contract.contract_hash == manipulated.contract_hash
    assert [item.criterion_id for item in contract.criteria] == [
        item.criterion_id for item in manipulated.criteria
    ]
    assert [item.mode for item in contract.criteria] == ["automatic", "manual"]
    assert "[x]" not in canonical_acceptance_source(PLAN).lower()


def test_contract_change_invalidates_hash_and_changed_criterion_id():
    original = parse_acceptance_contract(PLAN)
    changed = parse_acceptance_contract(PLAN.replace("Dashboard gegenprüfen", "CLI gegenprüfen"))

    assert original.contract_hash != changed.contract_hash
    assert original.criteria[0].criterion_id == changed.criteria[0].criterion_id
    assert original.criteria[1].criterion_id != changed.criteria[1].criterion_id


def test_source_bound_contract_round_trips_and_changes_with_base_commit():
    source = PlanningSourceSnapshot(
        schema_version=1,
        repository="https://scm.example/owner/repo",
        base_ref="main",
        base_sha="a" * 40,
        issue_digest="sha256:" + "b" * 64,
    )
    contract = parse_acceptance_contract(
        PLAN,
        source_snapshot=source,
        allow_embedded_source=False,
    )
    posted = (
        "## Plan für Issue #42\n\n**Status:** Geprüft.\n\n"
        f"{PLAN}\n\n---\n\n{render_planning_source(source)}\n\n## Agent-Metadaten"
    )

    assert contract.schema_version == 2
    assert contract.source_snapshot == source
    assert parse_acceptance_contract(posted) == contract
    assert AcceptanceContract.from_dict(contract.as_dict()) == contract

    moved = PlanningSourceSnapshot(
        schema_version=1,
        repository=source.repository,
        base_ref=source.base_ref,
        base_sha="c" * 40,
        issue_digest=source.issue_digest,
    )
    assert parse_acceptance_contract(PLAN, source_snapshot=moved).contract_hash != (
        contract.contract_hash
    )


def test_source_bound_contract_round_trips_with_terminal_markdown_separator():
    source = PlanningSourceSnapshot(
        schema_version=1,
        repository="https://scm.example/owner/repo",
        base_ref="main",
        base_sha="a" * 40,
        issue_digest="sha256:" + "b" * 64,
    )
    plan = PLAN.rstrip() + "\n\n---"
    contract = parse_acceptance_contract(
        plan,
        source_snapshot=source,
        allow_embedded_source=False,
    )
    posted = (
        "## Plan für Issue #42\n\n**Status:** Geprüft.\n\n"
        f"{plan}\n\n---\n\n{render_planning_source(source)}\n\n## Agent-Metadaten"
    )

    assert parse_acceptance_contract(posted) == contract


def test_llm_plan_cannot_supply_its_own_source_snapshot():
    source = PlanningSourceSnapshot(
        schema_version=1,
        repository="https://scm.example/owner/repo",
        base_ref="main",
        base_sha="a" * 40,
        issue_digest="sha256:" + "b" * 64,
    )

    with pytest.raises(ValueError, match="must not provide"):
        parse_acceptance_contract(
            f"{PLAN}\n{render_planning_source(source)}",
            source_snapshot=source,
            allow_embedded_source=False,
        )


def test_posted_plan_wrapper_and_metadata_do_not_create_a_second_contract():
    plan = """### Änderungsscope
Scope-Schema: 1
- [FILE] `module.py`
Architecture-Expansion: disabled

### Akzeptanzkriterien
- [ ] [DIFF] module.py"""
    posted = (
        "## Plan für Issue #42\n\n"
        "**Status:** Geprüft — wartet auf menschliche Freigabe.\n\n"
        f"{plan}\n\n---\n\nAgent-Metadaten\n- Score: 100"
    )

    assert parse_acceptance_contract(posted) == parse_acceptance_contract(plan)


def test_duplicate_criteria_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        parse_acceptance_contract("- [ ] [TEST] test_one\n- [x] [TEST] test_one")


@pytest.mark.parametrize(
    "criterion",
    [
        "test_one",
        "TestBoard.test_highest_score_first — focused test",
        "tests/test_board.py::test_highest_score_first",
        "tests/test_board.py::TestBoard::test_highest_score_first",
    ],
)
def test_test_argument_accepts_only_verifier_supported_selectors(criterion: str):
    assert parse_test_criterion_argument(criterion)
    parse_acceptance_contract(f"- [ ] [TEST] {criterion}")


@pytest.mark.parametrize(
    "criterion",
    [
        "tests/test_board.py",
        "../tests/test_board.py::test_value",
        "/tests/test_board.py::test_value",
        "tests/./test_board.py::test_value",
    ],
)
def test_contract_rejects_test_selectors_the_verifier_cannot_execute(criterion: str):
    with pytest.raises(ValueError, match="rejected"):
        parse_acceptance_contract(f"- [ ] [TEST] {criterion}")


@pytest.mark.parametrize(
    ("criterion", "pattern"),
    [
        ('"foo bar"', "foo bar"),
        ('"foo" — repository-wide marker', "foo"),
        ("'token = \"synthetic-demo-value\"'", 'token = "synthetic-demo-value"'),
        ('`token = "synthetic-demo-value"`', 'token = "synthetic-demo-value"'),
        ("class Handler", "class Handler"),
        ("'legacy' : removal description", "legacy"),
    ],
)
def test_grep_argument_is_repository_wide_and_keeps_unquoted_multiword_patterns(
    criterion: str, pattern: str
):
    assert parse_grep_criterion_argument(criterion) == pattern


@pytest.mark.parametrize("tag", ["GREP", "GREP:NOT"])
def test_contract_rejects_apparent_grep_path_suffix(tag: str):
    plan = f'- [ ] [{tag}] "marker" game/domain/board.py'

    with pytest.raises(ValueError, match="does not support a path or other suffix"):
        parse_acceptance_contract(plan)


@pytest.mark.parametrize("tag", ["GREP", "GREP:NOT"])
def test_contract_accepts_markdown_inline_code_grep_pattern(tag: str):
    plan = f'- [ ] [{tag}] `token = "synthetic-demo-value"`'

    contract = parse_acceptance_contract(plan)

    assert contract.criteria[0].text == '`token = "synthetic-demo-value"`'
    assert parse_grep_criterion_argument(contract.criteria[0].text) == (
        'token = "synthetic-demo-value"'
    )


@pytest.mark.parametrize(
    "criterion",
    ["`unterminated", "`marker` game/domain/board.py", "``"],
)
def test_grep_rejects_incomplete_or_ambiguous_markdown_wrapper(criterion: str):
    with pytest.raises(ValueError):
        parse_grep_criterion_argument(criterion)


def test_grep_rejects_whitespace_only_pattern():
    with pytest.raises(ValueError, match="non-empty pattern"):
        parse_grep_criterion_argument('"   "')


def test_grep_rejects_escaped_delimiter_with_actionable_existing_syntax():
    with pytest.raises(ValueError, match="wrap a pattern containing double quotes in single"):
        parse_grep_criterion_argument('"token = \\"synthetic-demo-value\\""')


@pytest.mark.parametrize(
    "path",
    ["../escape.py", "/absolute.py", "samuel\\core.py", "samuel/./core.py"],
)
def test_scope_rejects_non_canonical_and_traversal_paths(path: str):
    plan = f"""### Änderungsscope
Scope-Schema: 1
- [FILE] `{path}`
Architecture-Expansion: disabled
"""
    with pytest.raises(ValueError):
        parse_acceptance_contract(plan)


def test_scope_rejects_missing_empty_and_ambiguous_sections():
    assert parse_acceptance_contract("- [ ] [TEST] test_one").scope is None
    with pytest.raises(ValueError):
        parse_acceptance_contract(
            "### Änderungsscope\nScope-Schema: 1\nArchitecture-Expansion: disabled"
        )
    with pytest.raises(ValueError, match="multiple"):
        parse_acceptance_contract(
            """### Änderungsscope
Scope-Schema: 1
- [FILE] `a.py`
Architecture-Expansion: disabled
### Änderungsscope
Scope-Schema: 1
- [FILE] `b.py`
Architecture-Expansion: disabled
"""
        )


def test_approval_is_bound_to_exact_contract():
    contract = parse_acceptance_contract(PLAN)
    approval = AcceptanceApproval(
        state="approved",
        actor="alice",
        method="comment",
        source_id="comment:17",
        approved_at="2026-08-25T10:00:00Z",
        contract_hash=contract.contract_hash,
        plan_comment_id=16,
    )
    approved = contract.with_approval(approval)

    assert AcceptanceContract.from_dict(approved.as_dict()) == approved
    with pytest.raises(ValueError, match="different"):
        contract.with_approval(
            AcceptanceApproval(
                state="approved",
                actor="alice",
                method="comment",
                source_id="comment:17",
                approved_at="2026-08-25T10:00:00Z",
                contract_hash="sha256:" + "0" * 64,
                plan_comment_id=16,
            )
        )


def test_revocation_binds_comment_identity_even_for_identical_replacement_plan():
    contract = parse_acceptance_contract(PLAN)
    revocation = PlanRevocation(
        schema_version=1,
        plan_comment_id=10,
        contract_hash=contract.contract_hash,
        reason_digest=text_digest("Plan ist unvollständig"),
        revoked_at="2026-09-17T10:00:00Z",
        actor="operator:local-cli",
    )
    comments = [
        Comment(id=10, body=PLAN, user="bot", created_at="2026-09-17T09:00:00Z"),
        Comment(id=11, body=render_plan_revocation(revocation), user="bot"),
        Comment(id=12, body=PLAN, user="bot", created_at="2026-09-17T11:00:00Z"),
    ]

    active = latest_active_plan(comments)

    assert active is not None
    assert active[0].id == 12
    assert active[1].contract_hash == contract.contract_hash


def test_revocation_marker_from_different_actor_cannot_revoke_plan():
    contract = parse_acceptance_contract(PLAN)
    marker = render_plan_revocation(
        PlanRevocation(
            schema_version=1,
            plan_comment_id=10,
            contract_hash=contract.contract_hash,
            reason_digest=text_digest("forged"),
            revoked_at="2026-09-17T10:00:00Z",
            actor="operator:local-cli",
        )
    )

    active = latest_active_plan(
        [
            Comment(id=10, body=PLAN, user="example-bot"),
            Comment(id=11, body=marker, user="mallory"),
        ]
    )

    assert active is not None
    assert active[0].id == 10


def test_block_comment_with_agent_metadata_is_not_an_active_plan():
    block_comment = """## Plan blockiert — Issue #80

**Grund:** git_remote_not_authorized

**Was jetzt zu tun ist:**

Den vollstaendigen Kontext liefert das Audit-Log.

---

## Agent-Metadaten
- **Issue:** #80
- **Generated-By:** S.A.M.U.E.L.@2.0.0a24
"""

    assert latest_active_plan([Comment(id=42960, body=block_comment, user="bot")]) is None
