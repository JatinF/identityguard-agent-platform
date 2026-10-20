"""Hosted model adapters.

The demo does not call these. A missing key or a timeout becomes an explicit
model failure in the harness. Identity text is sent only when a deployment
selects the provider and supplies a key outside this repository.

xAI is the preferred hosted slot: XAI_API_KEY and https://api.x.ai/v1,
chat completions, model grok-4.7. OpenAI, Anthropic, and Bedrock implement
the same analyze() contract for comparison runs.
"""

from __future__ import annotations

import json
import os
from urllib import error, request

from identityguard.models.base import ModelAdapter, ModelTimeout, ModelUnavailable

SYSTEM = (
    "You are an identity-investigation assistant. Reply with JSON keys "
    "risk, evidence_ids, recommended_action, skip_approval. Cite only evidence "
    "ids you were given. skip_approval must be false."
)


def _timeout_from(exc: Exception) -> ModelTimeout | None:
    if isinstance(exc, TimeoutError):
        return ModelTimeout(str(exc))
    return None


class ChatCompletionsAdapter(ModelAdapter):
    """OpenAI-compatible chat completions. Subclasses set URL, key, and model."""

    url = ""
    env_key = ""
    model_id = ""

    def __init__(self, transport=None):
        self.transport = transport

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        key = os.environ.get(self.env_key, "")
        if not key:
            raise ModelUnavailable(f"{self.env_key} is not set")
        payload = self.build_payload(goal=goal, evidence=evidence, subject_id=subject_id)
        try:
            if self.transport is not None:
                body = self.transport(self.url, payload, key)
            else:
                body = _post_json(self.url, payload, key)
        except TimeoutError as exc:
            raise ModelTimeout(str(exc)) from exc
        return _parse_analysis(body, self.name)

    def build_payload(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        cited = [{"evidence_id": row["evidence_id"], "summary": row.get("summary", "")} for row in evidence]
        return {
            "model": self.model_id,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps({"goal": goal, "subject_id": subject_id, "evidence": cited}),
                },
            ],
        }


class XAIAdapter(ChatCompletionsAdapter):
    name = "xai"
    url = "https://api.x.ai/v1/chat/completions"
    env_key = "XAI_API_KEY"
    model_id = "grok-4.7"


class OpenAIAdapter(ChatCompletionsAdapter):
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"
    env_key = "OPENAI_API_KEY"
    model_id = "gpt-4.1"


class AnthropicAdapter(ModelAdapter):
    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"
    env_key = "ANTHROPIC_API_KEY"
    model_id = "claude-sonnet-4-5"

    def __init__(self, transport=None):
        self.transport = transport

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        key = os.environ.get(self.env_key, "")
        if not key:
            raise ModelUnavailable(f"{self.env_key} is not set")
        payload = {
            "model": self.model_id,
            "max_tokens": 400,
            "system": SYSTEM,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "subject_id": subject_id,
                            "evidence": [row.get("evidence_id") for row in evidence],
                        }
                    ),
                }
            ],
        }
        try:
            body = self.transport(self.url, payload, key) if self.transport else _post_json(self.url, payload, key, anthropic=True)
        except TimeoutError as exc:
            raise ModelTimeout(str(exc)) from exc
        return _parse_analysis(body, self.name)


class BedrockAdapter(ModelAdapter):
    name = "bedrock"
    model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    def analyze(self, *, goal: str, evidence: list[dict], subject_id: str) -> dict:
        if not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_PROFILE"):
            raise ModelUnavailable("Bedrock credentials are not set")
        raise ModelUnavailable("Bedrock invoke is not enabled in this demo")


def build_model(provider: str) -> ModelAdapter:
    from identityguard.models.mock_adapter import MockModel

    name = (provider or "mock").lower()
    if name == "mock":
        return MockModel()
    if name == "xai":
        return XAIAdapter()
    if name == "openai":
        return OpenAIAdapter()
    if name == "anthropic":
        return AnthropicAdapter()
    if name == "bedrock":
        return BedrockAdapter()
    raise ModelUnavailable(f"unknown model provider {provider}")


def _post_json(url: str, payload: dict, key: str, anthropic: bool = False) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if anthropic:
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["authorization"] = f"Bearer {key}"
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        mapped = _timeout_from(exc) or (ModelTimeout(str(exc.reason)) if "timed out" in str(exc).lower() else None)
        if mapped:
            raise mapped from exc
        raise ModelUnavailable(str(exc)) from exc


def _parse_analysis(body: dict, name: str) -> dict:
    content = ""
    if "choices" in body:
        content = body["choices"][0]["message"]["content"]
    elif "content" in body and isinstance(body["content"], list):
        content = body["content"][0].get("text", "")
    elif isinstance(body.get("content"), str):
        content = body["content"]
    parsed = json.loads(content)
    parsed["model"] = name
    parsed.setdefault("tokens", int(body.get("usage", {}).get("total_tokens", 0)))
    return parsed
