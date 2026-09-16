"""Heuristic filtering of new-benchmark candidates: dedupe, score, tag, extract claims."""
from __future__ import annotations

import re
from collections import defaultdict

ARXIV_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
TITLE_KW = re.compile(r"\b(bench(?:mark)?s?|eval(?:uation)?s?|leaderboards?|arena|exam|suite|testbed|test ?sets?)\b", re.I)
TITLE_NAME = re.compile(r"\b[A-Z][\w]*-?(?:Bench|Eval|QA|Arena|Exam|Verse|Suite)(?:-[A-Za-z0-9]+)*\b")
INTRO = re.compile(r"\bwe (?:introduce|present|propose|release|build|curate|construct|develop|create)\b(?:\s+[\w\-,()]+){0,7}?\s+"
                   r"(?:benchmark|evaluation (?:suite|framework|benchmark|testbed)|testbed|leaderboard|dataset (?:for|to) (?:evaluat|assess|measur)\w*|"
                   r"suite of (?:tasks|tests|evaluations))", re.I)
EVAL_TARGET = re.compile(r"\b(?:evaluat|assess|measur|test)\w*\s+(?:\w+\s+){0,3}?(?:LLMs?|large language models?|language models?|agents?|VLMs?|MLLMs?|LVLMs?|"
                         r"foundation models?|frontier models?|multimodal models?|AI (?:systems|models|agents))\b", re.I)
OPEN = re.compile(r"\b(?:code|data|dataset|benchmark|leaderboard)s?\b[^.]{0,50}\b(?:publicly |openly )?(?:available|released|open-?sourced?)\b", re.I)
SURVEY = re.compile(r"\b(survey|position paper|tutorial|perspective|roadmap|opinion|systematic review)\b", re.I)
VERB_ONLY = re.compile(r"\bwe benchmark\b", re.I)
METHOD = re.compile(r"\bwe propose (?:a|an|the) (?:novel |new |simple |unified )?(?:method|framework|approach|model|algorithm|architecture|technique)\b", re.I)
OUTPERF = re.compile(r"\b(outperform|surpass|state-of-the-art (?:results|performance)|improv\w+ over)\b", re.I)
BEST_CLAIM = re.compile(
    r"(?:best|strongest|top|leading|state-of-the-art|SOTA|frontier|even|most capable)\W+(?:[\w\-\.]+\W+){0,6}?(?:models?|systems?|LLMs?|agents?)\W+"
    r"(?:[\w\-\.]+\W+){0,6}?(?:achiev|reach|attain|obtain|scor|solv|succeed|complet)\w*\W+(?:only|just|merely|a mere|at most)?\W*(?:an?\s+)?"
    r"(?:accuracy|score|pass@1|success rate|F1|resolve rate)?(?:\s+of)?\s*(\d{1,3}(?:\.\d+)?)\s?%", re.I)
MODEL_ONLY = re.compile(r"\b(GPT-?[456o][\w\.\-]*|o[1345](?:-mini|-pro)?|Claude[\w\.\- ]{0,20}|Gemini[\w\.\- ]{0,20}|DeepSeek[\w\.\-]*|Qwen[\w\.\-]*|Grok[\w\.\-]*)"
                        r"\b[^.]{0,80}?\b(?:only|just|merely)\s+(\d{1,3}(?:\.\d+)?)\s?%", re.I)
HUMAN = re.compile(r"\b(human|expert|annotator|crowd)", re.I)
DELTA = re.compile(r"\b(improv|gain|increase|boost|relative|drop|decreas|reduc|higher than|lower than|compared)", re.I)


def arxiv_id(*texts) -> str | None:
    for t in texts:
        if not t:
            continue
        m = re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", str(t), re.I) or re.fullmatch(r"\s*(\d{4}\.\d{4,5})(?:v\d+)?\s*", str(t))
        if m:
            return m.group(1)
    return None


def norm_url(u: str) -> str:
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = u.split("?")[0].split("#")[0].rstrip("/")
    return re.sub(r"v\d+$", "", u) if "arxiv.org" in u else u


def candidate_key(c: dict) -> str:
    aid = c.get("arxiv_id") or arxiv_id(c.get("url"), c.get("code_url"), c.get("hf_url"))
    if aid:
        c["arxiv_id"] = aid
        return f"arxiv:{aid}"
    if c.get("kind") == "dataset" and c.get("repo"):
        return f"hf-ds:{c['repo']}"
    if c.get("kind") == "space" and c.get("repo"):
        return f"hf-sp:{c['repo']}"
    if c.get("kind") == "epoch" and c.get("slug"):
        return f"epoch:{c['slug']}"
    return f"url:{norm_url(c.get('url') or c.get('title') or '')}"


def norm_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


NAME_FROM_TITLE = re.compile(r"^\s*([A-Za-z][\w\-\.\+/]*(?:\s+[A-Za-z0-9][\w\-\.\+]*){0,3}?)\s*[:\-–—]\s")


def extract_name(title: str) -> str:
    title = (title or "").strip()
    m = NAME_FROM_TITLE.match(title)
    if m and len(m.group(1)) <= 40:
        return m.group(1).strip()
    m = TITLE_NAME.search(title)
    if m:
        return m.group(0)
    words = title.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")


