import os
import httpx
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("OPENROUTER_API_KEY", "")

models = httpx.get("https://openrouter.ai/api/v1/models").json()["data"]
free_ids = [
    m["id"] for m in models
    if m["id"].endswith(":free")
    and "embed" not in m["id"]
    and "rerank" not in m["id"]
    and "decider" not in m["id"]
]

print(f"Testing {len(free_ids)} free models...\n")
for mid in free_ids:
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": mid,
                "reasoning": {"effort": "none"},
                "max_tokens": 50,
                "messages": [{"role": "user", "content": 'Return ONLY: {"ok":true}'}],
            },
            timeout=15.0,
        )
        if r.status_code == 200:
            msg = r.json()["choices"][0]["message"]
            out = (msg.get("content") or msg.get("reasoning") or "").strip().replace("\n", " ")
            print(f"✅ {mid}  -->  {out[:60]}")
        else:
            print(f"❌ {mid}  -->  HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ {mid}  -->  {type(e).__name__}")