# T1/T2 Analysis: Google News RSS Structure (Jul 9, 2026)

## Current Status
- **All `<link>` fields are Google tracking IDs** — no real publisher URLs anywhere
- `source` field gives publisher name + domain (e.g. `{href:'https://www.cnbc.com', title:'CNBC'}`)
- Descriptions strip down to ~50-95 chars of plain text → basically just title repetition + source name
- Alternative Google News parameters (`hl`, `gl`) don't change the tracking ID format

## Available Context Per Story
| Source | Avg Length | Usable Content |
|--------|-----------|----------------|
| Title | 60-150 chars | Full headline, sometimes includes publisher suffix |
| Stripped description | 50-95 chars | Mostly title repeated + source name (the `<a>` link text) |
| `source.title` | varies | Just the publisher name ("CNBC", "Reuters", etc.) |
| `pubDate` | varies | Accurate publication timestamp |

## What Changed (vs ~48h ago)
**This is the key question T3-T5 will answer.** Possibilities:
1. Google changed their RSS format permanently (tracking IDs, minimal descriptions) ✓ This appears confirmed now
2. We broke something in our parser that caused us to lose context that was previously available  
3. Both

## Next Tests Plan

### T3: Restore Check
- Reproduce exact same pipeline behavior as old runs
- Feed sample stories with known article text into Qwen (from cached files) → measure summary quality
- If summaries are good with real article text, confirm extraction is needed (not a prompt issue)

### T4: Test Title-Only Summarization
- Run batch queries containing ONLY title + source name
- Measure: factual accuracy, specificity, hallucination rate
- Determine if Qwen can add value via knowledge-augmentation given just titles

### T5: Context Enhancement Experiments  
- Test various prompt approaches to maximize utility from ~100 chars of context
- Compare plain batch vs structured extraction prompts