def extract_best(text: str) -> dict | None:
    """Best-model score claimed in an abstract, e.g. 'the best model achieves only 23.4%'."""
    if not text:
        return None
    found: list[float] = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if DELTA.search(sent):
            continue
        for m in BEST_CLAIM.finditer(sent):
            window = sent[max(0, m.start() - 60):m.start()]
            if HUMAN.search(window) or HUMAN.search(m.group(0)):
                continue
            v = float(m.group(1))
            if 0 < v < 100:
                found.append(v)
        for m in MODEL_ONLY.finditer(sent):
            v = float(m.group(2))
            if 0 < v < 100:
                found.append(v)
    if not found:
        return None
    return {"score": min(found), "metric": "reported", "source": "abstract"}


def tag_domain(text: str, domains_cfg: dict, title: str = "") -> str:
    """Weighted keyword vote; title hits count triple."""
    t = (text or "").lower()
    ti = (title or "").lower()
    best, best_n = "other", 0
    for did, cfg in domains_cfg.items():
        n = 0
        for kw in cfg.get("keywords", []):
            kw = kw.lower()
            rx = r"\b" + re.escape(kw) + (r"\w*" if len(kw) > 3 else r"\b")
            n += len(re.findall(rx, t)) + 3 * len(re.findall(rx, ti))
        if n > best_n:
            best, best_n = did, n
    return best


def score(c: dict, cfg: dict) -> tuple[int, list[str]]:
    T = c.get("title") or ""
    A = c.get("abstract") or ""
    kind = c.get("kind")
    tags = [str(t).lower() for t in (c.get("tags") or [])]
    s, why = 0, []
    if kind == "epoch":
        return 10, ["tracked by Epoch AI"]
    if TITLE_KW.search(T):
        s += 3; why.append("title keyword")
    if TITLE_NAME.search(T):
        s += 2; why.append("name pattern")
    intro = bool(INTRO.search(A))
    if intro:
        s += 3; why.append("introduces a benchmark")
    if EVAL_TARGET.search(A):
        s += 1; why.append("evaluates models")
    terms = cfg.get("frontier_model_terms") or []
    if any(re.search(r"\b" + re.escape(t) + r"\b", A) for t in terms):
        s += 1; why.append("frontier models named")
    if c.get("best_reported"):
        s += 2; why.append("reports best score")
    if OPEN.search(A):
        s += 1; why.append("artifacts released")
    if len(set(c.get("sources") or [])) >= 2:
        s += 2; why.append("multiple sources")
    if (c.get("upvotes") or 0) >= 10:
        s += 1; why.append("HF upvotes")
    if kind == "dataset" and any(t in ("benchmark", "evaluation", "eval", "leaderboard") for t in tags):
        s += 2; why.append("dataset tagged benchmark")
    if kind == "space":
        if any(t == "leaderboard" or t.startswith(("eval:", "judge:", "test:")) for t in tags):
            s += 3; why.append("leaderboard space")
        else:
            s += 1
    if SURVEY.search(T):
        s -= 3; why.append("survey/position")
    neg = cfg.get("negative_terms") or []
    hay = (T + " " + A[:600]).lower()
    if any(n.lower() in hay for n in neg):
        s -= 3; why.append("non-ML domain")
    if str(c.get("announce_type") or "").startswith("replace"):
        s -= 2; why.append("arXiv replacement")
    if VERB_ONLY.search(A) and not intro:
        s -= 2; why.append("benchmark as verb")
    if METHOD.search(A) and OUTPERF.search(A) and not intro and not TITLE_KW.search(T):
        s -= 2; why.append("method paper")
    return s, why


def merge(cands: list[dict]) -> list[dict]:
    """Merge duplicates by key, then by normalised name. Unions sources, keeps earliest date."""
    def combine(a: dict, b: dict) -> dict:
        out = dict(a)
        out["sources"] = sorted(set(a.get("sources") or []) | set(b.get("sources") or []))
        for k in ("abstract", "title", "url", "code_url", "hf_url", "org", "authors", "arxiv_id", "repo"):
            if not out.get(k) and b.get(k):
                out[k] = b[k]
        if b.get("abstract") and len(b["abstract"]) > len(out.get("abstract") or ""):
            out["abstract"] = b["abstract"]
        if b.get("date") and (not out.get("date") or b["date"] < out["date"]):
            out["date"] = b["date"]
        out["upvotes"] = max(a.get("upvotes") or 0, b.get("upvotes") or 0)
        out["tags"] = sorted(set(a.get("tags") or []) | set(b.get("tags") or []))
        # a paper beats a dataset/space entry for identity
        if b.get("kind") == "paper" and out.get("kind") != "paper":
            out["kind"], out["url"], out["title"] = "paper", b.get("url") or out.get("url"), b.get("title") or out.get("title")
        return out

    by_key: dict[str, dict] = {}
    for c in cands:
        c.setdefault("sources", [c.get("source")] if c.get("source") else [])
        k = candidate_key(c)
        c["key"] = k
        by_key[k] = combine(by_key[k], c) if k in by_key else c
    by_name: dict[str, str] = {}
    out: dict[str, dict] = {}
    for k, c in by_key.items():
        c["name"] = c.get("name") or extract_name(c.get("title") or "")
        nn = norm_name(c["name"])
        c["name_norm"] = nn
        if nn and len(nn) >= 4 and nn in by_name:
            tgt = by_name[nn]
            out[tgt] = combine(out[tgt], c)
            continue
        if nn and len(nn) >= 4:
            by_name[nn] = k
        out[k] = c
    return list(out.values())
