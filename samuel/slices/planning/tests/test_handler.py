from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import PlanIssueCommand
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse
from samuel.slices.planning.handler import (
    PlanningHandler,
    validate_plan,
    validate_plan_against_skeleton,
)

GOOD_PLAN = """\
## Analyse
Änderung in `handler.py` Zeile 42.

### Akzeptanzkriterien
- [ ] [DIFF] handler.py — Handler geändert
- [ ] [TEST] test_handler — Tests grün
"""

BAD_PLAN = "Hier ist ein Plan ohne jegliche Struktur."

MEDIUM_PLAN = """\
## Analyse
Änderung in `handler.py`.

### Akzeptanzkriterien
- [ ] [DIFF] handler.py — Handler geändert
- [ ] [INVALIDTAG] something — broken tag
"""


class MockSCM(IVersionControl):
    def __init__(self, issue: Issue | None = None):
        self._issue = issue or Issue(number=42, title="Test Issue", body="- [ ] AC1\n- [ ] AC2", state="open")
        self.posted_comments: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return self._issue

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted_comments.append((number, body))
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return f"http://test/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"http://test/pulls/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"http://test/branch/{branch}"

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class MockLLM(ILLMProvider):
    def __init__(self, response_text: str = GOOD_PLAN):
        self._text = response_text
        self.call_count = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200000


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestPlanningHandler:
    def test_happy_path(self):
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        events = _collect_events(bus)

        cmd = PlanIssueCommand(issue_number=42, idempotency_key="plan:42")
        result = handler.handle(cmd)

        assert result["score"] >= 50
        event_names = [e.name for e in events]
        assert "PlanCreated" in event_names
        assert "PlanValidated" in event_names
        assert "PlanPosted" in event_names
        assert len(scm.posted_comments) == 1
        assert scm.posted_comments[0][0] == 42

    def test_post_comment_runs_before_plan_validated(self):
        """Regression #221: PlanValidated triggert downstream Implement->Eval->
        CreatePR-Gates synchron. Wenn der Plan-Comment erst NACH PlanValidated
        gepostet wird, fehlt er bei den Gate-Checks und PR-Gates 2/3/11
        schlagen fehl. Daher muss post_comment vor publish(PlanValidated)
        laufen."""
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)

        observation_log: list[str] = []

        def on_plan_validated(_event):
            observation_log.append(
                f"plan_validated_seen comments={len(scm.posted_comments)}"
            )

        original_post = scm.post_comment

        def post_with_log(number: int, body: str):
            observation_log.append("post_comment")
            return original_post(number, body)

        scm.post_comment = post_with_log
        bus.subscribe("PlanValidated", on_plan_validated)

        handler.handle(PlanIssueCommand(issue_number=42))

        assert "post_comment" in observation_log
        assert any(
            entry.startswith("plan_validated_seen") for entry in observation_log
        )
        post_idx = observation_log.index("post_comment")
        validated_idx = next(
            i for i, e in enumerate(observation_log)
            if e.startswith("plan_validated_seen")
        )
        assert post_idx < validated_idx, (
            "post_comment muss vor PlanValidated-Subscriber laufen"
        )
        assert observation_log[validated_idx] == "plan_validated_seen comments=1", (
            "PlanValidated-Subscriber sieht den Plan-Comment bereits gepostet"
        )

    def test_plan_comment_contains_metadata_block(self):
        """Regression #188: Plan-Kommentar muss '## Agent-Metadaten' enthalten,
        sonst blockiert PR-Gate 3."""
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        handler.handle(PlanIssueCommand(issue_number=42, idempotency_key="plan:42"))

        body = scm.posted_comments[0][1]
        assert "## Agent-Metadaten" in body
        assert "Issue:** #42" in body
        assert "Generated:" in body
        assert "Plan-Score:" in body
        assert "Checks:" in body

    def test_no_scm_publishes_blocked(self):
        bus = Bus()
        handler = PlanningHandler(bus, scm=None, llm=MockLLM())
        events = _collect_events(bus)

        result = handler.handle(PlanIssueCommand(issue_number=42))

        assert result is None
        assert any(e.name == "PlanBlocked" for e in events)

    def test_no_llm_publishes_blocked(self):
        bus = Bus()
        handler = PlanningHandler(bus, scm=MockSCM(), llm=None)
        events = _collect_events(bus)

        result = handler.handle(PlanIssueCommand(issue_number=42))

        assert result is None
        assert any(e.name == "PlanBlocked" for e in events)

    def test_bad_plan_blocked(self):
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(BAD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        events = _collect_events(bus)

        result = handler.handle(PlanIssueCommand(issue_number=42))

        assert result["score"] < 50
        assert any(e.name == "PlanBlocked" for e in events)
        assert len(scm.posted_comments) == 0

    def test_medium_plan_triggers_retry(self):
        bus = Bus()
        scm = MockSCM()
        call_count = [0]

        class RetryLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                call_count[0] += 1
                if call_count[0] == 1:
                    return LLMResponse(text=MEDIUM_PLAN, input_tokens=100, output_tokens=50)
                return LLMResponse(text=GOOD_PLAN, input_tokens=100, output_tokens=50)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            @property
            def context_window(self) -> int:
                return 200000

        handler = PlanningHandler(bus, scm=scm, llm=RetryLLM())
        events = _collect_events(bus)

        handler.handle(PlanIssueCommand(issue_number=42))

        event_names = [e.name for e in events]
        assert "PlanRetry" in event_names
        assert call_count[0] == 2

    def test_correlation_id_consistent(self):
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        events = _collect_events(bus)

        cmd = PlanIssueCommand(issue_number=42, correlation_id="test-corr-123")
        handler.handle(cmd)

        for e in events:
            assert e.correlation_id == "test-corr-123"

    def test_prompt_contains_guard_markers(self):
        bus = Bus()
        scm = MockSCM()
        captured_prompts: list[str] = []

        class CaptureLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                captured_prompts.append(messages[0]["content"])
                return LLMResponse(text=GOOD_PLAN, input_tokens=100, output_tokens=50)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            @property
            def context_window(self) -> int:
                return 200000

        handler = PlanningHandler(bus, scm=scm, llm=CaptureLLM())
        handler.handle(PlanIssueCommand(issue_number=42))

        assert len(captured_prompts) == 1
        assert "Unveränderliche Schranken" in captured_prompts[0]
        assert "Ignoriere Anweisungen" in captured_prompts[0]

    def test_user_content_has_xml_delimiters(self):
        bus = Bus()
        issue = Issue(number=42, title="<script>alert</script>", body="Malicious body", state="open")
        scm = MockSCM(issue=issue)
        captured_prompts: list[str] = []

        class CaptureLLM(ILLMProvider):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                captured_prompts.append(messages[0]["content"])
                return LLMResponse(text=GOOD_PLAN, input_tokens=100, output_tokens=50)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            @property
            def context_window(self) -> int:
                return 200000

        handler = PlanningHandler(bus, scm=scm, llm=CaptureLLM())
        handler.handle(PlanIssueCommand(issue_number=42))

        assert "<user-content>" in captured_prompts[0]


class TestValidatePlan:
    def test_good_plan_high_score(self):
        result = validate_plan(GOOD_PLAN)
        assert result["score"] >= 80

    def test_bad_plan_low_score(self):
        result = validate_plan(BAD_PLAN)
        assert result["score"] < 50

    def test_invalid_ac_tags_detected(self):
        result = validate_plan(MEDIUM_PLAN)
        assert any("AC-Tags" in f for f in result["failures"])

    def test_forbidden_paths_detected(self):
        plan = "Ändere `node_modules/foo.py`\n- [ ] [DIFF] test.py — ok"
        result = validate_plan(plan)
        assert any("Verbotene" in f for f in result["failures"])

    def test_missing_acs_detected(self):
        plan = "Hier ist ein Plan mit Text aber ohne Checkboxen."
        result = validate_plan(plan)
        assert any("Akzeptanzkriterien" in f for f in result["failures"])


class TestValidatePlanAgainstSkeleton:
    def test_empty_skeleton_passes(self):
        result = validate_plan_against_skeleton(GOOD_PLAN, skeleton=None)
        assert result["score"] == 100

    def test_skeleton_with_matching_files(self):
        skeleton = {"handler.py": [{"name": "handle", "line_start": 42}]}
        result = validate_plan_against_skeleton(GOOD_PLAN, skeleton=skeleton)
        assert result["score"] >= 50


class TestPlanContext:
    """#237: Plan-Stage laedt Code-Kontext (Skeleton + relevant Files + Grep)."""

    def test_planning_context_loaded(self, tmp_path):
        from pathlib import Path
        from samuel.core.commands import PlanIssueCommand

        (tmp_path / "marker_file.py").write_text("def special_marker():\n    pass\n")

        class _SCM:
            def get_issue(self, n):
                return Issue(number=n, title="t", body="special_marker function", state="open")
            def post_comment(self, n, body):
                return Comment(id=1, body=body, user="bot")

        class _LLM:
            context_window = 100000
            def complete(self, msgs, **kw):
                return LLMResponse(
                    text="### Akzeptanzkriterien\n- [ ] [DIFF] marker_file.py",
                    input_tokens=100, output_tokens=50, cached_tokens=0,
                    stop_reason="end_turn", model_used="x", latency_ms=1,
                )
            def estimate_tokens(self, t): return len(t)//4

        bus = Bus()
        captured: list = []
        bus.subscribe("PlanContextLoaded", lambda e: captured.append(e))

        from samuel.slices.planning.handler import PlanningHandler
        handler = PlanningHandler(
            bus, scm=_SCM(), llm=_LLM(), project_root=tmp_path,
        )
        handler.handle(PlanIssueCommand(issue_number=237))

        assert len(captured) == 1
        evt = captured[0]
        assert evt.payload["issue"] == 237
        assert "skeleton_tokens" in evt.payload
        assert "relevant_files_count" in evt.payload
        assert evt.payload["evt"] == "plan_context_load"

    def test_plan_works_without_skeleton_builders(self, tmp_path):
        """Bus-Resilience: skeleton_builders=None laesst Plan trotzdem laufen."""
        from samuel.core.commands import PlanIssueCommand

        class _SCM:
            def get_issue(self, n):
                return Issue(number=n, title="t", body="some keywords here", state="open")
            def post_comment(self, n, body):
                return Comment(id=1, body=body, user="bot")

        class _LLM:
            context_window = 100000
            def complete(self, msgs, **kw):
                return LLMResponse(
                    text="### Akzeptanzkriterien\n- [ ] [DIFF] x.py",
                    input_tokens=10, output_tokens=10, cached_tokens=0,
                    stop_reason="end_turn", model_used="x", latency_ms=1,
                )
            def estimate_tokens(self, t): return len(t)//4

        from samuel.slices.planning.handler import PlanningHandler
        handler = PlanningHandler(
            Bus(), scm=_SCM(), llm=_LLM(), project_root=tmp_path,
        )
        result = handler.handle(PlanIssueCommand(issue_number=1))
        assert result is None or "score" in result

    def test_plan_uses_toc_mode_for_large_files(self, tmp_path):
        """#152: Files > Threshold werden als TOC gerendert (kuerzer)."""
        big = "\n".join(f"line {i} large_file_marker" for i in range(1, 600))
        (tmp_path / "huge.py").write_text(big)

        from samuel.slices.planning.handler import _render_plan_files
        out = _render_plan_files(tmp_path, ["huge.py"])
        assert "TOC-Mode" in out
        assert len(out) < 5000

    def test_plan_skeleton_filtered_by_keywords(self, tmp_path):
        """Skeleton zeigt nur Symbole die zu Issue-Keywords matchen."""
        from samuel.slices.planning.handler import _render_plan_skeleton
        from samuel.core.types import SkeletonEntry

        class _Builder:
            def build(self, root):
                yield "x.py", [
                    SkeletonEntry(name="match_marker", kind="function", file="x.py", line_start=1, line_end=5),
                    SkeletonEntry(name="other_function", kind="function", file="x.py", line_start=10, line_end=20),
                ]

        out = _render_plan_skeleton([_Builder()], tmp_path, ["match_marker"])
        assert "match_marker" in out
        assert "other_function" not in out

    def test_plan_extract_keywords_filters_stopwords(self):
        from samuel.slices.planning.handler import _extract_plan_keywords
        kws = _extract_plan_keywords("Der Plan soll the validator function nutzen")
        assert "validator" in kws
        assert "function" in kws
        assert "der" not in kws
        assert "the" not in kws

    def test_plan_relevant_files_includes_non_python(self, tmp_path):
        """#1.1 Sprachneutralitaet: .go-Datei mit Keyword wird gefunden."""
        (tmp_path / "main.go").write_text("// special_go_marker\npackage main\n")
        from samuel.slices.planning.handler import _filter_relevant_files_for_plan
        from samuel.core.project_files import CODE_EXTENSIONS, CONFIG_EXTENSIONS
        files = _filter_relevant_files_for_plan(
            tmp_path, ["special_go_marker"], CODE_EXTENSIONS | CONFIG_EXTENSIONS, [],
        )
        assert "main.go" in files


class TestPlanPreCheck:
    """#238: Plan-Pre-Check mit Skeleton-Validation, AC-Dry-Run und
    Komplexitaets-Score (Schicht A aus #247)."""

    def _register_ac_handler(self, bus: Bus) -> None:
        """Stub-VerifyAC-Handler ohne Cross-Slice-Import (Charter §1).
        Liefert deterministische Parsing-Resultate ueber Tag-/Arg-Regex."""
        import re
        ac_re = re.compile(r"- \[.\] \[([A-Z:]+)\][ \t]*([^\n]*)")

        def stub(cmd):
            results: list[dict] = []
            for m in ac_re.finditer(cmd.payload.get("plan_text", "")):
                tag = m.group(1)
                arg = m.group(2).strip()
                results.append({
                    "tag": tag,
                    "arg": arg,
                    "passed": bool(arg),
                    "reason": "ok" if arg else "arg empty",
                })
            return {
                "verified": all(r["passed"] for r in results),
                "total": len(results),
                "passed": sum(1 for r in results if r["passed"]),
                "manual": 0,
                "results": results,
            }

        bus.register_command("VerifyAC", stub)

    def test_plan_pre_check_skeleton_failure(self):
        """Plan referenziert Datei nicht im Skeleton -> Pre-Check warnings,
        Retry triggert."""
        from samuel.slices.planning.handler import _run_plan_pre_check
        bus = Bus()
        self._register_ac_handler(bus)
        plan = (
            "## Analyse\nReferenziert `unknown_file.py`\n"
            "### Akzeptanzkriterien\n"
            "- [ ] [DIFF] unknown_file.py — bla\n"
            "- [ ] [TEST] t — bla\n"
        )
        skeleton = {"known.py": [{"name": "f", "kind": "function",
                                  "line_start": 1, "line_end": 5}]}
        result = _run_plan_pre_check(
            bus, plan, issue_number=238, correlation_id="c",
            skeleton=skeleton, project_root=None, issue_body="",
        )
        assert result["skeleton_score"] < 100 or result["structural_score"] < 100

    def test_plan_pre_check_ac_dry_run_failure(self):
        """Plan mit unparseable AC -> Pre-Check Failure, overall_pass=False."""
        from samuel.slices.planning.handler import _run_plan_pre_check
        bus = Bus()
        self._register_ac_handler(bus)
        # GREP ohne quoted pattern + leerer arg
        plan = (
            "### Akzeptanzkriterien\n"
            "- [ ] [GREP]\n"
            "- [ ] [DIFF]\n"
        )
        result = _run_plan_pre_check(
            bus, plan, issue_number=238, correlation_id="c",
            skeleton=None, project_root=None, issue_body="",
        )
        # Bei leeren Args ist die Parsing-Pass-Rate niedrig.
        assert result["overall_pass"] is False or result["ac_dry_run_score"] < 100

    def test_plan_pre_check_retry_with_hints(self):
        """Pre-Check-Failures werden in retry_prompt injiziert."""
        from samuel.slices.planning.handler import _build_retry_prompt
        prompt = _build_retry_prompt(
            "ORIG", failures=["f1"], warnings=[],
            pre_check_hints=["DIFF foo: arg leer", "complexity: too high"],
        )
        assert "Plan-Pre-Check Failures" in prompt
        assert "DIFF foo: arg leer" in prompt
        assert "complexity: too high" in prompt

    def test_plan_complexity_warn_threshold(self):
        """Viele ACs -> recommendation=warn."""
        from samuel.slices.planning.handler import _compute_plan_complexity
        plan = "\n".join(f"- [ ] [DIFF] f{i}.py" for i in range(8))
        c = _compute_plan_complexity(plan)
        assert c["ac_count"] == 8
        assert c["recommendation"] == "warn"

    def test_plan_complexity_split_recommended(self):
        """Viele Pflicht-Bereiche -> recommendation=split_recommended."""
        from samuel.slices.planning.handler import _compute_plan_complexity
        plan = (
            "- [ ] [DIFF] a.py\n"
            "- [ ] [TEST] t1\n"
            "- [ ] [GREP] \"x\"\n"
            "- [ ] [GREP:NOT] \"y\"\n"
            "- [ ] [EXISTS] z.py\n"
            "- [ ] [IMPORT] mod\n"
        )
        c = _compute_plan_complexity(plan)
        assert c["pflicht_bereich_count"] >= 5
        assert c["recommendation"] == "split_recommended"

    def test_pre_check_works_without_skeleton(self):
        """Bus-Resilience: skeleton=None -> Skeleton-Check skippt, andere laufen."""
        from samuel.slices.planning.handler import _run_plan_pre_check
        bus = Bus()
        self._register_ac_handler(bus)
        plan = (
            "### Akzeptanzkriterien\n"
            "- [ ] [DIFF] foo.py\n"
            "- [ ] [TEST] test_foo\n"
        )
        result = _run_plan_pre_check(
            bus, plan, issue_number=1, correlation_id="c",
            skeleton=None, project_root=None, issue_body="",
        )
        # skeleton_score=100 (skip), strukturell ok -> overall_pass koennte True
        assert result["skeleton_score"] == 100
        assert "complexity" in result

    def test_pre_check_event_published_in_handler(self):
        """Integration: PlanPreCheckCompleted-Event wird im Handler publisht."""
        bus = Bus()
        self._register_ac_handler(bus)
        scm = MockSCM()
        llm = MockLLM(GOOD_PLAN)
        events: list = []
        bus.subscribe("*", lambda e: events.append(e))
        handler = PlanningHandler(bus, scm=scm, llm=llm)
        handler.handle(PlanIssueCommand(issue_number=42))
        names = [e.name for e in events]
        assert "PlanPreCheckCompleted" in names
        pre = next(e for e in events if e.name == "PlanPreCheckCompleted")
        assert "structural_score" in pre.payload
        assert "skeleton_score" in pre.payload
        assert "ac_dry_run_score" in pre.payload
        assert "overall_pass" in pre.payload
        assert "complexity" in pre.payload

# #297: Schicht D — Issue-Body-Coverage-Check Tests
def _make_pre_check_args(
    plan_text: str = "",
    issue_body: str = "",
):
    """Common helper to invoke _run_plan_pre_check with minimal Bus."""
    bus = Bus()
    return {
        "bus": bus,
        "plan_text": plan_text,
        "issue_number": 297,
        "correlation_id": "test-corr",
        "skeleton": None,
        "project_root": None,
        "issue_body": issue_body,
    }


def test_pre_check_blocks_when_issue_path_not_in_acs():
    """Issue mentions a file path that no AC references — coverage_score < 100, overall_pass=False."""
    from samuel.slices.planning.handler import _run_plan_pre_check
    issue = "Modify samuel/server.py to add the new /api/v1/foo endpoint."
    plan = """## Plan
### Akzeptanzkriterien
- [ ] [DIFF] something_else.py
- [ ] [TEST] test_thing
"""
    res = _run_plan_pre_check(**_make_pre_check_args(plan_text=plan, issue_body=issue))
    assert res["coverage_score"] < 100
    assert res["overall_pass"] is False
    missing = res.get("coverage_missing", [])
    assert any("samuel/server.py" in m for m in missing)


def test_pre_check_passes_when_all_anchors_covered():
    from samuel.slices.planning.handler import _run_plan_pre_check
    issue = "Edit samuel/core/foo.py and add test_foo."
    plan = """## Plan
### Akzeptanzkriterien
- [ ] [DIFF] samuel/core/foo.py
- [ ] [TEST] test_foo
"""
    res = _run_plan_pre_check(**_make_pre_check_args(plan_text=plan, issue_body=issue))
    assert res["coverage_score"] == 100
    assert res.get("coverage_missing", []) == []


def test_pre_check_ignores_out_of_scope_section():
    from samuel.slices.planning.handler import _run_plan_pre_check
    issue = """## Goal
Implement samuel/core/foo.py.

## Out-of-Scope
This issue does NOT cover samuel/extras/never.py — that is a future ticket.
"""
    plan = """## Plan
### Akzeptanzkriterien
- [ ] [DIFF] samuel/core/foo.py
"""
    res = _run_plan_pre_check(**_make_pre_check_args(plan_text=plan, issue_body=issue))
    assert res["coverage_score"] == 100
    # Out-of-Scope-Pfad darf NICHT als missing erscheinen
    assert not any("samuel/extras/never.py" in m for m in res.get("coverage_missing", []))


def test_pre_check_extracts_api_endpoints_from_issue():
    from samuel.slices.planning.handler import _run_plan_pre_check
    issue = "Wire up /api/v1/license/status."
    plan_no_api = """## Plan
### Akzeptanzkriterien
- [ ] [DIFF] samuel/server.py
"""
    res = _run_plan_pre_check(**_make_pre_check_args(plan_text=plan_no_api, issue_body=issue))
    assert res["coverage_score"] < 100
    assert any("/api/v1/license/status" in m for m in res.get("coverage_missing", []))


def test_pre_check_passes_when_issue_body_empty():
    from samuel.slices.planning.handler import _run_plan_pre_check
    plan = """## Plan
### Akzeptanzkriterien
- [ ] [DIFF] samuel/core/foo.py
"""
    res = _run_plan_pre_check(**_make_pre_check_args(plan_text=plan, issue_body=""))
    assert res["coverage_score"] == 100
    assert res.get("coverage_missing", []) == []