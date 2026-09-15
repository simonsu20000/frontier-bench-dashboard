from pipeline.models import ModelRegistry, normalize_name


def test_normalize_epoch_suffix_and_dates():
    assert normalize_name("gpt-5.2-2025-12-11_none") == ("gpt-5-2-2025-12-11", "gpt-5-2", "")
    assert normalize_name("claude-fable-5-1_xhigh") == ("claude-fable-5-1", "claude-fable-5-1", "xhigh")
    assert normalize_name("grok-4-0709")[1] == "grok-4"
    assert normalize_name("openai/gpt-oss-120b_high") == ("gpt-oss-120b", "gpt-oss-120b", "high")


def test_normalize_keeps_max_in_names_unless_soft():
    assert normalize_name("Qwen3.8 Max (0902)") == ("qwen3-8-max", "qwen3-8-max", "")
    assert normalize_name("qwen3.8-max-0902_xhigh")[2] == "xhigh"
    assert normalize_name("claude-fable-5.1-max", soft_max=True) == ("claude-fable-5-1", "claude-fable-5-1", "max")
    assert normalize_name("GPT-6 Astra (Max)")[2] == "max"


def test_normalize_thinking_budget_and_parens():
    full, stripped, variant = normalize_name("claude-opus-4-1-20250805-thinking-16k")
    assert variant == "16k"
    assert full.endswith("thinking")
    assert normalize_name("Gemini 2.5 Pro (Thinking 16K)")[2] == "thinking-16k"


def test_registry_resolution(metadata):
    meta, eci = metadata
    reg = ModelRegistry.from_epoch(meta, eci, {"swebench:GPT 5.2 Codex": "gpt-5-2"})
    assert set(reg.models) == {"gpt-5-2", "claude-fable-5-1", "qwen3-8-max-0902", "gemini-2-5-pro-mar-2025",
                               "gemini-2-5-pro-jun-2025", "kimi-k2-thinking", "kimi-k2-jul-2025"}
    assert reg.models["gpt-5-2"].eci == 155.4
    assert reg.models["gpt-5-2"].release_date == "2025-12-11"
    # epoch version -> registry
    r = reg.resolve("gpt-5.2-2025-12-11_high", "epoch")
    assert (r.model_id, r.variant, r.matched_by) == ("gpt-5-2", "high", "epoch")
    # foreign spellings
    assert reg.resolve("gpt-5.2", "lmarena").model_id == "gpt-5-2"
    assert reg.resolve("GPT-5.2 (high)", "arcprize").model_id == "gpt-5-2"
    assert reg.resolve("claude-fable-5.1-max", "lmarena").variant == "max"
    assert reg.resolve("claude-fable-5.1-max", "lmarena").model_id == "claude-fable-5-1"
    assert reg.resolve("qwen3.8-max", "livebench").model_id == "qwen3-8-max-0902"
    # alias
    a = reg.resolve("GPT 5.2 Codex", "swebench")
    assert (a.model_id, a.matched_by) == ("gpt-5-2", "alias")
    # sorted-token match
    assert reg.resolve("Fable 5.1 Claude", "swebench").model_id == "claude-fable-5-1"


def test_registry_ambiguity_and_date_hint(metadata):
    meta, eci = metadata
    reg = ModelRegistry.from_epoch(meta, eci)
    amb = reg.resolve("Gemini 2.5 Pro", "swebench")
    assert amb.model_id is None
    assert ("swebench", "Gemini 2.5 Pro") in reg.ambiguous
    dated = reg.resolve("Gemini 2.5 Pro", "arcprize", date_hint="2025-06-10")
    assert (dated.model_id, dated.matched_by) == ("gemini-2-5-pro-jun-2025", "date")
    # "thinking" is part of the identity: Kimi K2 Thinking and Kimi K2 stay distinct in both directions
    assert reg.resolve("kimi-k2-thinking", "lmarena").model_id == "kimi-k2-thinking"
    assert reg.resolve("Kimi K2", "aider").model_id == "kimi-k2-jul-2025"
    # unmatched names get suggestions, never auto-applied
    assert reg.resolve("totally-new-model", "lmarena").model_id is None
    reg.note_unmatched("gpt-5.2-turbo", "lmarena", 1400.0, "lmarena-text")
    assert reg.unmatched[("lmarena", "gpt-5.2-turbo")]["suggestions"][0]["model_id"] == "gpt-5-2"
