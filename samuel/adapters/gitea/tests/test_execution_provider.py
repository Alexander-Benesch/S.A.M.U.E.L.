from __future__ import annotations

import hashlib
import hmac
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from samuel.adapters.gitea.execution_provider import (
    GiteaExecutionProfile,
    GiteaExecutionProvider,
)
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.types import (
    ExecutionProviderError,
    ProviderCriterionEvidence,
    ProviderEvidence,
    ProviderRunReference,
    VerificationAuthority,
    VerificationCriterion,
    VerificationRequest,
)

KEY = b"k" * 32
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
WORKFLOW = b"name: trusted verification\n"


@pytest.fixture
def profile() -> GiteaExecutionProfile:
    return GiteaExecutionProfile(
        name="gitea-reference-v1",
        repository="owner/repo",
        workflow_id="samuel-verification.yml",
        workflow_path=".gitea/workflows/samuel-verification.yml",
        workflow_ref="main",
        workflow_digest=f"sha256:{hashlib.sha256(WORKFLOW).hexdigest()}",
        tool_digest="sha256:" + "2" * 64,
        environment_digest="sha256:" + "3" * 64,
        issuer="gitea-reference-control-plane",
        integrity_key_id="qualification-key-v1",
    )


@pytest.fixture
def verification_request(profile: GiteaExecutionProfile) -> VerificationRequest:
    subject = EvaluationSubject(
        repository="https://gitea.example/owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="1",
        policy_digest="sha256:" + "d" * 64,
    )
    authority = VerificationAuthority(
        issue_number=71,
        plan_comment_id=42536,
        contract_hash=subject.contract_hash,
        approval_source_id="label-event:9",
        approval_actor="maintainer",
        approval_method="scm_label_timeline",
    )
    return VerificationRequest.build(
        request_nonce="nonce-1",
        authorized_at=NOW.isoformat(),
        subject=subject,
        authority=authority,
        criteria=(
            VerificationCriterion(
                criterion_id="ac-1",
                tag="TEST",
                text="tests/test_demo.py::test_pipeline",
            ),
        ),
        policy_binding={"policy_digest": subject.policy_digest},
        provider_profile=profile.name,
        provider_profile_digest=profile.profile_digest,
        consumer_mode="passive_candidate",
    )


def adapter(profile: GiteaExecutionProfile, api: MagicMock) -> GiteaExecutionProvider:
    return GiteaExecutionProvider(
        api,
        base_url="https://gitea.example",
        profile=profile,
        integrity_key=KEY,
        clock=lambda: NOW,
    )


def test_shipped_execution_profile_is_disabled_and_unqualified() -> None:
    path = Path(__file__).parents[4] / "config" / "execution.json"
    value = json.loads(path.read_text(encoding="utf-8"))

    assert value["enabled"] is False
    assert value["required_qualified"] is False
    assert GiteaExecutionProfile.from_file(path) is None


def test_enabled_profile_requires_explicit_required_qualification(tmp_path) -> None:
    path = tmp_path / "execution.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "enabled": True,
                "required_qualified": False,
                "gitea": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not qualified"):
        GiteaExecutionProfile.from_file(path)


def test_enabled_profile_rejects_placeholder_trust_digests(tmp_path) -> None:
    shipped = Path(__file__).parents[4] / "config" / "execution.json"
    value = json.loads(shipped.read_text(encoding="utf-8"))
    value["enabled"] = True
    value["required_qualified"] = True
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="still a placeholder"):
        GiteaExecutionProfile.from_file(path)


def reference(verification_request: VerificationRequest) -> ProviderRunReference:
    return ProviderRunReference(
        provider="gitea-actions",
        repository="owner/repo",
        run_id="704",
        attempt=1,
        request_key=verification_request.request_key,
    )


