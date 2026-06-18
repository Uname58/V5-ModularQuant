"""
News Monitor — S/A/B/C event grading, S-level triggers risk pause.
Runs as cron job or manual check. Integrates with risk_controller.
"""
import json, os, re, datetime, urllib.request, hashlib

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
V5_DIR = os.path.dirname(SCRIPTS_DIR) if os.path.basename(SCRIPTS_DIR) == "monitoring" else os.path.dirname(SCRIPTS_DIR)
STATE_FILE = os.path.join(V5_DIR, "data", "news_state.json")
JOURNAL_FILE = os.path.join(V5_DIR, "logs", "news_journal.jsonl")

# ═══════════════════════════════════════════
# S/A/B/C CLASSIFIER
# ═══════════════════════════════════════════

# False positive blocklist — demote S matches that are figurative/historical
S_TO_B_BLOCKLIST = [
    r"\bcold war\b", r"\bworld war (i|ii|1|2)\b",
    r"\bbidding war\b", r"\bprice war\b", r"\bcpi war\b",
    r"\bwar (room|chest)\b", r"\bwar on (fraud|drugs|poverty|cancer)\b",
    r"\bwar (ready|game|movie|film|series|book|novel)\b",
    r"\bstar wars\b", r"\bwar eagle\b", r"\bwar memorial\b", r"\bwarriors?\b",
]

S_TO_A_BLOCKLIST = [
    r"\bnuclear (energy|plant|reactor|power|fusion)\b",
    r"\bsanctions? (screening|check|compliance|list)\b",
]

S_KEYWORDS_PATTERNS = [
    r"\bwar(s|fare)?\b", r"\bstrike(s|d)?\b", r"\bmissile(s)?\b", r"\binvasion\b",
    r"\bmilitary attack", r"\bnuclear\b", r"\bair strike",
    r"\btroops deployed\b", r"\bdeclares? war\b", r"\bmilitary conflict",
    r"\bexchange hack(ed|ing)?\b", r"\bexchange shutdown\b",
    r"\bregulatory ban\b", r"\btrading halt(ed)?\b",
    r"\bsanctions?\b", r"\bembargo(es)?\b", r"\bterrorist attack",
    r"\bcoup\b", r"\bmartial law\b", r"\bemergency act",
    r"\bcapital controls\b", r"\bsovereign default\b",
    r"\bdowned\b", r"\bshot down\b", r"\bhelicopter crash\b",
]
A_KEYWORDS_PATTERNS = [
    r"\bsec\b", r"\bcftc\b", r"\bregulation\b", r"\bregulatory\b", r"\blawsuit\b", r"\bcourt ruling\b",
    r"\betf\b", r"\bexchange listing\b", r"\bdelisting\b", r"\bmajor upgrade\b", r"\bhard fork\b",
    r"\binterest rate\b", r"\bfederal reserve\b", r"\bfed decision\b", r"\bcpi\b", r"\binflation data\b",
    r"\bgdp\b", r"\bnonfarm payroll\b", r"\bpolicy change\b", r"\bexecutive order\b",
]
B_KEYWORDS_PATTERNS = [
    r"\bpartnership\b", r"\bfunding\b", r"\braise\b", r"\blaunch\b", r"\bmainnet\b", r"\btestnet\b",
    r"\bacquisition\b", r"\bmerger\b", r"\bceo\b", r"\blayoff\b", r"\bquarterly report\b",
    r"\brevenue\b", r"\bburn\b", r"\btoken unlock\b", r"\bairdrop\b",
]

C_PATTERNS = [
    r"(?i)price.*prediction",
    r"(?i)will.*reach.*\$",
    r"(?i)analyst.*says",
    r"(?i)could.*go.*to",
    r"(?i)top.*\d.*coins.*to.*buy",
    r"(?i)next.*100x",
]


def classify(title: str, source: str = "") -> dict:
    """Classify a news headline into S/A/B/C with metadata."""
    text = title.lower()

    # Check S-level first (word-boundary regex)
    for pat in S_KEYWORDS_PATTERNS:
        if re.search(pat, text):
            # Blocklist check — demote false positives
            for block in S_TO_B_BLOCKLIST:
                if re.search(block, text):
                    return {"level": "B", "reason": f"demoted S→B: {block}", "source": source,
                            "risk_pause": False}
            for block in S_TO_A_BLOCKLIST:
                if re.search(block, text):
                    return {"level": "A", "reason": f"demoted S→A: {block}", "source": source,
                            "risk_pause": False}
            return {"level": "S", "reason": f"pattern: {pat}", "source": source,
                    "risk_pause": True}

    # C-level (noise filter)
    for pat in C_PATTERNS:
        if re.search(pat, text):
            return {"level": "C", "reason": "noise pattern match", "source": source,
                    "risk_pause": False}

    # A-level
    for pat in A_KEYWORDS_PATTERNS:
        if re.search(pat, text):
            return {"level": "A", "reason": f"pattern: {pat}", "source": source,
                    "risk_pause": False}

    # B-level
    for pat in B_KEYWORDS_PATTERNS:
        if re.search(pat, text):
            return {"level": "B", "reason": f"pattern: {pat}", "source": source,
                    "risk_pause": False}

    return {"level": "B", "reason": "default", "source": source, "risk_pause": False}


