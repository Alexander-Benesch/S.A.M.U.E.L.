"""Gitea Actions reference adapter for bound verification requests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import urllib.parse
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from samuel.adapters.gitea.api import GiteaAPI, GiteaAPIError
from samuel.core.ports import IExecutionProvider
from samuel.core.types import (
    ExecutionProviderError,
    ProviderDispatchResult,
    ProviderEvidence,
    ProviderRunReference,
    VerificationRequest,
    canonical_digest,
)

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("provider timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class GiteaExecutionProfile:
    """Public, versioned trust profile; the integrity key is injected separately."""

    name: str
    repository: str
    workflow_id: str
    workflow_path: str
    workflow_ref: str
    workflow_digest: str
    tool_digest: str
    environment_digest: str
    issuer: str
    integrity_key_id: str
    artifact_name: str = "samuel-verification-evidence"
    evidence_filename: str = "evidence.json"
    max_artifact_bytes: int = 262_144
    max_evidence_age_seconds: int = 3_600
    clock_skew_seconds: int = 60
    schema_version: int = 1

    def __post_init__(self) -> None:
        values = {
            "name": self.name,
            "repository": self.repository,
            "workflow_id": self.workflow_id,
            "workflow_path": self.workflow_path,
            "workflow_ref": self.workflow_ref,
            "issuer": self.issuer,
            "integrity_key_id": self.integrity_key_id,
            "artifact_name": self.artifact_name,
            "evidence_filename": self.evidence_filename,
        }
        for field, value in values.items():
            if (
                not value
                or value != value.strip()
                or len(value) > 1024
                or any(ord(char) < 32 or ord(char) == 127 for char in value)
            ):
                raise ValueError(f"execution profile {field} is invalid")
        for field in ("workflow_digest", "tool_digest", "environment_digest"):
            value = str(getattr(self, field))
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
                raise ValueError(f"execution profile {field} is invalid")
            if value == "sha256:" + "0" * 64:
                raise ValueError(f"execution profile {field} is still a placeholder")
        if not self.workflow_path.startswith(".gitea/workflows/") or ".." in self.workflow_path:
            raise ValueError("execution profile workflow_path is invalid")
        if "/" in self.evidence_filename or "\\" in self.evidence_filename:
            raise ValueError("execution profile evidence_filename is invalid")
        if (
            not isinstance(self.max_artifact_bytes, int)
            or isinstance(self.max_artifact_bytes, bool)
            or self.max_artifact_bytes <= 0
            or self.max_artifact_bytes > 2_000_000
        ):
            raise ValueError("execution profile artifact limit is invalid")
        if (
            not isinstance(self.max_evidence_age_seconds, int)
            or isinstance(self.max_evidence_age_seconds, bool)
            or self.max_evidence_age_seconds <= 0
            or self.max_evidence_age_seconds > 86_400
        ):
            raise ValueError("execution profile evidence age limit is invalid")
        if (
            not isinstance(self.clock_skew_seconds, int)
            or isinstance(self.clock_skew_seconds, bool)
            or self.clock_skew_seconds < 0
            or self.clock_skew_seconds > 300
        ):
            raise ValueError("execution profile clock skew is invalid")
        if self.schema_version != 1:
            raise ValueError("unsupported execution profile schema")

    @property
    def profile_digest(self) -> str:
        return canonical_digest(asdict(self))

    @classmethod
    def from_file(cls, path: str | Path) -> GiteaExecutionProfile | None:
        """Load the single shipped reference profile; disabled means absent."""

        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("execution provider config has an unsupported schema")
        if value.get("enabled") is not True:
            return None
        profile = value.get("gitea")
        if not isinstance(profile, dict):
            raise ValueError("enabled execution provider has no Gitea profile")
        if value.get("required_qualified") is not True:
            raise ValueError("execution provider is not qualified for required use")
        return cls(
            schema_version=profile.get("schema_version", 0),
            name=str(profile.get("name", "")),
            repository=str(profile.get("repository", "")),
            workflow_id=str(profile.get("workflow_id", "")),
            workflow_path=str(profile.get("workflow_path", "")),
            workflow_ref=str(profile.get("workflow_ref", "")),
            workflow_digest=str(profile.get("workflow_digest", "")),
            tool_digest=str(profile.get("tool_digest", "")),
            environment_digest=str(profile.get("environment_digest", "")),
            issuer=str(profile.get("issuer", "")),
            integrity_key_id=str(profile.get("integrity_key_id", "")),
            artifact_name=str(profile.get("artifact_name", "samuel-verification-evidence")),
            evidence_filename=str(profile.get("evidence_filename", "evidence.json")),
            max_artifact_bytes=profile.get("max_artifact_bytes", 262_144),
            max_evidence_age_seconds=profile.get("max_evidence_age_seconds", 3_600),
            clock_skew_seconds=profile.get("clock_skew_seconds", 60),
        )


class GiteaExecutionProvider(IExecutionProvider):
    """Dispatch a trusted workflow and verify its bounded evidence artifact."""

    def __init__(
        self,
        api: GiteaAPI,
        *,
        base_url: str,
        profile: GiteaExecutionProfile,
        integrity_key: bytes,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if len(integrity_key) < 32:
            raise ValueError("execution provider integrity key must contain at least 32 bytes")
        self._api = api
        self._base_url = base_url.rstrip("/")
        self._profile = profile
        self._integrity_key = integrity_key
        self._clock = clock

    def dispatch(self, request: VerificationRequest) -> ProviderDispatchResult:
        self._validate_request_profile(request)
        workflow = urllib.parse.quote(self._profile.workflow_id, safe="")
        query = urllib.parse.urlencode({"return_run_details": "true"})
        path = f"/repos/{self._profile.repository}/actions/workflows/{workflow}/dispatches?{query}"
        payload = {
            "ref": self._profile.workflow_ref,
            "inputs": {
                "request_key": request.request_key,
                "request_nonce": request.request_nonce,
                "subject": _canonical_json(request.subject.as_dict()),
                "criteria": _canonical_json([item.as_dict() for item in request.criteria]),
                "policy_binding": _canonical_json(request.policy_binding),
                "provider_profile_digest": request.provider_profile_digest,
                "consumer_mode": request.consumer_mode,
            },
        }
        try:
            result = self._api.request_once("POST", path, payload)
        except GiteaAPIError as exc:
            if exc.status in {400, 403, 404, 422}:
                return ProviderDispatchResult(
                    state="rejected", reason_code=f"gitea_dispatch_http_{exc.status}"
                )
            raise
        if result is None:
            return ProviderDispatchResult(
                state="unknown", reason_code="gitea_dispatch_run_id_missing"
            )
        if not isinstance(result, dict):
            return ProviderDispatchResult(
                state="unknown", reason_code="gitea_dispatch_response_invalid"
            )
        run_id = result.get("workflow_run_id")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            return ProviderDispatchResult(
                state="unknown", reason_code="gitea_dispatch_run_id_missing"
            )
        return ProviderDispatchResult(
            state="accepted",
            reference=self._reference(request, run_id, attempt=1),
        )

    def reconcile(
        self,
        request: VerificationRequest,
        reference: ProviderRunReference | None,
    ) -> ProviderDispatchResult:
        self._validate_request_profile(request)
        if reference is not None:
            self._validate_reference(request, reference)
            try:
                run = self._run(int(reference.run_id))
            except GiteaAPIError as exc:
                if exc.status == 404:
                    return ProviderDispatchResult(
                        state="unknown", reason_code="gitea_run_temporarily_missing"
                    )
                raise
            self._validate_run_binding(request, run)
            return ProviderDispatchResult(state="accepted", reference=reference)

        workflow = urllib.parse.quote(self._profile.workflow_id, safe="")
        query = urllib.parse.urlencode({"event": "workflow_dispatch", "page": 1, "limit": 50})
        payload = self._api.request(
            "GET",
            f"/repos/{self._profile.repository}/actions/workflows/{workflow}/runs?{query}",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
            raise ExecutionProviderError(
                "gitea_run_search_invalid", "Gitea run search returned an invalid response"
            )
        matches: list[dict[str, Any]] = []
        authorized_at = _timestamp(request.authorized_at)
        for item in payload["workflow_runs"]:
            if not isinstance(item, dict) or item.get("display_title") != request.request_key:
                continue
            created_at = item.get("created_at")
            try:
                if not isinstance(created_at, str) or _timestamp(created_at) < authorized_at:
                    continue
            except ValueError:
                continue
            matches.append(item)
        if not matches:
            # Search absence is not proof that the POST had no effect.
            return ProviderDispatchResult(
                state="unknown", reason_code="gitea_run_not_yet_attributable"
            )
        if len(matches) != 1:
            return ProviderDispatchResult(
                state="rejected", reason_code="gitea_request_run_ambiguous"
            )
        run = matches[0]
        self._validate_run_binding(request, run)
        run_id = run.get("id")
        attempt = run.get("run_attempt", run.get("attempt", 1))
        if (
            not isinstance(run_id, int)
            or isinstance(run_id, bool)
            or run_id <= 0
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt <= 0
        ):
            raise ExecutionProviderError(
                "gitea_run_identity_invalid", "Gitea run identity is invalid"
            )
        return ProviderDispatchResult(
            state="accepted", reference=self._reference(request, run_id, attempt=attempt)
        )

    def read_evidence(
        self,
        request: VerificationRequest,
        reference: ProviderRunReference,
    ) -> ProviderEvidence | None:
        self._validate_request_profile(request)
        self._validate_reference(request, reference)
        run_id = int(reference.run_id)
        run = self._run(run_id)
        self._validate_run_binding(request, run)
        status = str(run.get("status") or "").lower()
        if status != "completed":
            return None
        if str(run.get("conclusion") or "").lower() != "success":
            raise ExecutionProviderError(
                "gitea_control_plane_failed",
                "Gitea verification control-plane run did not complete successfully",
            )
        reported_attempt = run.get("run_attempt", run.get("attempt"))
        if reported_attempt != reference.attempt:
            raise ExecutionProviderError(
                "gitea_attempt_mismatch", "Gitea run attempt differs from the request binding"
            )
        self._verify_workflow(run)
        query = urllib.parse.urlencode({"name": self._profile.artifact_name})
        payload = self._api.request(
            "GET",
            f"/repos/{self._profile.repository}/actions/runs/{run_id}/artifacts?{query}",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("artifacts"), list):
            raise ExecutionProviderError(
                "gitea_artifact_list_invalid", "Gitea artifact list is invalid"
            )
        artifacts = [
            item
            for item in payload["artifacts"]
            if isinstance(item, dict) and item.get("name") == self._profile.artifact_name
        ]
        if len(artifacts) != 1:
            raise ExecutionProviderError(
                "gitea_evidence_artifact_ambiguous",
                "Gitea run does not expose exactly one verification evidence artifact",
            )
        artifact = artifacts[0]
        artifact_id = artifact.get("id")
        size = artifact.get("size_in_bytes")
        if artifact.get("expired") is True:
            raise ExecutionProviderError(
                "gitea_evidence_artifact_expired", "Gitea verification evidence has expired"
            )
        if (
            not isinstance(artifact_id, int)
            or isinstance(artifact_id, bool)
            or artifact_id <= 0
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or size > self._profile.max_artifact_bytes
        ):
            raise ExecutionProviderError(
                "gitea_evidence_artifact_invalid", "Gitea evidence artifact metadata is invalid"
            )
        archive = self._api.request_bytes_once(
            "GET",
            f"/repos/{self._profile.repository}/actions/artifacts/{artifact_id}/zip",
            max_response_bytes=self._profile.max_artifact_bytes,
        )
        evidence = self._parse_evidence_archive(archive)
        self._verify_evidence_integrity(evidence)
        if evidence.reference != reference:
            raise ExecutionProviderError(
                "gitea_evidence_run_mismatch",
                "Provider evidence belongs to another run or attempt",
            )
        if evidence.workflow_digest != self._profile.workflow_digest:
            raise ExecutionProviderError(
                "gitea_workflow_digest_mismatch",
                "Provider evidence names an unexpected workflow digest",
            )
        if evidence.tool_digest != self._profile.tool_digest:
            raise ExecutionProviderError(
                "gitea_tool_digest_mismatch", "Provider evidence names an unexpected tool digest"
            )
        if evidence.environment_digest != self._profile.environment_digest:
            raise ExecutionProviderError(
                "gitea_environment_digest_mismatch",
                "Provider evidence names an unexpected execution environment",
            )
        if evidence.issuer != self._profile.issuer:
            raise ExecutionProviderError(
                "gitea_issuer_mismatch", "Provider evidence has an unexpected issuer"
            )
        issued_at = _timestamp(evidence.issued_at)
        expires_at = _timestamp(evidence.expires_at)
        now = self._clock().astimezone(timezone.utc)
        if issued_at > now + timedelta(seconds=self._profile.clock_skew_seconds):
            raise ExecutionProviderError(
                "gitea_evidence_freshness_invalid",
                "Provider evidence issue time is outside the trusted clock window",
            )
        if expires_at - issued_at > timedelta(seconds=self._profile.max_evidence_age_seconds):
            raise ExecutionProviderError(
                "gitea_evidence_freshness_invalid",
                "Provider evidence validity exceeds the trusted profile",
            )
        return evidence

    def _validate_request_profile(self, request: VerificationRequest) -> None:
        if (
            request.provider_profile != self._profile.name
            or request.provider_profile_digest != self._profile.profile_digest
        ):
            raise ExecutionProviderError(
                "provider_profile_mismatch", "Verification request uses another provider profile"
            )
        if request.subject.repository.rstrip("/") != (
            f"{self._base_url}/{self._profile.repository}"
        ).rstrip("/"):
            raise ExecutionProviderError(
                "provider_repository_mismatch",
                "Verification subject belongs to another repository",
            )

    def _validate_reference(
        self, request: VerificationRequest, reference: ProviderRunReference
    ) -> None:
        if (
            reference.provider != "gitea-actions"
            or reference.repository != self._profile.repository
            or reference.request_key != request.request_key
            or not reference.run_id.isdigit()
        ):
            raise ExecutionProviderError(
                "gitea_run_reference_mismatch", "Gitea run reference differs from the request"
            )

    def _reference(
        self, request: VerificationRequest, run_id: int, *, attempt: int
    ) -> ProviderRunReference:
        return ProviderRunReference(
            provider="gitea-actions",
            repository=self._profile.repository,
            run_id=str(run_id),
            attempt=attempt,
            request_key=request.request_key,
        )

    def _run(self, run_id: int) -> dict[str, Any]:
        payload = self._api.request(
            "GET", f"/repos/{self._profile.repository}/actions/runs/{run_id}"
        )
        if not isinstance(payload, dict) or payload.get("id") != run_id:
            raise ExecutionProviderError(
                "gitea_run_response_invalid", "Gitea run response is invalid"
            )
        return payload

    def _validate_run_binding(self, request: VerificationRequest, run: dict[str, Any]) -> None:
        if run.get("display_title") != request.request_key:
            raise ExecutionProviderError(
                "gitea_run_request_mismatch", "Gitea run does not identify the exact request"
            )
        if str(run.get("event") or "").lower() != "workflow_dispatch":
            raise ExecutionProviderError(
                "gitea_run_event_mismatch", "Gitea run was not created by workflow dispatch"
            )
        raw_path = str(run.get("path") or "")
        path, separator, workflow_ref = raw_path.partition("@")
        if path and not path.startswith(".gitea/workflows/"):
            path = f".gitea/workflows/{path.lstrip('/')}"
        if path != self._profile.workflow_path:
            raise ExecutionProviderError(
                "gitea_run_workflow_mismatch", "Gitea run used another workflow"
            )
        expected_ref = (
            self._profile.workflow_ref
            if self._profile.workflow_ref.startswith("refs/")
            else f"refs/heads/{self._profile.workflow_ref}"
        )
        if separator != "@" or workflow_ref != expected_ref:
            raise ExecutionProviderError(
                "gitea_run_workflow_ref_mismatch",
                "Gitea run used an unexpected workflow reference",
            )

    def _verify_workflow(self, run: dict[str, Any]) -> None:
        head_sha = str(run.get("head_sha") or "").lower()
        if not _FULL_SHA_RE.fullmatch(head_sha):
            raise ExecutionProviderError(
                "gitea_workflow_revision_invalid", "Gitea run lacks a trusted workflow revision"
            )
        path = urllib.parse.quote(self._profile.workflow_path, safe="/")
        query = urllib.parse.urlencode({"ref": head_sha})
        payload = self._api.request(
            "GET", f"/repos/{self._profile.repository}/contents/{path}?{query}"
        )
        if not isinstance(payload, dict) or payload.get("encoding") != "base64":
            raise ExecutionProviderError(
                "gitea_workflow_content_invalid", "Gitea workflow content is unavailable"
            )
        try:
            content = base64.b64decode(str(payload.get("content") or ""), validate=True)
        except (ValueError, TypeError) as exc:
            raise ExecutionProviderError(
                "gitea_workflow_content_invalid", "Gitea workflow content is invalid"
            ) from exc
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if digest != self._profile.workflow_digest:
            raise ExecutionProviderError(
                "gitea_workflow_digest_mismatch", "Gitea run used an untrusted workflow revision"
            )

    def _parse_evidence_archive(self, archive: bytes) -> ProviderEvidence:
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                files = [item for item in bundle.infolist() if not item.is_dir()]
                if len(files) != 1 or files[0].filename != self._profile.evidence_filename:
                    raise ExecutionProviderError(
                        "gitea_evidence_archive_invalid",
                        "Gitea evidence archive has unexpected contents",
                    )
                member = files[0]
                if (
                    member.file_size <= 0
                    or member.file_size > self._profile.max_artifact_bytes
                    or member.flag_bits & 0x1
                ):
                    raise ExecutionProviderError(
                        "gitea_evidence_archive_invalid",
                        "Gitea evidence archive member is invalid",
                    )
                raw = bundle.read(member)
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise ExecutionProviderError(
                "gitea_evidence_archive_invalid", "Gitea evidence archive is invalid"
            ) from exc
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExecutionProviderError(
                "gitea_evidence_json_invalid", "Gitea evidence payload is invalid"
            ) from exc
        if not isinstance(value, dict):
            raise ExecutionProviderError(
                "gitea_evidence_json_invalid", "Gitea evidence payload is invalid"
            )
        try:
            return ProviderEvidence.from_dict(value)
        except (TypeError, ValueError) as exc:
            raise ExecutionProviderError(
                "gitea_evidence_contract_invalid", "Gitea evidence contract is invalid"
            ) from exc

    def _verify_evidence_integrity(self, evidence: ProviderEvidence) -> None:
        proof = evidence.integrity
        if (
            set(proof) != {"scheme", "key_id", "signature"}
            or proof.get("scheme") != "hmac-sha256"
            or proof.get("key_id") != self._profile.integrity_key_id
            or not isinstance(proof.get("signature"), str)
            or re.fullmatch(r"[0-9a-f]{64}", str(proof.get("signature"))) is None
        ):
            raise ExecutionProviderError(
                "gitea_evidence_integrity_invalid", "Provider evidence integrity proof is invalid"
            )
        signature = hmac.new(
            self._integrity_key,
            _canonical_json(evidence.unsigned_dict()).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, str(proof["signature"])):
            raise ExecutionProviderError(
                "gitea_evidence_integrity_invalid", "Provider evidence signature is invalid"
            )