def signed_evidence(
    verification_request: VerificationRequest,
    profile: GiteaExecutionProfile,
    *,
    signature: str | None = None,
) -> ProviderEvidence:
    evidence = ProviderEvidence(
        request_key=verification_request.request_key,
        subject=verification_request.subject,
        reference=reference(verification_request),
        provider_profile_digest=profile.profile_digest,
        workflow_digest=profile.workflow_digest,
        tool_digest=profile.tool_digest,
        environment_digest=profile.environment_digest,
        issuer=profile.issuer,
        issued_at=(NOW + timedelta(seconds=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        nonce=verification_request.request_nonce,
        criteria=(
            ProviderCriterionEvidence(
                criterion_id="ac-1",
                tag="TEST",
                status="passed",
                reason="trusted run passed",
                evidence_digest="sha256:" + "4" * 64,
            ),
        ),
        integrity={"scheme": "hmac-sha256", "key_id": profile.integrity_key_id, "signature": "x"},
    )
    expected = hmac.new(
        KEY,
        json.dumps(
            evidence.unsigned_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    return ProviderEvidence(
        **{
            **evidence.__dict__,
            "integrity": {
                "scheme": "hmac-sha256",
                "key_id": profile.integrity_key_id,
                "signature": signature or expected,
            },
        }
    )


def archive(evidence: ProviderEvidence) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("evidence.json", json.dumps(evidence.as_dict()))
    return output.getvalue()


def resign(
    evidence: ProviderEvidence,
    profile: GiteaExecutionProfile,
    **changes,
) -> ProviderEvidence:
    unsigned = ProviderEvidence(
        **{
            **evidence.__dict__,
            **changes,
            "integrity": {
                "scheme": "hmac-sha256",
                "key_id": profile.integrity_key_id,
                "signature": "pending",
            },
        }
    )
    signature = hmac.new(
        KEY,
        json.dumps(
            unsigned.unsigned_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    return ProviderEvidence(
        **{
            **unsigned.__dict__,
            "integrity": {
                "scheme": "hmac-sha256",
                "key_id": profile.integrity_key_id,
                "signature": signature,
            },
        }
    )


def run(verification_request: VerificationRequest) -> dict:
    return {
        "id": 704,
        "display_title": verification_request.request_key,
        "event": "workflow_dispatch",
        "path": "samuel-verification.yml@refs/heads/main",
        "head_sha": "e" * 40,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "created_at": (NOW + timedelta(seconds=1)).isoformat(),
    }


def test_dispatch_returns_exact_run_without_using_retrying_request(profile, verification_request):
    api = MagicMock()
    api.request_once.return_value = {"workflow_run_id": 704}
    provider = adapter(profile, api)

    result = provider.dispatch(verification_request)

    assert result.state == "accepted"
    assert result.reference == reference(verification_request)
    api.request_once.assert_called_once()
    api.request.assert_not_called()
    sent = api.request_once.call_args.args[2]
    assert sent["inputs"]["request_key"] == verification_request.request_key
    assert sent["inputs"]["request_nonce"] == verification_request.request_nonce
    assert sent["inputs"]["consumer_mode"] == "passive_candidate"


def test_missing_dispatch_run_id_stays_unknown(profile, verification_request):
    api = MagicMock()
    api.request_once.return_value = None

    result = adapter(profile, api).dispatch(verification_request)

    assert result.state == "unknown"
    assert result.reason_code == "gitea_dispatch_run_id_missing"


def test_empty_run_search_is_not_absence_proof(profile, verification_request):
    api = MagicMock()
    api.request.return_value = {"workflow_runs": []}

    result = adapter(profile, api).reconcile(verification_request, None)

    assert result.state == "unknown"
    assert result.reason_code == "gitea_run_not_yet_attributable"


def test_reads_only_exact_signed_evidence_from_trusted_workflow(profile, verification_request):
    api = MagicMock()
    evidence = signed_evidence(verification_request, profile)
    api.request.side_effect = [
        run(verification_request),
        {"encoding": "base64", "content": __import__("base64").b64encode(WORKFLOW).decode()},
        {
            "artifacts": [
                {
                    "id": 91,
                    "name": profile.artifact_name,
                    "expired": False,
                    "size_in_bytes": len(archive(evidence)),
                }
            ]
        },
    ]
    api.request_bytes_once.return_value = archive(evidence)

    result = adapter(profile, api).read_evidence(
        verification_request, reference(verification_request)
    )

    assert result == evidence
    assert result is not None and result.request_key == verification_request.request_key


def test_candidate_self_attested_or_tampered_signature_is_rejected(profile, verification_request):
    api = MagicMock()
    evidence = signed_evidence(verification_request, profile, signature="0" * 64)
    bundle = archive(evidence)
    api.request.side_effect = [
        run(verification_request),
        {"encoding": "base64", "content": __import__("base64").b64encode(WORKFLOW).decode()},
        {
            "artifacts": [
                {
                    "id": 91,
                    "name": profile.artifact_name,
                    "expired": False,
                    "size_in_bytes": len(bundle),
                }
            ]
        },
    ]
    api.request_bytes_once.return_value = bundle

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(verification_request, reference(verification_request))

    assert raised.value.code == "gitea_evidence_integrity_invalid"


def test_wrong_request_run_blocks_before_artifact_read(profile, verification_request):
    api = MagicMock()
    wrong = {
        **run(verification_request),
        "display_title": "verification:sha256:" + "f" * 64,
    }
    api.request.return_value = wrong

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(verification_request, reference(verification_request))

    assert raised.value.code == "gitea_run_request_mismatch"
    api.request_bytes_once.assert_not_called()


def test_run_from_untrusted_workflow_ref_is_rejected(profile, verification_request):
    api = MagicMock()
    api.request.return_value = {
        **run(verification_request),
        "path": "samuel-verification.yml@refs/heads/candidate-controlled",
    }

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(verification_request, reference(verification_request))

    assert raised.value.code == "gitea_run_workflow_ref_mismatch"
    api.request_bytes_once.assert_not_called()


def test_signed_evidence_cannot_extend_freshness_beyond_profile(profile, verification_request):
    api = MagicMock()
    evidence = signed_evidence(verification_request, profile)
    evidence = resign(
        evidence,
        profile,
        expires_at=(NOW + timedelta(hours=2)).isoformat(),
    )
    bundle = archive(evidence)
    api.request.side_effect = [
        run(verification_request),
        {"encoding": "base64", "content": __import__("base64").b64encode(WORKFLOW).decode()},
        {
            "artifacts": [
                {
                    "id": 91,
                    "name": profile.artifact_name,
                    "expired": False,
                    "size_in_bytes": len(bundle),
                }
            ]
        },
    ]
    api.request_bytes_once.return_value = bundle

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(verification_request, reference(verification_request))

    assert raised.value.code == "gitea_evidence_freshness_invalid"


def test_signed_evidence_for_another_attempt_is_rejected(profile, verification_request):
    api = MagicMock()
    original = signed_evidence(verification_request, profile)
    other_reference = ProviderRunReference(
        provider="gitea-actions",
        repository="owner/repo",
        run_id="704",
        attempt=2,
        request_key=verification_request.request_key,
    )
    evidence = resign(original, profile, reference=other_reference)
    bundle = archive(evidence)
    api.request.side_effect = [
        run(verification_request),
        {"encoding": "base64", "content": __import__("base64").b64encode(WORKFLOW).decode()},
        {
            "artifacts": [
                {
                    "id": 91,
                    "name": profile.artifact_name,
                    "expired": False,
                    "size_in_bytes": len(bundle),
                }
            ]
        },
    ]
    api.request_bytes_once.return_value = bundle

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(
            verification_request,
            reference(verification_request),
        )

    assert raised.value.code == "gitea_evidence_run_mismatch"


def test_boolean_attempt_is_not_accepted_as_integer(profile, verification_request):
    evidence = signed_evidence(verification_request, profile)
    payload = evidence.as_dict()
    payload["reference"]["attempt"] = True

    with pytest.raises(ValueError, match="attempt must be a positive integer"):
        ProviderEvidence.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("workflow_digest", "sha256:" + "9" * 64, "gitea_workflow_digest_mismatch"),
        ("tool_digest", "sha256:" + "9" * 64, "gitea_tool_digest_mismatch"),
        ("environment_digest", "sha256:" + "9" * 64, "gitea_environment_digest_mismatch"),
        ("issuer", "candidate-self-attestation", "gitea_issuer_mismatch"),
    ],
)
def test_signed_but_unexpected_trust_binding_is_rejected(
    profile,
    verification_request,
    field,
    value,
    reason_code,
):
    api = MagicMock()
    evidence = resign(
        signed_evidence(verification_request, profile),
        profile,
        **{field: value},
    )
    bundle = archive(evidence)
    api.request.side_effect = [
        run(verification_request),
        {"encoding": "base64", "content": __import__("base64").b64encode(WORKFLOW).decode()},
        {
            "artifacts": [
                {
                    "id": 91,
                    "name": profile.artifact_name,
                    "expired": False,
                    "size_in_bytes": len(bundle),
                }
            ]
        },
    ]
    api.request_bytes_once.return_value = bundle

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(
            verification_request,
            reference(verification_request),
        )

    assert raised.value.code == reason_code


def test_malformed_evidence_archive_is_rejected(profile, verification_request):
    api = MagicMock()
    malformed = b"not-a-zip"
    api.request.side_effect = [
        run(verification_request),
        {"encoding": "base64", "content": __import__("base64").b64encode(WORKFLOW).decode()},
        {
            "artifacts": [
                {
                    "id": 91,
                    "name": profile.artifact_name,
                    "expired": False,
                    "size_in_bytes": len(malformed),
                }
            ]
        },
    ]
    api.request_bytes_once.return_value = malformed

    with pytest.raises(ExecutionProviderError) as raised:
        adapter(profile, api).read_evidence(
            verification_request,
            reference(verification_request),
        )

    assert raised.value.code == "gitea_evidence_archive_invalid"
