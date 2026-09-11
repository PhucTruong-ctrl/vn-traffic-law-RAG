"""Deterministic-first claim support verification with fail-closed judging."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from typing import Any
from urllib import error, request

import app.config as config

from .l2_citation import LayerResult, VerificationIssue


L5_JUDGE_MODEL = "google/gemini-2.5-flash-lite"
L5_JUDGE_PATH = "/chat/completions"


def _v(x: Any, n: str, d: Any = None) -> Any:
    return x.get(n, d) if isinstance(x, Mapping) else getattr(x, n, d)


class OpenRouterClaimJudge:
    """Strict semantic claim-support judge backed by OpenRouter."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        opener: Any = request.urlopen,
    ) -> None:
        self._api_key, self._base_url, self._model = api_key, base_url, model
        self._timeout, self._opener = timeout, opener

    def __call__(self, claim: str, evidence: Sequence[str]) -> Mapping[str, Any]:
        settings = config.get_generation_settings()
        api_key = self._api_key if self._api_key is not None else settings.openrouter_api_key
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for the semantic judge")
        model = self._model or settings.model or L5_JUDGE_MODEL
        base_url = (self._base_url or settings.openrouter_base_url).rstrip("/")
        schema = {
            "type": "object",
            "properties": {
                "supported": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["supported", "reason"],
            "additionalProperties": False,
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Determine whether the claim is supported by the evidence. "
                        "Return only JSON matching the schema; do not infer absent facts.\n"
                        f"Claim: {claim}\nEvidence: {list(evidence)}"
                    ),
                }
            ],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "claim_verdict", "strict": True, "schema": schema},
            },
        }
        req = request.Request(
            f"{base_url}{L5_JUDGE_PATH}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(req, timeout=self._timeout) as response:
                result = json.loads(response.read())
            content = result["choices"][0]["message"]["content"]
            verdict = json.loads(content) if isinstance(content, str) else content
            if (
                not isinstance(verdict, Mapping)
                or type(verdict.get("supported")) is not bool
                or not isinstance(verdict.get("reason"), str)
            ):
                raise ValueError("invalid claim verdict")
            return verdict
        except (
            error.HTTPError,
            error.URLError,
            TimeoutError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError("OpenRouter semantic judge failed") from exc


def _text(x: Any) -> str:
    return str(_v(x, "text", _v(x, "content", x)) or "")


def _tokens(s: str) -> set[str]:
    return {w.casefold() for w in s.split() if len(w) > 2}


class L5ClaimVerifier:
    def __init__(self, judge: Callable[..., Any] | None = None, judge_enabled: bool = True) -> None:
        self.judge, self.judge_enabled = judge, judge_enabled

    def verify(
        self,
        draft: Any,
        context: Sequence[Any] = (),
        query_context: Any = None,
        **_: Any,
    ) -> LayerResult:
        issues: list[VerificationIssue] = []
        checked: list[str] = []
        by_id = {_v(x, "provision_id", _v(x, "id")): x for x in context}
        for i, claim in enumerate(_v(draft, "claims", ()) or ()):
            ids = _v(claim, "provision_ids", ()) or ()
            if not ids:
                issues.append(
                    VerificationIssue(
                        "L5_CLAIM_WITHOUT_CITATION", "claim has no citation", claim_index=i
                    )
                )
                continue
            passages = [_text(by_id[x]) for x in ids if x in by_id]
            if not passages:
                issues.append(
                    VerificationIssue("L5_CLAIM_NOT_SUPPORTED", "no cited passage", claim_index=i)
                )
                continue
            claim_text = _text(claim) if _v(claim, "claim") is None else str(_v(claim, "claim"))
            if _tokens(claim_text) & set().union(*(_tokens(p) for p in passages)):
                checked.append(str(i))
                continue
            if self.judge_enabled and self.judge is not None:
                try:
                    verdict = self.judge(claim_text, passages)
                    if verdict is True or _v(verdict, "supported", False) is True:
                        checked.append(str(i))
                        continue
                except Exception:
                    issues.append(
                        VerificationIssue(
                            "L5_JUDGE_UNAVAILABLE",
                            "semantic judge unavailable",
                            claim_index=i,
                        )
                    )
                    continue
            issues.append(
                VerificationIssue("L5_CLAIM_NOT_SUPPORTED", "claim is not supported", claim_index=i)
            )
        return LayerResult(not issues, issues, checked)


def verify(
    draft: Any, context: Sequence[Any] = (), query_context: Any = None, **kwargs: Any
) -> LayerResult:
    return L5ClaimVerifier().verify(draft, context, query_context, **kwargs)


__all__ = ["L5ClaimVerifier", "verify"]
__all__ = ["L5ClaimVerifier", "OpenRouterClaimJudge", "verify"]
