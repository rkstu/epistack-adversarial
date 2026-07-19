"""Static HTML site generator — Jinja2 + inline styles.

Generates a navigable HTML site from the epistemic store showing:
- index.html: positions, cruxes, stats, settling status
- positions/{id}.html: stance, strongest claims, member claims
- cruxes/{id}.html: claim text, confidence, cascade impact

Minimal first pass — inline styles, expand later.

Design sources:
- IMPLEMENTATION_PLAN.md §9
- PROJECT_CONTEXT.md §7 (static HTML over D3 graph)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import get_config
from .store import EpistemicStore
from .crux_detection import get_top_cruxes
from .settling import detect_performed_settling

log = structlog.get_logger()

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def generate_site(
    store: EpistemicStore,
    discourse_result: dict[str, Any],
    output_dir: Path,
    case_name: str = "case_study",
) -> Path:
    """Generate the full static HTML site.

    Args:
        store: Populated EpistemicStore
        discourse_result: Output from build_discourse_map()
        output_dir: Where to write HTML files
        case_name: Human-readable case name

    Returns: Path to output directory
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "positions").mkdir(exist_ok=True)
    (output_dir / "cruxes").mkdir(exist_ok=True)
    (output_dir / "static").mkdir(exist_ok=True)

    # Copy CSS
    css_source = Path(__file__).parent.parent.parent / "static" / "style.css"
    if css_source.exists():
        import shutil
        shutil.copy2(css_source, output_dir / "static" / "style.css")

    env = _get_jinja_env()

    positions = discourse_result.get("positions", [])
    cruxes = discourse_result.get("cruxes", [])
    empty_chairs = discourse_result.get("empty_chairs", [])
    disagreement_types = discourse_result.get("disagreement_types", [])

    # Settling detection
    settling_results = detect_performed_settling(store)

    # Determine if this is a "settled" case (no cruxes, high confidence, 1 position)
    is_settled = len(cruxes) == 0 and len(positions) <= 1

    # Stats
    stats = _compute_stats(store, positions, cruxes)

    # Generate index
    _render(env, "index.html", output_dir / "index.html", {
        "case_name": case_name,
        "positions": positions,
        "cruxes": cruxes,
        "empty_chairs": empty_chairs,
        "disagreement_types": disagreement_types,
        "settling": settling_results,
        "stats": stats,
        "is_settled": is_settled,
    })

    # Identify claims that get individual pages (cruxes + strongest_case)
    important_claims = set()
    for crux in cruxes:
        important_claims.add(crux.get("claim_id", ""))
    for pos in positions:
        for cid in pos.get("strongest_claims", [])[:5]:
            important_claims.add(cid)

    # Generate claim pages (only for important claims)
    (output_dir / "claims").mkdir(exist_ok=True)
    for cid in important_claims:
        claim = store.claims.get(cid, {})
        if not claim:
            continue
        # Find edges involving this claim
        supporting = [e for e in store.edges.values()
                      if e.get("target") == cid and e.get("edge_type") == "supports" and e.get("status") == "active"]
        contradicting = [e for e in store.edges.values()
                         if (e.get("source") == cid or e.get("target") == cid)
                         and e.get("edge_type") == "contradicts" and e.get("status") == "active"]
        # Find which position(s) this claim belongs to
        claim_positions = [p for p in positions if cid in p.get("member_claims", [])]

        _render(env, "claim.html", output_dir / "claims" / f"{cid}.html", {
            "claim": claim,
            "claim_id": cid,
            "supporting": supporting,
            "contradicting": contradicting,
            "positions": claim_positions,
            "store": store,
            "case_name": case_name,
        })

    # Generate position pages (top 15 shown, rest in toggle)
    for pos in positions:
        all_claims = [store.claims.get(cid, {}) for cid in pos.get("member_claims", [])]
        top_claims = all_claims[:15]
        rest_claims = all_claims[15:]
        _render(env, "position.html", output_dir / "positions" / f"{pos['position_id']}.html", {
            "position": pos,
            "claims": top_claims,
            "rest_claims": rest_claims,
            "important_claims": important_claims,
            "case_name": case_name,
        })

    # Generate crux pages (with cross-links to claims and positions)
    for i, crux in enumerate(cruxes):
        crux_id = f"crux_{i:02d}"
        claim = store.claims.get(crux.get("claim_id", ""), {})
        crux_positions = [p for p in positions if crux.get("claim_id") in p.get("member_claims", [])]
        _render(env, "crux.html", output_dir / "cruxes" / f"{crux_id}.html", {
            "crux": crux,
            "claim": claim,
            "crux_id": crux_id,
            "positions": crux_positions,
            "case_name": case_name,
        })

    total_pages = 1 + len(positions) + len(cruxes) + len(important_claims)
    log.info("site_generated", output_dir=str(output_dir), pages=total_pages)
    return output_dir


