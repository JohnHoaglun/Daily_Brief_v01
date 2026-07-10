#!/usr/bin/env python3
"""Debug batch summarization: show exactly what Qwen returns for our prompt format."""

import asyncio, aiohttp, feedparser, json, time, sys
from bs4 import BeautifulSoup

RSS_BASE = "https://news.google.com/rss/search?q="
RSS_PARAMS = "&hl=en-US&gl=US&ceid=US:en"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

OLLAMA_HOST = "http://192.168.4.52:11434"
QWEN_MODEL = "qwen3.6-256k-agents:latest"

import ollama
_qwen_client = ollama.Client(host=OLLAMA_HOST)


def strip_html(raw):
    if not raw:
        return ""
    s = BeautifulSoup(raw, "html.parser")
    return s.get_text(separator=" ", strip=True)


def normalize_title(title):
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    return (parts[0] if parts else title.lower().strip())[:80].lower()


async def fetch_sample():
    """Fetch up to 3 diverse stories from RSS."""
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        queries = [("World News", "world+news", 10), ("US News", "US+news", 10)]
        results = []
        seen = set()
        
        for name, query, mx in queries:
            if len(results) >= 3:
                break
            url = f"{RSS_BASE}{query}{RSS_PARAMS}"
            async with session.get(url) as resp:
                text = await resp.text()
            feed = feedparser.parse(text)
            for entry in feed.entries[:mx]:
                title = (entry.get("title", "") or "").strip() if isinstance(entry.get("title"), str) else ""
                raw = (entry.get("summary") or entry.get("description") or "").strip() if isinstance(entry.get("summary"), str) and entry["summary"] else ""
                plain = strip_html(raw)
                norm = normalize_title(title)
                if norm in seen:
                    continue
                seen.add(norm)
                results.append({
                    "category": name,
                    "title": title,
                    "snippet": plain,
                })
                if len(results) >= 3:
                    break
        return results


def build_context(s):
    """Build summary context from snippet + title (since article extraction is dead)."""
    parts = [v.strip() for v in [s["snippet"], s["title"]] 
             if v and len((v or "").strip()) > 0]
    if not parts:
        return f"{s['category']}: {s['title']}"
    return "\n---\n".join(parts + [f"Category: {s['category']}"])


def main():
    stories = asyncio.run(fetch_sample())
    print(f"Collected {len(stories)} stories\n")
    for i, s in enumerate(stories):
        ctx = build_context(s)
        s["_ctx"] = ctx
        print(f"--- Story {i} ---")
        print(f"  Title:   {s['title'][:80]}")
        print(f"  Snippet:  {len(s['snippet'])} chars")
        print(f"  Context:  {ctx[:60]}...")
        print()

    # Try BOTH prompt styles and compare actual outputs
    SYSTEM_STYLE_A = ("You are a news summarization engine. For EACH story, output EXACTLY ONE line.\n"
                      "Format: STORY_<number>: <two-sentence summary>\n"
                      "No preamble, no bullet points. Match the story numbers exactly.")

    SYSTEM_STYLE_B = ("You are an objective news editor.\n"
                      "For each story labeled STORY_N, produce a 2-3 sentence factual summary.\n"
                      "Label each with its exact number. Example:\n"
                      "STORY_0: The president announced...\n"
                      "STORY_1: Markets rallied as...\n\n"
                      "No preamble or intro text. Start directly with STORY_0")

    batch_text = "\n\n".join(
        f"STORY_{i} (Category: {s['category']}): {s['_ctx']}"
        for i, s in enumerate(stories)
    )

    tests = [
        ("A", SYSTEM_STYLE_A),
        ("B", SYSTEM_STYLE_B),
    ]

    responses = {}

    for tag, system_prompt in tests:
        print("=" * 70)
        print(f"PROMPT STYLE {tag}:")
        print(system_prompt)
        print(f"\nUSER CONTENT:\n{batch_text}\n{'='*70}")
        
        t0 = time.time()
        try:
            r = _qwen_client.chat(
                model=QWEN_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": batch_text}
                ],
                options={"temperature": 0.3, "top_p": 0.8, "num_ctx": 4096}
            )
            elapsed = time.time() - t0
            raw = r["message"]["content"]
            print(f'\n{"="*70}')
            print(f"Response ({elapsed:.1f}s):\n{'='*70}")
            if len(raw) > 2000:
                print(raw[:800] + f"\n...[{len(raw)} total chars]")
            else:
                print(raw)
            
            # Analyze parseability
            lines = [l.strip() for l in raw.split('\n') if l.strip()]
            story_matches = 0
            for line in lines:
                if line.startswith(f'STORY_{stories.count(stories)}') or any(f'STORY_{j}:' in line for j in range(5)):
                    story_matches += 1
            
            # Count how many STORY_N: patterns actually appear
            import re
            found_ids = [m.group(1) for m in re.finditer(r'STORY_(\d+)', raw)]
            print(f"\nFOUND STORY_IDs in response: {found_ids}")
            
            responses[tag] = raw
        except Exception as e:
            print(f"ERROR: {e}\n")
            responses[tag] = str(e)

    # Now test with curl too — same prompt, compare latency and output
    import subprocess
    system_prompt = SYSTEM_STYLE_B
    payload = json.dumps({
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": batch_text}
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 4096}
    })

    print(f"\n{'='*70}")
    print("CURL ALTERNATIVE (same prompt B):")
    print("=" * 70)
    t0 = time.time()
    r = subprocess.run(['curl','-s','--max-time',300,
        '-X','POST', 'http://192.168.4.52:11434/api/chat',
        '-H','Content-Type: application/json',' -d', payload],
    capture_output=True, text=True)
    elapsed = time.time() - t0
    resp_dict = json.loads(r.stdout) if r.stdout else {}
    raw = resp_dict.get('message', {}).get('content', 'EMPTY')
    print(f"Response ({elapsed:.1f}s):\n{raw[:600]}")
    
    # Summary of what we need to fix in pipeline parser
    print(f"\n\n{'='*70}")
    print("PARSING DIAGNOSTIC:")
    print("=" * 70)
    for tag, resp in responses.items():
        lines = [l.strip() for l in (resp or '').split('\n') if l.strip()]
        print(f"\nStyle {tag} — {len(lines)} output lines:")
        for line in lines[:6]:
            print(f"  [{line[:80]}]")


if __name__ == "__main__":
    main()