# ═══════════════════════════════════════════
# NEWS FETCHING
# ═══════════════════════════════════════════

def fetch_google_news(keywords: list[str] = None) -> list[dict]:
    """Fetch crypto/macro headlines from Google News RSS."""
    if keywords is None:
        keywords = ["crypto", "bitcoin", "fed", "regulation", "war", "iran"]
    items = []
    for kw in keywords:
        url = f"https://news.google.com/rss/search?q={urllib.request.quote(kw)}&hl=en-US&ceid=US:en"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "V5-NewsMonitor/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8")
            import xml.etree.ElementTree as ET
            root = ET.fromstring(data)
            for item_elem in root.iter("item"):
                title = item_elem.find("title").text if item_elem.find("title") is not None else ""
                source = item_elem.find("source").text if item_elem.find("source") is not None else ""
                pub = item_elem.find("pubDate").text if item_elem.find("pubDate") is not None else ""
                items.append({"title": title, "source": source, "pub_date": pub})
        except Exception as e:
            print(f"[News] fetch error for '{kw}': {e}")
    return items


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove near-duplicate headlines by hash of first 80 chars."""
    seen = set()
    unique = []
    for item in items:
        h = hashlib.md5(item["title"][:80].encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(item)
    return unique


# ═══════════════════════════════════════════
# STATE MANAGEMENT
# ═══════════════════════════════════════════

def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"risk_pause": False, "active_s_events": [], "last_check": ""}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_risk_paused() -> bool:
    """Check if trading is currently blocked by active S-level events."""
    state = load_state()
    return state.get("risk_pause", False)


def clear_risk_pause():
    """Manually clear risk pause (called after human review)."""
    state = load_state()
    state["risk_pause"] = False
    state["active_s_events"] = []
    save_state(state)
    return {"status": "cleared"}


# ═══════════════════════════════════════════
# MAIN SCAN
# ═══════════════════════════════════════════

def run_scan() -> dict:
    """Fetch, classify, deduplicate, return alert-worthy events."""
    os.makedirs(os.path.dirname(JOURNAL_FILE), exist_ok=True)
    items = fetch_google_news()
    items = deduplicate(items)

    results = {"s_events": [], "a_events": [], "b_count": 0, "c_count": 0, "total": len(items)}

    for item in items:
        grade = classify(item["title"], item.get("source", ""))
        item["level"] = grade["level"]
        item["reason"] = grade["reason"]
        item["risk_pause"] = grade["risk_pause"]

        if grade["level"] == "S":
            results["s_events"].append(item)
        elif grade["level"] == "A":
            results["a_events"].append(item)
        elif grade["level"] == "B":
            results["b_count"] += 1
        else:
            results["c_count"] += 1

        # Journal all
        with open(JOURNAL_FILE, "a") as f:
            f.write(json.dumps({**item, "scanned_at": datetime.datetime.now().isoformat()}) + "\n")

    # Update state if S-level found
    if results["s_events"]:
        state = load_state()
        state["risk_pause"] = True
        state["active_s_events"] = results["s_events"]
        state["last_check"] = datetime.datetime.now().isoformat()
        save_state(state)
        results["risk_pause_triggered"] = True
    else:
        state = load_state()
        state["last_check"] = datetime.datetime.now().isoformat()
        save_state(state)
        results["risk_pause_triggered"] = False

    results["risk_pause_active"] = is_risk_paused()
    return results


# ═══════════════════════════════════════════
# TELEGRAM OUTPUT
# ═══════════════════════════════════════════

def format_report(results: dict) -> str:
    """Format scan results for Telegram delivery."""
    lines = ["🔍 V5 News Scan", ""]

    if results["risk_pause_triggered"]:
        lines.append("🚨🚨🚨 S-LEVEL EVENT DETECTED — RISK PAUSE ACTIVATED 🚨🚨🚨")
        lines.append("Trading halted until manual review.")
        lines.append("")
        for e in results["s_events"]:
            lines.append(f"  ⛔ {e['title']}")
            lines.append(f"     Source: {e['source']} | Reason: {e['reason']}")
        lines.append("")

    if results["a_events"]:
        lines.append(f"⚠️  A-Level Events ({len(results['a_events'])}):")
        for e in results["a_events"][:5]:
            lines.append(f"  • {e['title']}")
        lines.append("")

    lines.append(f"Total: {results['total']} articles scanned")
    lines.append(f"  S: {len(results['s_events'])} | A: {len(results['a_events'])} | B: {results['b_count']} | C: {results['c_count']}")
    lines.append(f"  Risk Pause: {'🔴 ACTIVE' if results['risk_pause_active'] else '🟢 CLEAR'}")

    return "\n".join(lines)


if __name__ == "__main__":
    results = run_scan()
    print(format_report(results))
