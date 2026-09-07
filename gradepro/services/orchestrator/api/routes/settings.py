import json
import time
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import redis.asyncio as aioredis
from app.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])


class ApiKeySchema(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    key: str
    dailyLimit: int = 1000
    active: bool = True
    createdAt: str = ""


class ApiKeysPayload(BaseModel):
    keys: List[ApiKeySchema]


class TestKeyRequest(BaseModel):
    provider: str
    key: str
    model: Optional[str] = ""


@router.get("/keys")
async def get_api_keys():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        data = await r.get("gradepro:configured_api_keys")
        if data:
            return {"keys": json.loads(data)}
        return {"keys": []}
    finally:
        await r.close()


@router.post("/keys")
async def save_api_keys(payload: ApiKeysPayload):
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        keys_dict = [k.dict() for k in payload.keys]
        await r.set("gradepro:configured_api_keys", json.dumps(keys_dict))
        return {"status": "saved", "count": len(keys_dict)}
    finally:
        await r.close()


@router.post("/test-key")
async def test_api_key(req: TestKeyRequest):
    """
    Actually calls the LLM provider with a minimal prompt to verify the key works.
    Returns real latency. Never fakes success.
    """
    provider = req.provider.lower().strip()
    api_key = req.key.strip()
    model = req.model.strip() if req.model else ""

    # Minimal test prompt — cheap single token response
    test_prompt = "Reply with only the word: OK"

    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:

            # ── OpenAI / Groq / DeepSeek / Custom ──
            if provider in ["openai", "groq", "deepseek", "custom"]:
                base_url = "https://api.openai.com/v1"
                default_model = "gpt-4o-mini"
                if provider == "groq":
                    base_url = "https://api.groq.com/openai/v1"
                    default_model = "llama-3.3-70b-versatile"
                elif provider == "deepseek":
                    base_url = "https://api.deepseek.com/v1"
                    default_model = "deepseek-chat"

                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model or default_model,
                        "messages": [{"role": "user", "content": test_prompt}],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                )
                latency_ms = round((time.perf_counter() - start) * 1000)
                if resp.status_code == 200:
                    reply = resp.json()["choices"][0]["message"]["content"].strip()
                    return {"success": True, "latency_ms": latency_ms, "reply": reply,
                            "message": f"Validated {provider.title()} connection ({model or default_model}) — Latency: {latency_ms}ms"}
                else:
                    detail = resp.json().get("error", {}).get("message", resp.text[:200])
                    return {"success": False, "latency_ms": latency_ms, "message": f"Provider rejected key: {detail}"}

            # ── Anthropic ──
            elif provider == "anthropic":
                default_model = "claude-3-haiku-20240307"
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={
                        "model": model or default_model,
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": test_prompt}],
                    },
                )
                latency_ms = round((time.perf_counter() - start) * 1000)
                if resp.status_code == 200:
                    reply = resp.json()["content"][0]["text"].strip()
                    return {"success": True, "latency_ms": latency_ms, "reply": reply,
                            "message": f"Validated Anthropic connection ({model or default_model}) — Latency: {latency_ms}ms"}
                else:
                    detail = resp.json().get("error", {}).get("message", resp.text[:200])
                    return {"success": False, "latency_ms": latency_ms, "message": f"Provider rejected key: {detail}"}

            # ── Gemini ──
            elif provider == "gemini":
                default_model = "gemini-1.5-flash"
                use_model = model or default_model
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": test_prompt}]}], "generationConfig": {"maxOutputTokens": 5}},
                )
                latency_ms = round((time.perf_counter() - start) * 1000)
                if resp.status_code == 200:
                    reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return {"success": True, "latency_ms": latency_ms, "reply": reply,
                            "message": f"Validated Gemini connection ({use_model}) — Latency: {latency_ms}ms"}
                else:
                    detail = resp.json().get("error", {}).get("message", resp.text[:200])
                    return {"success": False, "latency_ms": latency_ms, "message": f"Provider rejected key: {detail}"}

            else:
                return {"success": False, "latency_ms": 0, "message": f"Unknown provider: {provider}"}

    except httpx.TimeoutException:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"success": False, "latency_ms": latency_ms, "message": "Request timed out — check your network or the provider status."}
    except Exception as e:
        latency_ms = round((time.perf_counter() - start) * 1000)
        return {"success": False, "latency_ms": latency_ms, "message": f"Connection error: {str(e)[:200]}"}
