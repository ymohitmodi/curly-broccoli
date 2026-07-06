"""LLM client for the harness.

Two backends behind one interface:

  OllamaClient — talks to the local Ollama daemon (http://localhost:11434).
    Ollama Cloud models (e.g. "qwen3-coder:480b-cloud") are served through the
    SAME local API after `ollama signin`, so a MacBook Air can orchestrate
    while the heavy inference runs in Ollama's cloud. Structured output is
    enforced by passing a JSON schema in the `format` field.

  MockLLM — generates deterministic schema-conforming JSON without any model.
    Used for pipeline testing (DARKFACTORY_LLM=mock) so you can verify the
    whole factory end-to-end for free before spending tokens.

A daily call budget (kv-counter in SQLite) acts as a circuit breaker.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import Any

import requests


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


class BaseLLM:
    def chat(self, messages: list[dict], *, model: str | None = None,
             temperature: float | None = None, json_schema: dict | None = None) -> str:
        raise NotImplementedError

    def chat_json(self, messages: list[dict], schema: dict, *,
                  model: str | None = None, temperature: float | None = None) -> Any:
        """Chat with schema-enforced output; parse (with one repair retry)."""
        raw = self.chat(messages, model=model, temperature=temperature, json_schema=schema)
        try:
            return _parse_json(raw)
        except ValueError:
            repair = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "That was not valid JSON. Respond again with ONLY valid JSON matching the schema."},
            ]
            raw = self.chat(repair, model=model, temperature=0.0, json_schema=schema)
            return _parse_json(raw)

    def chat_json_refined(self, messages: list[dict], schema: dict, critique: str, *,
                          model: str | None = None) -> Any:
        """Draft → self-critique against a rubric → revised final.

        Single-pass output is first-draft quality; forcing the model to attack
        its own draft with an explicit rubric before finalizing measurably
        raises accuracy for judgment tasks (scoring, copy, negotiation). Costs
        one extra call — reserve it for outputs that decide money."""
        draft = self.chat_json(messages, schema, model=model)
        revise = messages + [
            {"role": "assistant", "content": json.dumps(draft, default=str)},
            {"role": "user", "content":
                "Critique your draft ruthlessly against this rubric, then output the "
                "IMPROVED version. Fix every weakness you find; keep what is strong.\n\n"
                f"RUBRIC:\n{critique}\n\n"
                "Respond with ONLY the improved JSON (same schema)."},
        ]
        return self.chat_json(revise, schema, model=model, temperature=0.2)


class OllamaClient(BaseLLM):
    def __init__(self, cfg, memory=None):
        llm = cfg.harness.get("llm", {})
        self.host = llm.get("host", "http://localhost:11434").rstrip("/")
        self.planner_model = llm.get("planner_model", "qwen3:8b")
        self.worker_model = llm.get("worker_model", self.planner_model)
        self.fast_model = llm.get("fast_model", self.worker_model)
        self.temperature = float(llm.get("temperature", 0.4))
        self.timeout = int(llm.get("request_timeout_s", 420))
        self.max_retries = int(llm.get("max_retries", 3))
        self.max_calls_per_day = int(llm.get("max_calls_per_day", 300))
        self.memory = memory  # optional; enables the daily budget counter

    # -- budget circuit breaker -------------------------------------------
    def _check_budget(self):
        if self.memory is None:
            return
        key = f"llm_calls:{dt.date.today().isoformat()}"
        count = int(self.memory.kv_get(key) or 0)
        if count >= self.max_calls_per_day:
            raise BudgetExceeded(
                f"Daily LLM budget of {self.max_calls_per_day} calls reached; "
                "factory pauses until midnight. Raise llm.max_calls_per_day if intended.")
        self.memory.kv_set(key, str(count + 1))

    # -- transport ----------------------------------------------------------
    def chat(self, messages, *, model=None, temperature=None, json_schema=None) -> str:
        self._check_budget()
        payload: dict[str, Any] = {
            "model": model or self.worker_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature if temperature is None else temperature},
        }
        if json_schema is not None:
            payload["format"] = json_schema  # Ollama enforces the schema server-side

        delay = 2.0
        last_err: Exception | None = None
        for _ in range(self.max_retries):
            try:
                r = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
                r.raise_for_status()
                content = r.json().get("message", {}).get("content", "")
                if content:
                    return content
                last_err = LLMError("empty response from model")
            except (requests.RequestException, ValueError) as e:
                last_err = e
            time.sleep(delay)
            delay *= 2
        raise LLMError(f"Ollama chat failed after {self.max_retries} attempts: {last_err}")


class MockLLM(BaseLLM):
    """Deterministic schema-driven filler. Lets the entire factory run with
    zero model access so you can test scheduling, memory, approvals, reports."""

    planner_model = worker_model = fast_model = "mock"

    def chat(self, messages, *, model=None, temperature=None, json_schema=None) -> str:
        if json_schema is not None:
            return json.dumps(_fill_schema(json_schema))
        return "[mock] " + (messages[-1]["content"][:120] if messages else "")


def _parse_json(raw: str) -> Any:
    """Parse model output as JSON, tolerating code fences and preamble."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # last resort: first {...} or [...] span
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = raw.find(opener), raw.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except json.JSONDecodeError:
                    continue
    raise ValueError("model output was not valid JSON")


def _fill_schema(schema: dict, depth: int = 0) -> Any:
    """Generate a plausible value conforming to a JSON schema (mock mode)."""
    t = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if t == "object" or "properties" in schema:
        return {k: _fill_schema(v, depth + 1) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        item = schema.get("items", {"type": "string"})
        return [_fill_schema(item, depth + 1) for _ in range(2)]
    if t == "number":
        return 0.62
    if t == "integer":
        return 7
    if t == "boolean":
        return True
    # strings carry a digit so evidence-citation gates behave as with a real
    # model (which is instructed to cite numbers)
    return (f"mock-42 {schema.get('description', 'value')[:40]}"
            if isinstance(schema.get("description"), str) else "mock-value 42")


def make_llm(cfg, memory=None) -> BaseLLM:
    mode = cfg.llm("mode", "ollama")
    if mode == "mock":
        return MockLLM()
    return OllamaClient(cfg, memory=memory)
