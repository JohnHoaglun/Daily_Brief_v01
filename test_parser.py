import re
import unittest
from datetime import datetime, timezone

# Mocking necessary parts of dashboard_pipeline since we are testing just the parser
def _safe_sentence_summary(text):
    return text.strip()

def parse_batch_summary_response(response, count):
    """
    Redrawn from dashboard_pipeline.py for isolation testing.
    """
    results = ["" for _ in range(count)]
    if not response:
        return results

    lines = response.splitlines()

    heading_re = re.compile(
        r"^\s*(?:###\s*)?(?:\*\*)?(?:(\d+)[\)\.]\s*|STORY[_\-\s]*(\d+)\s*[:\)]?\s*)(.*)$",
        flags=re.IGNORECASE
    )

    headers = []
    story_key_re = re.compile(r"STORY[_\-\s]*(\d+)", flags=re.IGNORECASE)

    print(f"\n--- Parsing Response (count={count}) ---")
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = heading_re.match(stripped)
        if m:
            print(f"Line {i} matched heading_re: '{stripped}' | groups: {m.groups()}")
            idx_str = m.group(1) or m.group(2)
            if not idx_str:
                print(f"  No index found in group 1 or 2")
                continue
            idx = int(idx_str)
            if idx > 0:
                idx -= 1
            print(f"  Computed idx: {idx} (from raw: '{idx_str}')")
            
            if 0 <= idx < count:
                headers.append((i, idx, line))
            else:
                print(f"  Index {idx} out of bounds for count {count}")

            m2 = story_key_re.match(stripped)
            if m2 and m2.group(1):
                print(f"  Line {i} also matched story_key_re: '{stripped}' | group 1: {m2.group(1)}")
                idx_inner = int(m2.group(1))
                if idx_inner > 0:
                    idx_inner -= 1
                if 0 <= idx_inner < count:
                    if (i, idx_inner, line) not in headers:
                        headers.append((int(i), idx_inner, line))
                    else:
                        print(f"  Duplicate header prevented for index {idx_inner}")
                else:
                    print(f"  Inner index {idx_inner} out of bounds")

    if not headers:
        print("No headers found.")
        if count == 1:
            cleaned = "\n".join(
                [l for l in lines if l.strip() and not l.strip().startswith("Here are") and not l.strip().startswith("***")]
            ).strip()
            if cleaned:
                results[0] = _safe_sentence_summary(cleaned)
        return results

    normalized = []
    for line_idx, idx, raw in headers:
        normalized.append((line_idx, idx, raw))
    headers = normalized

    if count > 1 and all(h[1] is None for h in headers):
        fallback_chunks = []
        current = []
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("summary of") and i > 0:
                if current:
                    fallback_chunks.append(current)
                    current = []
            current.append(line)
        if current:
            fallback_chunks.append(current)
        for i, chunk in enumerate(fallback_chunks[:count]):
            results[i] = _safe_sentence_summary("\n".join(chunk).strip())
        return results

    for n, (line_idx, idx, raw) in enumerate(headers):
        start = line_idx
        end = len(lines)
        if n + 1 < len(headers):
            end = headers[n + 1][0]

        chunk = "\n".join(lines[start:end]).strip()
        if not chunk:
            continue
        chunk_lines = [l for l in lines[start:end] if l.strip()]

        head = raw.strip()
        summary = head
        for sep in (":", "-", ")"):
            _, sep_token, rest = head.partition(sep)
            if sep_token:
                summary = rest.strip()
                break
        if len(chunk_lines) > 1:
            summary = "\n".join(chunk_lines[1:]).strip()
        elif not summary and "." in head:
            summary = head.split(".", 1)[1].strip()
        if not summary:
            summary = "\n".join(chunk_lines).strip()

        summary = re.sub(r"^\*+\s*", "", summary)
        summary = re.sub(r"^(###\s*)?\**\d+[\)\.]\s*", "", summary)
        summary = re.sub(r"^Summary:\s*", "", summary, flags=re.IGNORECASE)
        summary = re.sub(r"\*\*|\*{2,}$", "", summary).strip()
        results[idx] = _safe_sentence_summary(summary)

    return results

class TestParser(unittest.TestCase):
    def test_standard_format(self):
        resp = "1. Story one\n2. Story two"
        expected = ["Story one", "Story two"]
        self.assertEqual(parse_batch_summary_response(resp, 2), expected)

    def test_story_key_format(self):
        resp = "STORY_0: Summary A\nSTORY_1: Summary B"
        expected = ["Summary A", "Summary B"]
        self.assertEqual(parse_batch_summary_response(resp, 2), expected)

    def test_markdown_headings(self):
        resp = "### 1. First story\nSome content here\n### 2. Second story\nMore content"
        expected = ["Some content here", "More content"]
        self.assertEqual(parse_batch_summary_response(resp, 2), expected)

    def test_single_story_fallback(self):
        resp = "Here is the summary: This is a plain text summary."
        expected = ["This is a plain text summary."]
        self.assertEqual(parse_batch_summary_response(resp, 1), expected)

    def test_out_of_bounds_ignored(self):
        resp = "5. Out of bounds\n1. In bounds"
        expected = ["In bounds", ""]
        self.assertEqual(parse_batch_summary_response(resp, 2), expected)

    def test_duplicate_indices_overwrite(self):
        resp = "1. First\n1. Second"
        expected = ["Second", ""]
        self.assertEqual(parse_batch_summary_response(resp, 2), expected)

if __name__ == "__main__":
    unittest.main()
