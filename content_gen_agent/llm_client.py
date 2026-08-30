"""OpenAI client for the generation modules (CG-009 onward).

A thin wrapper rather than calling the SDK directly from each generator, for
three reasons: the generators can then be tested without network access, the
key and model live in one place, and every call returns parsed JSON so callers
never handle raw strings.

Configuration follows what nablix-backend already does
(`app/services/rag/config.py`), so there is one convention across the codebase:

    OPENAI_API_KEY, or NABLIX_OPENAI_API_KEY as a fallback
    CONTENT_GEN_LLM_MODEL to override the model, default gpt-5.1

The key is only ever read from the environment. It is never logged, never
included in an error message, and never passed anywhere but the SDK.

Testing
-------

`LLMClient` is a Protocol, so a generator accepts anything with a matching
`complete_json`. `FakeLLMClient` implements it by returning canned responses,
which is how the CG-009 tests run offline and how failure modes -- malformed
JSON, a model inventing content -- are exercised deterministically.

A note on determinism
---------------------

Temperature is left unset by default. Newer models reject an explicit
temperature, and even at zero a model is not guaranteed to return the same
output twice. Reproducibility for this pipeline comes from validating model
output against the source document (see topic_generator), not from sampling
settings.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional, Protocol, runtime_checkable

DEFAULT_MODEL = os.getenv("CONTENT_GEN_LLM_MODEL", "gpt-5.1")

API_KEY_VARS = ("OPENAI_API_KEY", "NABLIX_OPENAI_API_KEY")


class LLMError(Exception):
    """The model call failed, or returned something unusable."""


class LLMNotConfiguredError(LLMError):
    """No API key in the environment."""


@runtime_checkable
class LLMClient(Protocol):
    """What a generator needs from a model. Implemented by real and fake alike."""

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        purpose: str = "",
    ) -> dict[str, Any]:
        """Send the prompts, return the parsed JSON object."""
        ...


def find_api_key() -> Optional[str]:
    """The configured key, or None. The value is never logged or returned in errors."""
    for name in API_KEY_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def is_configured() -> bool:
    """True when a key is present, so tests and CLIs can skip cleanly."""
    return find_api_key() is not None


class OpenAIClient:
    """Calls the OpenAI API and returns parsed JSON.

    `response_format={"type": "json_object"}` is used rather than a strict JSON
    schema because schema support varies by model, and the response is
    validated by Pydantic afterwards regardless.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: int = 2,
    ):
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries

        key = api_key or find_api_key()
        if not key:
            raise LLMNotConfiguredError(
                "No OpenAI API key found. Set OPENAI_API_KEY (or "
                "NABLIX_OPENAI_API_KEY) in your .env file."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError(
                "The openai package is not installed. Run: "
                "python3 -m pip install -r requirements.txt"
            ) from exc

        self._client = OpenAI(api_key=key, max_retries=max_retries)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        purpose: str = "",
    ) -> dict[str, Any]:
        label = purpose or "llm call"

        request: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.temperature is not None:
            request["temperature"] = self.temperature

        try:
            response = self._client.chat.completions.create(**request)
        except Exception as exc:
            # Deliberately does not echo the request, which would put document
            # content and headers into the log.
            raise LLMError(f"{label}: the API call failed ({type(exc).__name__})") from exc

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise LLMError(f"{label}: the model returned an empty response")

        return parse_json_object(content, label)


def parse_json_object(content: str, label: str = "llm call") -> dict[str, Any]:
    """Parse a JSON object, tolerating a fenced code block around it.

    Models sometimes wrap JSON in ```json fences despite being asked not to, so
    that one case is handled rather than failing the whole run over formatting.
    """
    text = content.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"{label}: the model did not return valid JSON ({exc})") from exc

    if not isinstance(parsed, dict):
        raise LLMError(
            f"{label}: expected a JSON object, got {type(parsed).__name__}"
        )
    return parsed


class FakeLLMClient:
    """A scripted client, for tests and dry runs.

    Give it responses in the order they will be requested. Each may be a dict
    (returned as-is), a string (parsed, so malformed JSON can be tested), or an
    Exception (raised, so API failures can be tested).
    """

    def __init__(self, responses: list[Any] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, str]] = []

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        purpose: str = "",
    ) -> dict[str, Any]:
        self.calls.append(
            {"system": system_prompt, "user": user_prompt, "purpose": purpose}
        )

        if not self.responses:
            raise LLMError(
                f"FakeLLMClient ran out of scripted responses "
                f"(call {len(self.calls)}, purpose={purpose!r})"
            )

        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if isinstance(nxt, str):
            return parse_json_object(nxt, purpose or "fake call")
        if isinstance(nxt, dict):
            return nxt
        raise LLMError(f"FakeLLMClient cannot return a {type(nxt).__name__}")

    @property
    def call_count(self) -> int:
        return len(self.calls)


def default_client() -> LLMClient:
    """A configured OpenAIClient, or a clear error explaining what is missing."""
    return OpenAIClient()


if __name__ == "__main__":
    print(f"model            : {DEFAULT_MODEL}")
    print(f"api key present  : {is_configured()}")
    if not is_configured():
        print(f"  looked for: {', '.join(API_KEY_VARS)}")
