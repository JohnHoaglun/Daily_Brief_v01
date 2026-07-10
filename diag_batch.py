#!/usr/bin/env python3
"""Quick diagnostic: see exactly what Qwen returns for batch prompt."""
import json, subprocess, time, re, sys

batch_input = """STORY_0 (Category: World): U.S. and Iran exchange attacks after Trump says ceasefire is over. Analysis of tensions between major powers.

STORY_1 (Category: Sports): Live updates on fifa world cup quarterfinals as teams advance. Barcelona hits 47 degrees during tournament excitement across europe.

STORY_2 (Category: Technology): AI companies face new regulation framework as government considers oversight requirements for large language models.

STORY_3 (Category: Market): Stock markets rally broadly as investors digest latest economic data and corporate earnings.

STORY_4 (Category: Science): NASA confirms successful landing of deep space probe carrying advanced instruments."""

SYSTEM_PROMPT = """You are a news summarization engine.
For each story, produce exactly 2-3 sentences of key facts in this EXACT format:

STORY_0: <your summary>
STORY_1: <your summary>

Rules:
- Start immediately with STORY_0 (no preamble or intro text)
- One line per story, number matches input number  
- Factual neutral tone. Nothing else."""

payload = json.dumps({
    "model": "qwen3.6-256k-agents:latest",
    "messages": [
        {"role":"system","content": SYSTEM_PROMPT},
        {"role":"user","content": batch_input}
    ],
    "stream": False,
    "options": {"temperature": 0.3, "num_ctx": 4096}
})

t0 = time.time()
args = ["curl", "-s", "--max-time", "300",
        "-X", "POST", "http://192.168.4.52:11434/api/chat",
        "-H", "Content-Type: application/json",
        "-d" + payload]  # No space after -d

p = subprocess.run(args, capture_output=True, text=True)
elapsed = time.time() - t0

resp = json.loads(p.stdout)
raw = resp["message"]["content"]

print(f"Elapsed: {elapsed:.1f}s | Response length: {len(raw)} chars\n")
print("COMPLETE OUTPUT (line by line):")
print("=" * 60)
for i, line in enumerate(raw.split("\n")):
    print(f"{i:3d}: {repr(line)}")

# Parse patterns
matches = list(re.finditer(r"STORY_(\d+)", raw))
print(f"\nFound {len(matches)} STORY_N matches:")
for m in matches:
    full = max(0, m.start()-5)
    print(f"  match at pos {m.start()}: ...{repr(raw[max(0,m.start()-10):m.end()+20])}...")

# Check if response is all thinking/reasoning (this is a reasoning model)
has_thinking_marker = "Thought:" in raw or "Thinking:" in raw or "[thinking]" in raw.lower() or "<think>" in raw

if has_thinking_marker:
    print("\n*** THIS IS THINKING BLOCK OUTPUT, NOT THE SUMMARY ***")
    msg = resp.get("message", {})
    if isinstance(msg, dict):
        reasoning_text = msg.get("thinking","") or ""
        if reasoning_text and len(reasoning_text) > 50:
            print(f"Thinking block length: {len(reasoning_text)} chars")
            print(f"Thinking (first 200): {reasoning_text[:200]}")
