"""
Keyword Researcher — Streamlit UI
Run with: streamlit run app.py
"""
import os
import sys
import threading
import queue
import logging
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # no-op on Streamlit Cloud, works locally

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Keyword Researcher",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS (dark theme matching screenshot) ─────────────────────────────────
st.markdown("""
<style>
/* Sidebar status badges */
.badge-ok {
    background: #1a7a3a;
    color: #fff;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.85rem;
    display: inline-block;
    margin-bottom: 6px;
    width: 100%;
    text-align: center;
}
.badge-err {
    background: #7a1a1a;
    color: #fff;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 0.85rem;
    display: inline-block;
    margin-bottom: 6px;
    width: 100%;
    text-align: center;
}
/* Tab underline tweak */
[data-testid="stTabs"] button[aria-selected="true"] {
    border-bottom: 2px solid #e05252;
    color: #e05252;
}
/* Output table */
.kw-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.kw-table th { background: #1e3a5f; color: #fff; padding: 8px 12px; text-align: left; }
.kw-table td { padding: 6px 12px; border-bottom: 1px solid #333; }
.kw-table tr:nth-child(even) td { background: #1a1a2e; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ─────────────────────────────────────────────────────────────────────
def _get_secret(key: str) -> str | None:
    """Read from st.secrets first, then env vars (works on Cloud and locally)."""
    try:
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key)


def _check_env() -> dict[str, bool]:
    checks = {
        "Anthropic API key": bool(_get_secret("ANTHROPIC_API_KEY")),
        "Google Ads developer token": bool(_get_secret("GOOGLE_ADS_DEVELOPER_TOKEN")),
        "Google Ads client ID": bool(_get_secret("GOOGLE_ADS_CLIENT_ID")),
        "Google Ads client secret": bool(_get_secret("GOOGLE_ADS_CLIENT_SECRET")),
        "Google Ads refresh token": bool(_get_secret("GOOGLE_ADS_REFRESH_TOKEN")),
        "Google Ads login customer ID": bool(_get_secret("GOOGLE_ADS_LOGIN_CUSTOMER_ID")),
        "Google Ads customer ID": bool(_get_secret("GOOGLE_ADS_CUSTOMER_ID")),
    }
    return checks


def _validate_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _domain(url: str) -> str:
    return urlparse(url).netloc


# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Keyword Researcher")
    st.caption("Google Ads keyword research automation")
    st.divider()

    st.markdown("**Config status**")
    env = _check_env()
    all_ok = all(env.values())

    # Group into two badges: Anthropic + Google Ads
    anthropic_ok = env["Anthropic API key"]
    google_ok = all(v for k, v in env.items() if k != "Anthropic API key")

    if anthropic_ok:
        st.markdown('<div class="badge-ok">✓ Anthropic API key ready</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="badge-err">✗ Anthropic API key missing</div>', unsafe_allow_html=True)

    if google_ok:
        st.markdown('<div class="badge-ok">✓ Google Ads API ready</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="badge-err">✗ Google Ads API incomplete</div>', unsafe_allow_html=True)

    if not all_ok:
        with st.expander("Missing variables"):
            for k, ok in env.items():
                if not ok:
                    st.markdown(f"- `{k.upper().replace(' ', '_')}`")

    st.divider()

    # Last run stats from session state
    if "last_run" in st.session_state:
        lr = st.session_state["last_run"]
        st.markdown("**Last generated**")
        st.markdown(f"**URL:** {lr.get('url', '—')}")
        st.markdown(f"**Mode:** {lr.get('mode', '—')}")
        st.markdown(f"**Candidate kws:** {lr.get('candidate_kws', 0)}")
        st.markdown(f"**After filter:** {lr.get('filtered_kws', 0)}")
        if lr.get("output_path"):
            st.markdown(f"**Output:** `{os.path.basename(lr['output_path'])}`")


# ── Main content ─────────────────────────────────────────────────────────────────
st.title("Generate Keywords")
st.markdown("Enter a URL to research keywords. The tool will extract search queries, fetch real volumes from Google Ads, and export an Excel file.")

tab1, tab2 = st.tabs(["1 — Single URL", "2 — Full Site Crawl"])


# ────────────────────────────────────────────────────────────────────────────────
# TAB 1: Single URL
# ────────────────────────────────────────────────────────────────────────────────
with tab1:
    col1, col2 = st.columns([3, 1])

    with col1:
        url_input = st.text_input(
            "Page URL",
            placeholder="https://example.com/collections/headphones",
            key="single_url",
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_single = st.button("Run", key="run_single", type="primary", use_container_width=True)

    if run_single:
        if not url_input:
            st.error("Please enter a URL.")
        elif not _validate_url(url_input):
            st.error("Invalid URL. Must start with http:// or https://")
        elif not all_ok:
            st.error("Please configure all required API keys in your .env file before running.")
        else:
            st.divider()
            log_box = st.empty()
            progress = st.progress(0, text="Starting...")
            result_area = st.empty()

            logs: list[str] = []

            def _log(msg: str):
                ts = datetime.now().strftime("%H:%M:%S")
                logs.append(f"`{ts}` {msg}")
                log_box.markdown("\n\n".join(logs[-10:]))

            try:
                from pipeline.scraper import scrape_keywords
                from pipeline.keyword_planner import get_search_volumes
                from pipeline.excel_writer import write_single_page

                _log("Extracting keywords from page...")
                progress.progress(20, text="Extracting keywords...")
                keywords = scrape_keywords(url_input)

                if not keywords:
                    st.error("No keywords could be extracted from the page.")
                    st.stop()

                _log(f"Extracted **{len(keywords)}** candidate keywords.")
                progress.progress(50, text="Fetching search volumes...")

                _log("Fetching search volumes from Google Ads...")
                kv = get_search_volumes(keywords)
                _log(f"**{len(kv)}** keywords passed the volume filter.")
                progress.progress(85, text="Writing Excel...")

                _log("Writing Excel output...")
                output_path = write_single_page(url_input, kv)
                progress.progress(100, text="Done!")

                st.session_state["last_run"] = {
                    "url": _domain(url_input),
                    "mode": "single",
                    "candidate_kws": len(keywords),
                    "filtered_kws": len(kv),
                    "output_path": output_path,
                }

                st.success(f"Done! File saved to `{output_path}`")

                # Offer download
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="Download Excel",
                        data=f,
                        file_name=os.path.basename(output_path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                # Preview top 20 keywords
                if kv:
                    st.markdown("### Preview (top 20 by volume)")
                    sorted_kws = sorted(kv.items(), key=lambda x: -x[1]["volume"])[:20]
                    rows = "".join(
                        f"<tr><td>{kw}</td><td>{data['volume']:,}</td><td>{data['competition']}</td></tr>"
                        for kw, data in sorted_kws
                    )
                    st.markdown(
                        f'<table class="kw-table"><thead><tr><th>Keyword</th><th>Volume</th><th>Competition</th></tr></thead><tbody>{rows}</tbody></table>',
                        unsafe_allow_html=True,
                    )

            except Exception as exc:
                st.error(f"Error: {exc}")
                raise


# ────────────────────────────────────────────────────────────────────────────────
# TAB 2: Full Site Crawl
# ────────────────────────────────────────────────────────────────────────────────
with tab2:
    col1, col2 = st.columns([3, 1])

    with col1:
        site_input = st.text_input(
            "Site URL",
            placeholder="https://example.com",
            key="site_url",
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        crawl_btn = st.button("Crawl Site", key="crawl_btn", use_container_width=True)

    # Step A: crawl and show discovered categories
    if crawl_btn:
        if not site_input:
            st.error("Please enter a site URL.")
        elif not _validate_url(site_input):
            st.error("Invalid URL.")
        elif not all_ok:
            st.error("Please configure all required API keys in your .env file before running.")
        else:
            with st.spinner("Crawling site for category pages..."):
                try:
                    from pipeline.site_crawler import crawl
                    cats = crawl(site_input)
                    st.session_state["discovered_cats"] = cats
                    st.session_state["site_url_for_run"] = site_input
                except Exception as exc:
                    st.error(f"Crawl failed: {exc}")

    # Show discovered categories + confirm button
    if "discovered_cats" in st.session_state:
        cats = st.session_state["discovered_cats"]
        site_url_for_run = st.session_state.get("site_url_for_run", "")

        if not cats:
            st.warning("No category pages found on this site.")
        else:
            st.success(f"Found **{len(cats)}** category pages.")
            with st.expander("View discovered categories", expanded=True):
                for i, u in enumerate(cats, 1):
                    st.markdown(f"{i}. {u}")

            run_site = st.button(
                f"Research keywords for all {len(cats)} pages",
                key="run_site",
                type="primary",
            )

            if run_site:
                st.divider()
                log_box2 = st.empty()
                progress2 = st.progress(0, text="Starting...")
                logs2: list[str] = []

                def _log2(msg: str):
                    ts = datetime.now().strftime("%H:%M:%S")
                    logs2.append(f"`{ts}` {msg}")
                    log_box2.markdown("\n\n".join(logs2[-12:]))

                try:
                    from pipeline.scraper import scrape_keywords
                    from pipeline.keyword_planner import get_search_volumes
                    from pipeline.categorizer import categorize_keywords
                    from pipeline.excel_writer import write_multi_category

                    all_keywords: list[str] = []

                    _log2(f"Scraping {len(cats)} pages...")
                    for idx, url in enumerate(cats):
                        progress2.progress(
                            int(10 + 40 * idx / len(cats)),
                            text=f"Scraping page {idx+1}/{len(cats)}...",
                        )
                        kws = scrape_keywords(url)
                        all_keywords.extend(kws)
                        _log2(f"Page {idx+1}/{len(cats)}: {len(kws)} kws — `{url}`")

                    unique_kws = list(dict.fromkeys(
                        kw.lower().strip() for kw in all_keywords if kw.strip()
                    ))
                    _log2(f"**{len(unique_kws)}** unique candidate keywords total.")

                    progress2.progress(55, text="Fetching search volumes...")
                    _log2("Fetching volumes from Google Ads...")
                    kv = get_search_volumes(unique_kws)
                    _log2(f"**{len(kv)}** keywords passed the volume filter.")

                    progress2.progress(75, text="Categorizing keywords...")
                    _log2("Categorizing keywords with Claude...")
                    categorized = categorize_keywords(kv, cats)
                    _log2(f"Keywords assigned to **{len(categorized)}** categories.")

                    progress2.progress(90, text="Writing Excel...")
                    _log2("Writing Excel output...")
                    output_path = write_multi_category(site_url_for_run, categorized)
                    progress2.progress(100, text="Done!")

                    st.session_state["last_run"] = {
                        "url": _domain(site_url_for_run),
                        "mode": "site",
                        "candidate_kws": len(unique_kws),
                        "filtered_kws": len(kv),
                        "output_path": output_path,
                    }
                    # Clear crawl state
                    del st.session_state["discovered_cats"]

                    st.success(f"Done! File saved to `{output_path}`")

                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="Download Excel",
                            data=f,
                            file_name=os.path.basename(output_path),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )

                    # Summary per category
                    st.markdown("### Summary by category")
                    rows = "".join(
                        f"<tr><td>{cat}</td><td>{len(kws)}</td></tr>"
                        for cat, kws in categorized.items()
                    )
                    st.markdown(
                        f'<table class="kw-table"><thead><tr><th>Category</th><th>Keywords</th></tr></thead><tbody>{rows}</tbody></table>',
                        unsafe_allow_html=True,
                    )

                except Exception as exc:
                    st.error(f"Error: {exc}")
                    raise