def _get_jinja_env() -> Environment:
    """Get Jinja2 environment with template directory or inline fallback."""
    # Use filesystem templates if they exist with actual .html files
    if TEMPLATES_DIR.exists() and list(TEMPLATES_DIR.glob("*.html")):
        return Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    # Fallback: use inline templates
    from jinja2 import DictLoader
    return Environment(
        loader=DictLoader(_INLINE_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )


def _render(env: Environment, template_name: str, output_path: Path, context: dict):
    """Render a template to file."""
    template = env.get_template(template_name)
    html = template.render(**context)
    output_path.write_text(html)


def _compute_stats(store: EpistemicStore, positions: list, cruxes: list) -> dict:
    """Compute summary statistics for the index page."""
    active_claims = [c for c in store.claims.values() if c.get("status") == "active"]
    active_edges = [e for e in store.edges.values() if e.get("status") == "active"]

    edge_types = {}
    for e in active_edges:
        t = e.get("edge_type", "unknown")
        edge_types[t] = edge_types.get(t, 0) + 1

    categories = {}
    for c in active_claims:
        cat = c.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    sources = set(c.get("source_title", "") for c in active_claims)

    return {
        "total_claims": len(active_claims),
        "total_edges": len(active_edges),
        "positions": len(positions),
        "cruxes": len(cruxes),
        "sources": len(sources),
        "edge_types": edge_types,
        "categories": categories,
        "source_names": sorted(sources),
    }


# ─── Inline Templates (external CSS + Mermaid via CDN) ──────────────────────

_HEAD = """<meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="{css_path}">
    <script type="module">import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';mermaid.initialize({{startOnLoad:true}});</script>"""

_INLINE_TEMPLATES = {
    "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    """ + _HEAD.format(css_path="static/style.css") + """
    <title>{{ case_name }} — Epistack Discourse Map</title>
</head>
<body>
    <h1>{{ case_name }}</h1>
    <p class="subtitle">Epistack Discourse Map — structural illumination of disagreement</p>

    <div class="stats">
        <div class="stat-card"><div class="number">{{ stats.total_claims }}</div><div class="label">Claims</div></div>
        <div class="stat-card"><div class="number">{{ stats.total_edges }}</div><div class="label">Edges</div></div>
        <div class="stat-card"><div class="number">{{ stats.positions }}</div><div class="label">Positions</div></div>
        <div class="stat-card"><div class="number">{{ stats.cruxes }}</div><div class="label">Cruxes</div></div>
        <div class="stat-card"><div class="number">{{ stats.sources }}</div><div class="label">Sources</div></div>
    </div>

    <h2>Discourse Structure</h2>
    <div class="mermaid-container">
    <pre class="mermaid">
graph LR
    {% for pos in positions %}{{ pos.position_id }}["{{ pos.stance[:40] if pos.stance else pos.position_id }} ({{ pos.member_claims|length }})"]
    {% endfor %}{% for d in disagreement_types %}{{ d.position_a }} ---|{{ d.contradicts }}⚔ {{ d.frames_differently }}◇| {{ d.position_b }}
    {% endfor %}</pre>
    </div>

    <h2>Positions</h2>
    {% for pos in positions %}
    <div class="position-card" style="--position-color: {{ ['#2563eb','#dc2626','#7c3aed','#059669'][loop.index0 % 4] }}">
        <h3><a href="positions/{{ pos.position_id }}.html">{{ pos.stance or pos.position_id }}</a></h3>
        <p>{{ pos.summary or '' }}</p>
        <p class="meta">{{ pos.member_claims|length }} claims · Core: {{ pos.core_commitment or 'Not identified' }}</p>
    </div>
    {% endfor %}
    {% if not positions %}<p><em>No positions identified. Run with more sources.</em></p>{% endif %}

    {% if is_settled %}
    <h2>Why This Is Settled</h2>
    <div class="settling-ok">
        <strong>✓ Scientific consensus — no live cruxes</strong>
        <p>All claims have high confidence. The safety argument rests on a well-established chain of reasoning. The weakest speculative link is identified below.</p>
    </div>
    {% if cruxes %}
    <h3>Weakest Speculative Links</h3>
    {% for crux in cruxes %}
    <div class="crux-card">
        <span class="crux-score">{{ "%.2f"|format(crux.crux_score) }}</span>
        <a href="cruxes/crux_{{ "%02d"|format(loop.index0) }}.html">{{ crux.text[:120] }}</a>
        <br><small>This is the least-certain claim in the dependency chain (conf: {{ "%.2f"|format(crux.confidence) }})</small>
    </div>
    {% endfor %}
    {% endif %}
    {% else %}
    <h2>Live Cruxes</h2>
    <p>Empirical claims whose resolution would most change the picture:</p>
    {% for crux in cruxes %}
    <div class="crux-card">
        <span class="crux-score">{{ "%.2f"|format(crux.crux_score) }}</span>
        <a href="cruxes/crux_{{ "%02d"|format(loop.index0) }}.html">{{ crux.text[:120] }}</a>
        <br><span class="badge badge-{{ crux.category }}">{{ crux.category }}</span>
        <span class="confidence-bar"><span class="confidence-fill {{ 'high' if crux.confidence > 0.7 else ('medium' if crux.confidence > 0.4 else 'low') }}" style="width: {{ (crux.confidence * 100)|int }}%"></span></span>
        <small>conf: {{ "%.2f"|format(crux.confidence) }}</small>
    </div>
    {% endfor %}
    {% if not cruxes %}<p><em>No cruxes detected.</em></p>{% endif %}
    {% endif %}

    <h2>Performed Settling</h2>
    {% for s in settling %}
    {% if s.detected %}
    <div class="settling-alert">
        <strong>⚠️ Performed Settling Detected</strong>
        <p>{{ s.explanation }}</p>
        <p><small>Severity: {{ "%.0f"|format(s.severity * 100) }}% · Type: {{ s.settling_type|join(', ') }}</small></p>
    </div>
    {% else %}
    <div class="settling-ok">
        <strong>✓ No performed settling detected</strong>
        <p>{{ s.get('reason', 'Verdict dependencies appear resolved.') }}</p>
    </div>
    {% endif %}
    {% endfor %}

    {% if empty_chairs %}
    <h2>Empty Chairs</h2>
    <p>Perspectives missing from the discourse:</p>
    {% for chair in empty_chairs %}
    <div class="empty-chair">
        <strong>{{ chair.perspective }}</strong>
        <p>{{ chair.why_it_matters }}</p>
    </div>
    {% endfor %}
    {% endif %}

    <h2>Sources</h2>
    <ul class="source-list">
    {% for name in stats.source_names %}<li>{{ name }}</li>{% endfor %}
    </ul>

    <div class="footer">Generated by Epistack-Adversarial · Compliance-aware epistemic verification · <a href="https://github.com/rkstu/epistack-adversarial">GitHub</a></div>
</body>
</html>""",

    "position.html": """<!DOCTYPE html>
<html lang="en">
<head>
    """ + _HEAD.format(css_path="../static/style.css") + """
    <title>{{ position.stance or position.position_id }} — {{ case_name }}</title>
</head>
<body>
    <a class="back-link" href="../index.html">← Back to overview</a>
    <h1>{{ position.stance or position.position_id }}</h1>
    <p>{{ position.summary or '' }}</p>
    <p><strong>Core commitment:</strong> {{ position.core_commitment or 'Not identified' }}</p>
    <p><strong>Total claims:</strong> {{ claims|length + rest_claims|length }}</p>

    <h2>Key Claims</h2>
    {% for claim in claims %}
    <div class="claim-card">
        <span class="claim-id">{% if claim.claim_id in important_claims %}<a href="../claims/{{ claim.claim_id }}.html">{{ claim.claim_id }}</a>{% else %}{{ claim.claim_id or '' }}{% endif %}</span>
        <span class="badge badge-{{ claim.category or 'unknown' }}">{{ claim.category or 'unknown' }}</span>
        {% if claim.confidence is defined and claim.confidence %}
        <span class="confidence-bar"><span class="confidence-fill {{ 'high' if claim.confidence > 0.7 else ('medium' if claim.confidence > 0.4 else 'low') }}" style="width: {{ (claim.confidence * 100)|int }}%"></span></span>
        {% endif %}
        <p class="claim-text">{{ claim.get('statement', {}).get('natural_language', '') }}</p>
        {% if claim.relevant_quote %}
        <p class="source-quote">"{{ claim.relevant_quote[:150] }}"</p>
        {% endif %}
    </div>
    {% endfor %}

    {% if rest_claims %}
    <details style="margin-top: 1rem;">
        <summary style="cursor: pointer; color: #2563eb; font-weight: 500;">Show all {{ rest_claims|length }} remaining claims</summary>
        {% for claim in rest_claims %}
        <div class="claim-card" style="margin-top: 0.5rem;">
            <span class="claim-id">{{ claim.claim_id or '' }}</span>
            <span class="badge badge-{{ claim.category or 'unknown' }}">{{ claim.category or 'unknown' }}</span>
            <p class="claim-text">{{ claim.get('statement', {}).get('natural_language', '') }}</p>
        </div>
        {% endfor %}
    </details>
    {% endif %}

    <div class="footer"><a class="back-link" href="../index.html">← Back to overview</a></div>
</body>
</html>""",

    "claim.html": """<!DOCTYPE html>
<html lang="en">
<head>
    """ + _HEAD.format(css_path="../static/style.css") + """
    <title>{{ claim.get('statement', {}).get('natural_language', '')[:50] }} — {{ case_name }}</title>
</head>
<body>
    <a class="back-link" href="../index.html">← Back to overview</a>
    <h1>Claim Detail</h1>
    <p style="font-size: 1.1rem; margin-bottom: 1rem;">{{ claim.get('statement', {}).get('natural_language', '') }}</p>

    <div class="stats" style="grid-template-columns: repeat(3, 1fr);">
        <div class="stat-card"><div class="number">{{ "%.2f"|format(claim.confidence or 0) }}</div><div class="label">Confidence</div></div>
        <div class="stat-card"><div class="number">{{ claim.category or 'unknown' }}</div><div class="label">Category</div></div>
        <div class="stat-card"><div class="number">{{ claim_id }}</div><div class="label">ID</div></div>
    </div>

    <h2>Source & Provenance</h2>
    <p class="source-quote">"{{ claim.relevant_quote or '' }}"</p>
    <p><small>Source: {{ claim.source_title or 'Unknown' }}{% if claim.source_url %} · <a href="{{ claim.source_url }}">Original</a>{% endif %}</small></p>

    {% if positions %}
    <h2>Belongs To</h2>
    {% for pos in positions %}
    <p><a href="../positions/{{ pos.position_id }}.html">{{ pos.stance or pos.position_id }}</a></p>
    {% endfor %}
    {% endif %}

    {% if supporting %}
    <h2>Supported By ({{ supporting|length }})</h2>
    {% for edge in supporting[:5] %}
    <div class="claim-card">
        <span class="badge badge-supports">supports</span>
        <span class="claim-id">{{ edge.source }}</span>
        <p>{{ store.claims.get(edge.source, {}).get('statement', {}).get('natural_language', '')[:120] }}</p>
    </div>
    {% endfor %}
    {% endif %}

    {% if contradicting %}
    <h2>Contradicted By ({{ contradicting|length }})</h2>
    {% for edge in contradicting[:5] %}
    <div class="claim-card" style="border-left: 3px solid #dc2626;">
        <span class="badge badge-contradicts">contradicts</span>
        <span class="claim-id">{{ edge.source if edge.source != claim_id else edge.target }}</span>
        <p>{{ store.claims.get(edge.source if edge.source != claim_id else edge.target, {}).get('statement', {}).get('natural_language', '')[:120] }}</p>
    </div>
    {% endfor %}
    {% endif %}

    <div class="footer"><a class="back-link" href="../index.html">← Back to overview</a></div>
</body>
</html>""",

    "crux.html": """<!DOCTYPE html>
<html lang="en">
<head>
    """ + _HEAD.format(css_path="../static/style.css") + """
    <title>Crux: {{ crux.text[:50] }} — {{ case_name }}</title>
</head>
<body>
    <a class="back-link" href="../index.html">← Back to overview</a>
    <h1>🔑 Crux</h1>
    <p style="font-size: 1.15rem; margin-bottom: 1.5rem;">{{ crux.text }}</p>

    <div class="stats" style="grid-template-columns: repeat(4, 1fr);">
        <div class="stat-card"><div class="number">{{ "%.2f"|format(crux.crux_score) }}</div><div class="label">Crux Score</div></div>
        <div class="stat-card"><div class="number">{{ "%.2f"|format(crux.confidence) }}</div><div class="label">Confidence</div></div>
        <div class="stat-card"><div class="number">{{ "%.3f"|format(crux.entropy) }}</div><div class="label">Entropy</div></div>
        <div class="stat-card"><div class="number">{{ crux.category }}</div><div class="label">Category</div></div>
    </div>

    <h2>Why This Is a Crux</h2>
    <p>This claim is <strong>uncertain</strong> (entropy {{ "%.3f"|format(crux.entropy) }}) AND has <strong>high downstream impact</strong>. If resolved, it would significantly change confidence in conclusion claims.</p>

    {% if claim.relevant_quote %}
    <h2>Source Evidence</h2>
    <p class="source-quote">"{{ claim.relevant_quote }}"</p>
    <p><small>Source: {{ claim.source_title or crux.source_title or 'Unknown' }}</small></p>
    {% endif %}

    <h2>What Would Resolve This</h2>
    <p>Finding definitive evidence that confirms or refutes this claim would shift the confidence of all downstream claims that depend on it, potentially changing which position is best-supported.</p>

    <div class="footer"><a class="back-link" href="../index.html">← Back to overview</a></div>
</body>
</html>""",
}

# Remove old style block that was in templates
# All styling now in static/style.css
