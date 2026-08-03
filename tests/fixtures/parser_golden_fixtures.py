"""
Golden fixtures for parse_batch_summary_response().

Each dict:
  response — the LLM response text
  headlines — story headlines (list of strings), or None
  count — number of expected story slots
  expected — list of expected summary strings (length == count)
  notes — documentation
"""

FIXTURES = [
    # ───────────────────────── 1. Canonical STORY_N | headline=summary ──────
    {
        "id": "canon_story_n_equals",
        "response": (
            "STORY_0 | Fire burns downtown=The fire destroyed three downtown buildings. "
            "Firefighters contained the blaze by evening. No injuries reported.\n"
            "STORY_1 | Mayor announces budget=The mayor announced a new budget plan. "
            "It includes funding for schools. Critics say it raises taxes too much.\n"
            "STORY_2 | Storm warning issued=A storm warning is in effect. "
            "Residents should prepare. The storm is expected to pass within hours."
        ),
        "headlines": [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ],
        "count": 3,
        "expected": [
            "The fire destroyed three downtown buildings. Firefighters contained the blaze by evening. No injuries reported.",
            "The mayor announced a new budget plan. It includes funding for schools. Critics say it raises taxes too much.",
            "A storm warning is in effect. Residents should prepare. The storm is expected to pass within hours.",
        ],
        "notes": "Canonical format with exact headline match, 3-sentence summaries.",
    },
    # ───────────────────────── 2. Reordered STORY_N with fuzzy headline ─────
    {
        "id": "story_n_reordered_fuzzy",
        "response": (
            "STORY_0 | Budget plan unveiled=The mayor announced a new budget plan. "
            "It includes funding for schools. Critics say it raises taxes too much.\n"
            "STORY_1 | Blaze in urban area=The fire destroyed three downtown buildings. "
            "Firefighters contained the blaze by evening. No injuries reported.\n"
            "STORY_2 | Severe weather alert=A storm warning is in effect. "
            "Residents should prepare. The storm is expected to pass within hours."
        ),
        "headlines": [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ],
        "count": 3,
        "expected": [
            "The fire destroyed three downtown buildings. Firefighters contained the blaze by evening. No injuries reported.",
            "The mayor announced a new budget plan. It includes funding for schools. Critics say it raises taxes too much.",
            "A storm warning is in effect. Residents should prepare. The storm is expected to pass within hours.",
        ],
        "notes": "Reordered STORY_N with paraphrased headlines requiring keyword overlap matching.",
    },
    # ───────────────────── 3. STORY_N | summary (no equals) overlap ─────────
    {
        "id": "story_n_no_equals_overlap",
        "response": (
            "STORY_0 | Three downtown buildings were destroyed by fire. Firefighters contained the blaze. No injuries.\n"
            "STORY_1 | Mayor unveils new budget for schools and raises taxes. Critics oppose the proposal.\n"
            "STORY_2 | Storm warning in effect. Residents urged to prepare for severe weather."
        ),
        "headlines": [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ],
        "count": 3,
        "expected": [
            "Three downtown buildings were destroyed by fire. Firefighters contained the blaze. No injuries.",
            "Mayor unveils new budget for schools and raises taxes. Critics oppose the proposal.",
            "Storm warning in effect. Residents urged to prepare for severe weather.",
        ],
        "notes": "STORY_N | summary (no = separator), matched by keyword overlap in summary text.",
    },
    # ───────────────────────── 4. Simple numbered list 1. 2. 3. ─────────────
    {
        "id": "numbered_simple",
        "response": (
            "1. Fire destroys downtown buildings. Firefighters contained the blaze by evening. No injuries reported.\n"
            "2. Mayor announces budget plan. It includes funding for schools.\n"
            "3. Storm warning issued for tonight. Residents should prepare."
        ),
        "headlines": None,
        "count": 3,
        "expected": [
            "Fire destroys downtown buildings. Firefighters contained the blaze by evening. No injuries reported.",
            "Mayor announces budget plan. It includes funding for schools.",
            "Storm warning issued for tonight. Residents should prepare.",
        ],
        "notes": "Simple 1-based numbered list, no headlines, positional assignment (1-based -> 0-based).",
    },
    # ───────────────────── 5. Mixed numbered formats 1. 2) ### ** ───────────
    {
        "id": "numbered_mixed_formats",
        "response": (
            "1. Fire destroys downtown. Three buildings lost.\n\n"
            "2) Mayor announces budget. Schools get new funding.\n\n"
            "### 3. Storm warning. Prepare for severe weather tonight."
        ),
        "headlines": None,
        "count": 3,
        "expected": [
            "Fire destroys downtown. Three buildings lost.",
            "Mayor announces budget. Schools get new funding.",
            "Storm warning. Prepare for severe weather tonight.",
        ],
        "notes": "Mixed header formats: 1., 2), ### 3. with continuation lines.",
    },
    # ───────────────── 6. Multi-line numbered entries ───────────────────────
    {
        "id": "numbered_multiline",
        "response": (
            "1. Downtown fire report\n"
            "   Three buildings destroyed in the blaze. Firefighters arrived within minutes. "
            "No injuries were reported.\n\n"
            "2. Mayor budget announcement\n"
            "   The mayor unveiled a new budget plan this morning. "
            "It includes new funding for schools."
        ),
        "headlines": None,
        "count": 2,
        "expected": [
            "Three buildings destroyed in the blaze. Firefighters arrived within minutes. No injuries were reported.",
            "The mayor unveiled a new budget plan this morning. It includes new funding for schools.",
        ],
        "notes": "Numbered entries with heading on first line, summary on continuation lines.",
    },
    # ──────────── 7. Summary of...: headings with sequential chunking ───────
    {
        "id": "summary_of_headings",
        "response": (
            "Summary of Fire downtown:\n"
            "Fire destroyed buildings. Contained by evening.\n\n"
            "Summary of Budget plan:\n"
            "Mayor announced budget. Schools get funding."
        ),
        "headlines": None,
        "count": 2,
        "expected": [
            "Summary of Fire downtown: Fire destroyed buildings. Contained by evening.",
            "Summary of Budget plan: Mayor announced budget. Schools get funding.",
        ],
        "notes": (
            "Summary of ...: headings with no explicit indexes — sequential chunking. "
            "Chunk includes the heading line joined with content (no line separator stripping)."
        ),
    },
    # ───────────────────── 8. Plain single-story (count=1) ──────────────────
    {
        "id": "single_plain_paragraph",
        "response": (
            "Here are the summaries:\n\n"
            "The fire destroyed three downtown buildings. Firefighters arrived quickly and "
            "contained the blaze by evening. No injuries were reported."
        ),
        "headlines": None,
        "count": 1,
        "expected": [
            "The fire destroyed three downtown buildings. Firefighters arrived quickly and contained the blaze by evening. No injuries were reported.",
        ],
        "notes": "Single-story plain paragraph with preamble. 'Here are' line filtered out.",
    },
    # ───────────────────── 9. Malformed / partial response ──────────────────
    {
        "id": "partial_malformed",
        "response": (
            "STORY_0 | Some headline=The fire was contained. No injuries.\n"
            "STORY_5 | Out of range=This should not match any story.\n"
            "1. Mayor budget. Schools get funding.\n"
            "3. Storm warning. Prepare tonight."
        ),
        "headlines": None,
        "count": 3,
        "expected": [
            "Mayor budget. Schools get funding.",
            "",
            "Storm warning. Prepare tonight.",
        ],
        "notes": (
            "Mix of STORY_0 (positional idx 0), out-of-range STORY_5 (excluded), numbered 1 → idx 0 "
            "(overwrites STORY_0), and numbered 3 → idx 2. Slot 1 is empty. "
            "Numbered entries take precedence over STORY_N entries at the same position."
        ),
    },
    # ──────────────── 10. Adjacent swap detection and repair ────────────────
    {
        "id": "adjacent_swap",
        "response": (
            "1. Fire destroys downtown. Three buildings lost.\n"
            "2. Mayor unveils budget. Schools get new funding."
        ),
        "headlines": [
            "Fire burns downtown",
            "Mayor announces budget",
        ],
        "count": 2,
        "expected": [
            "Fire destroys downtown. Three buildings lost.",
            "Mayor unveils budget. Schools get new funding.",
        ],
        "notes": (
            "Positionally correct order: 1=fire (fuzzy→idx 0), 2=mayor (fuzzy→idx 1). "
            "No swap needed — positional order matches headline order."
        ),
    },
    # ───────────────── 11. STORY_N without pipe (STORY_N: variant) ──────────
    {
        "id": "story_n_colon_variant",
        "response": (
            "STORY_0: The fire destroyed downtown buildings. Firefighters contained the blaze. No injuries.\n"
            "STORY_1: Mayor announced new budget. Schools get funding. Critics oppose taxes."
        ),
        "headlines": None,
        "count": 2,
        "expected": [
            "Mayor announced new budget. Schools get funding. Critics oppose taxes.",
            "",
        ],
        "notes": (
            "STORY_N: variant (no pipe, colon separator). Without headlines, initial STORY_N parsing skipped. "
            "Positional fallback: STORY_0 → idx 0, STORY_1 → idx 0 (decremented). Both map to 0, "
            "so second entry overwrites first. Slot 0 gets STORY_1 text, slot 1 empty."
        ),
    },
    # ─────────────── 12. STORY_N with STORY-1 and STORY 2 variants ──────────
    {
        "id": "story_n_dash_space_variants",
        "response": (
            "STORY-0 | Downtown fire: three buildings destroyed. No injuries reported.\n"
            "STORY 1 | Mayor announces new budget plan for the city. Schools get funding."
        ),
        "headlines": None,
        "count": 2,
        "expected": [
            "STORY 1 | Mayor announces new budget plan for the city. Schools get funding.",
            "",
        ],
        "notes": (
            "STORY-0 and STORY 1 variants without headlines. Positional fallback captures both. "
            "STORY-0 → idx 0 (no pipe parsed by positional regex), STORY 1 → idx 0 (decremented). "
            "Both map to slot 0; second overwrites first. Raw line is the 'summary' "
            "(positional parser can't strip pipe formatting). "
        ),
    },
    # ──────────── 13. Trimming: sentence summary trim ────────────────────────
    {
        "id": "sentence_trimming",
        "response": (
            "1. The fire started at dusk. It spread quickly through three buildings. "
            "Firefighters arrived within minutes. They contained the blaze by evening. "
            "No injuries were reported. Cleanup will take months.\n"
            "2. The mayor announced it. Schools get funding. Taxes will rise slightly."
        ),
        "headlines": None,
        "count": 2,
        "expected": [
            "The fire started at dusk. It spread quickly through three buildings. Firefighters arrived within minutes.",
            "The mayor announced it. Schools get funding. Taxes will rise slightly.",
        ],
        "notes": "_safe_sentence_summary trims story 1 to 3 sentences (6 input → 3 output). Story 2 is exactly 3.",
    },
    # ─────────── 14. STORY_N headline match already matched, skip positional ─
    {
        "id": "story_headline_overlap_skip",
        "response": (
            "STORY_0 | Fire burns downtown=Three buildings destroyed in the blaze.\n"
            "1. Mayor announces budget. Schools get new funding.\n"
            "2. Storm warning issued. Prepare tonight.\n"
        ),
        "headlines": [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ],
        "count": 3,
        "expected": [
            "Three buildings destroyed in the blaze.",
            "",
            "Storm warning issued. Prepare tonight.",
        ],
        "notes": (
            "STORY_0 matched by headline fuzzy → idx 0 (matched_by_headline). "
            "Positional 1. → idx 0, already in matched_by_headline → skipped. "
            "Positional 2. → idx 1, but fuzzy headline match redirects fuzzy_idx→2 "
            "(storm/warn/issu overlap with headline 2 = 100%). So target_idx=2, not 1. "
            "Slot 1 empty (mayor headline not assigned), slot 2 has storm warning."
        ),
    },
    # ───────── 15. Reordered numbered with fuzzy positional remapping ────────
    {
        "id": "numbered_reordered_fuzzy",
        "response": (
            "1. Mayor unveils budget plan. Schools get new funding.\n"
            "2. Storm warning in effect. Prepare for severe weather tonight.\n"
            "3. Fire destroys three downtown buildings. No injuries.\n"
        ),
        "headlines": [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ],
        "count": 3,
        "expected": [
            "Fire destroys three downtown buildings. No injuries.",
            "Mayor unveils budget plan. Schools get new funding.",
            "",
        ],
        "notes": (
            "Numbered out of order: 1=mayor (fuzzy→idx 1), 2=storm (positional idx 1), "
            "3=fire (fuzzy→idx 0). Slot 2 empty — fuzzy remapping of 2→1 overwrites slot 1 "
            "and slot 2 never filled. Documents data loss from duplicate fuzzy targets."
        ),
    },
]
