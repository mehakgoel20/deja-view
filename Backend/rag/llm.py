"""Thin wrappers over OpenAI-compatible clients: batched embeddings and strict-JSON chat.

Embeddings always go to OpenAI. Chat goes to RCA_LLM_BASE_URL when set (for
example a local Ollama server), otherwise to OpenAI.
"""
import json
import time

import numpy as np
from openai import BadRequestError, OpenAI

from .config import EMBED_MODEL, LLM_BASE_URL, LLM_MODEL, LLM_REASONING

_clients = {}
# Reasoning models (gpt-5, gpt-5.5, o3, ...) only accept the default temperature.
_no_temperature = set()


def client(base_url=None):
    """OpenAI client for `base_url`; None means api.openai.com."""
    if base_url not in _clients:
        if base_url:
            _clients[base_url] = OpenAI(base_url=base_url, api_key="local", max_retries=2, timeout=600)
        else:
            _clients[base_url] = OpenAI(max_retries=5)
    return _clients[base_url]


def embed(texts, model=EMBED_MODEL, batch_size=256):
    """Return L2-normalised float32 embeddings, one row per text."""
    rows = []
    for start in range(0, len(texts), batch_size):
        response = client().embeddings.create(model=model, input=texts[start:start + batch_size])
        rows += [item.embedding for item in response.data]
    vectors = np.asarray(rows, dtype="float32")
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def chat_json(system, user, schema, name, model=LLM_MODEL, temperature=0.0,
              base_url=LLM_BASE_URL, reasoning=LLM_REASONING):
    """Call the chat model with a strict JSON schema and return the parsed object."""
    request = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema},
        },
    }
    if reasoning:
        request["reasoning_effort"] = reasoning
    for attempt in range(3):
        if model not in _no_temperature:
            request["temperature"] = temperature
        try:
            response = client(base_url).chat.completions.create(**request)
        except BadRequestError as e:
            if "temperature" not in str(e) or model in _no_temperature:
                raise
            _no_temperature.add(model)
            request.pop("temperature")
            response = client(base_url).chat.completions.create(**request)
        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except (TypeError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(1)
