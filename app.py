"""
Keyword Researcher — Streamlit UI
Run with: streamlit run app.py
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

# ── Inject st.secrets into os.environ BEFORE any pipeline imports ───────────────
# config/settings.py reads os.environ at import time, so credentials must be
# present before any pipeline module is first imported.
_SECRET_KEYS = [
    "ANTHROPIC_API_KEY",
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "GOOGLE_ADS_CUSTOMER_ID",
    "GOOGLE_ADS_USE_PROTO_PLUS",
]

try:
    for _key in _SECRET_KEYS:
        _val = st.secrets.get(_key)
        if _val and not os.environ.get(_key):
            os.environ[_key] = str(_val)
except Exception:
    pass  # No secrets file — rely on .env loaded below

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Page config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Keyword Researcher",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.badge-ok  { background:#1a7a3a; color:#fff; padding:6px 14px; border-radius:6px;
             font-size:.85rem; display:inline-block; margin-bottom:6px; width:100%; text-align:center; }
.badge-err { background:#7a1a1a; color:#fff; padding:6px 14px; border-radius:6px;
             font-size:.85rem; display:inline-block; margin-bottom:6px; width:100%; text-align:center; }
.kw-table  { width:100%; border-collapse:collapse; font-size:.9rem; }
.kw-table th { background:#1e3a5f; color:#fff; padding:8px 12px; text-align:left; }
.kw-table td { padding:6px 12px; border-bottom:1px solid #333; }
.kw-table tr:nth-child(even) td { background:#1a1a2e; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────────
def _check_env() -> dict[str, bool]:
    keys = {
        "Anthropic API key":          "ANTHROPIC_API_KEY",
        "Google developer token":     "GOOGLE_ADS_DEVELOPER_TOKEN",
        "Google client ID":           "GOOGLE_ADS_CLIENT_ID",
        "Google client secret":       "GOOGLE_ADS_CLIENT_SECRET",
        "Google refresh token":       "GOOGLE_ADS_REFRESH_TOKEN",
        "Google login customer ID":   "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        "Google customer ID":         "GOOGLE_ADS_CUSTOMER_ID",
    }
    return {label: bool(os.environ.get(env_key)) for label, env_key in keys.items()}


def _validate_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _domain(url: str) -> str:
    return urlparse(url).netloc


def _output_path(url: str) -> str:
    domain = _domain(url).replace(".", "_").replace("-", "_")
    date   = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path   = f"data/output/{domain}_{date}.xlsx"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def _kw_table_html(rows: list[tuple[str, int]]) -> str:
    body = "".join(
        f"<tr><td>{kw}</td><td>{vol:,}</td></tr>"
        for kw, vol in rows
    )
    return (
        '<table class="kw-table"><thead>'
        "<tr><th>Keyword</th><th>Avg Monthly Volume</th></tr>"
        f"</thead><tbody>{body}</tbody></table>"
    )


# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Keyword Researcher")
    st.caption("Google Ads keyword research automation")
    st.divider()

    st.markdown("**Config status**")
    env = _check_env()
    anthropic_ok = env["Anthropic API key"]
    google_ok    = all(v for k, v in env.items() if k != "Anthropic API key")
    all_ok       = anthropic_ok and google_ok

    if anthropic_ok:
        st.markdown('<div class="badge-ok">✓ Anthropic API ready</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="badge-err">✗ Anthropic API key missing</div>', unsafe_allow_html=True)

    if google_ok:
        st.markdown('<div class="badge-ok">✓ Google Ads API ready</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="badge-err">✗ Google Ads API incomplete</div>', unsafe_allow_html=True)

    if not all_ok:
        with st.expander("Missing variables"):
            for label, ok in env.items():
                if not ok:
                    st.markdown(f"- {label}")

    st.divider()
    if "last_run" in st.session_state:
        lr = st.session_state["last_run"]
        st.markdown("**Last run**")
        st.markdown(f"**Site:** {lr.get('domain', '—')}")
        st.markdown(f"**Mode:** {lr.get('mode', '—')}")
        st.markdown(f"**Candidates:** {lr.get('candidates', 0)}")
        st.markdown(f"**After filter:** {lr.get('filtered', 0)}")


# ── Main ─────────────────────────────────────────────────────────────────────────
st.title("Keyword Researcher")
st.markdown(
    "Extract search keywords from ecommerce pages, fetch real Google Ads volumes, "
    "and download a ready-to-use Excel workbook."
)

tab1, tab2, tab3 = st.tabs(["Single URL", "Full Site Crawl", "CSV Upload"])


# Common geo/language options shown in the UI
_GEO_OPTIONS = {
    "Slovenia (SI)": "2705",
    "Croatia (HR)": "2191",
    "Austria (AT)": "2040",
    "Germany (DE)": "2276",
    "United Kingdom (UK)": "2826",
    "United States (US)": "2840",
    "Global": "2840",  # broadest single-country proxy
}
_LANG_OPTIONS = {
    "Slovenian": "1023",
    "Croatian": "1038",
    "German": "1001",
    "English": "1000",
}


# ── TAB 1: Single URL ─────────────────────────────────────────────────────────────
with tab1:
    col_url, col_btn = st.columns([4, 1])
    with col_url:
        single_url = st.text_input(
            "Page URL",
            placeholder="https://example.com/collections/headphones",
            key="single_url_input",
            label_visibility="collapsed",
        )
    with col_btn:
        run_single = st.button("Run", key="run_single_btn", type="primary", use_container_width=True)

    col_geo, col_lang = st.columns(2)
    with col_geo:
        single_geo_label = st.selectbox("Market (geo)", list(_GEO_OPTIONS.keys()), key="single_geo")
    with col_lang:
        single_lang_label = st.selectbox("Language", list(_LANG_OPTIONS.keys()), key="single_lang")

    if run_single:
        if not single_url:
            st.error("Enter a URL.")
        elif not _validate_url(single_url):
            st.error("Invalid URL — must start with http:// or https://")
        elif not all_ok:
            st.error("Configure all API credentials before running.")
        else:
            from pipeline.scraper import extract_keywords
            from pipeline.keyword_planner import get_search_volumes
            from pipeline.excel_writer import write_excel
            from config.settings import MIN_SEARCH_VOLUME

            log   = st.empty()
            prog  = st.progress(0)
            msgs: list[str] = []

            def _log(msg: str):
                msgs.append(msg)
                log.markdown("  \n".join(msgs[-8:]))

            try:
                _log(f"Extracting keywords from `{single_url}` …")
                prog.progress(15)
                candidates = extract_keywords(single_url)
                _log(f"{len(candidates)} candidate keywords extracted.")

                if not candidates:
                    st.error("No keywords extracted — check the URL and try again.")
                    st.stop()

                _log("Fetching search volumes from Google Ads …")
                prog.progress(45)
                geo_id  = _GEO_OPTIONS[single_geo_label]
                lang_id = _LANG_OPTIONS[single_lang_label]
                try:
                    volumes = get_search_volumes(candidates, geo_target_id=geo_id, language_id=lang_id)
                except Exception as gads_exc:
                    st.error(f"Google Ads API error: {gads_exc}")
                    st.info(
                        "Common causes:\n"
                        "- Developer token not yet approved for Basic access (Test tokens return 0)\n"
                        "- Wrong `GOOGLE_ADS_CUSTOMER_ID` or `LOGIN_CUSTOMER_ID`\n"
                        "- Mismatched language/geo settings for the page's market"
                    )
                    st.stop()

                kw_list = sorted(
                    [{"kw": kw, "volume": volumes.get(kw, 0)}
                     for kw in candidates if volumes.get(kw, 0) > MIN_SEARCH_VOLUME],
                    key=lambda x: x["volume"],
                    reverse=True,
                )
                _log(f"{len(kw_list)} keywords with volume > {MIN_SEARCH_VOLUME}.")

                if not kw_list:
                    st.warning(
                        "No keywords with sufficient search volume (all returned 0).  \n"
                        "If the page is in English, try setting language to English "
                        "(ID `1000`) and geo to a larger market (e.g. US = `2840`, UK = `2826`).  \n"
                        "Also check that your developer token has Basic access in Google Ads → Tools → API Center."
                    )
                    st.stop()

                _log("Writing Excel …")
                prog.progress(85)
                out = _output_path(single_url)
                write_excel([{"url": single_url, "keywords": kw_list}], out)
                prog.progress(100)

                st.session_state["last_run"] = {
                    "domain": _domain(single_url),
                    "mode": "single",
                    "candidates": len(candidates),
                    "filtered": len(kw_list),
                }

                st.success(f"Done — {len(kw_list)} keywords written to `{out}`")
                with open(out, "rb") as fh:
                    st.download_button(
                        "Download Excel",
                        fh,
                        file_name=Path(out).name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                st.markdown("### Preview (top 20)")
                st.markdown(
                    _kw_table_html([(r["kw"], r["volume"]) for r in kw_list[:20]]),
                    unsafe_allow_html=True,
                )

            except Exception as exc:
                st.error(f"Error: {exc}")
                raise


# ── TAB 2: Full Site Crawl ────────────────────────────────────────────────────────
with tab2:
    col_site, col_crawl = st.columns([4, 1])
    with col_site:
        site_url = st.text_input(
            "Homepage URL",
            placeholder="https://example.com",
            key="site_url_input",
            label_visibility="collapsed",
        )
    with col_crawl:
        crawl_btn = st.button("Crawl", key="crawl_btn", use_container_width=True)

    col_geo2, col_lang2 = st.columns(2)
    with col_geo2:
        site_geo_label = st.selectbox("Market (geo)", list(_GEO_OPTIONS.keys()), key="site_geo")
    with col_lang2:
        site_lang_label = st.selectbox("Language", list(_LANG_OPTIONS.keys()), key="site_lang")

    if crawl_btn:
        if not site_url:
            st.error("Enter a site URL.")
        elif not _validate_url(site_url):
            st.error("Invalid URL.")
        elif not all_ok:
            st.error("Configure all API credentials before running.")
        else:
            from pipeline.site_crawler import crawl, _is_category_url

            with st.spinner("Crawling site for category pages …"):
                try:
                    all_urls = crawl(site_url)
                    # Apply the same filtering as main.py run_site
                    _SKIP_SLUGS = {
                        "shop", "store", "trgovina", "boutique", "tienda", "negozio", "winkel",
                        "sale", "deals", "offers", "akcija", "aktualne-ugodnosti", "ugodnosti",
                        "promotions", "rabais", "offerte", "angebote",
                        "gift-cards", "gift-vouchers", "darilni-boni", "boni", "vouchers",
                        "uncategorized", "neuvrsceni", "neuvrsteno", "brez-kategorije", "page",
                    }
                    seen: set[str] = set()
                    cat_urls: list[str] = []
                    for u in all_urls:
                        if not _is_category_url(u):
                            continue
                        segments = [s for s in u.rstrip("/").split("/") if s]
                        slug = segments[-1]
                        if slug.isdigit() or slug in _SKIP_SLUGS or "page" in segments:
                            continue
                        if slug not in seen:
                            seen.add(slug)
                            cat_urls.append(u)

                    st.session_state["crawled_urls"]   = cat_urls
                    st.session_state["crawled_site"]   = site_url
                except Exception as exc:
                    st.error(f"Crawl failed: {exc}")

    # Show discovered categories and confirm
    if "crawled_urls" in st.session_state:
        cat_urls   = st.session_state["crawled_urls"]
        crawled_site = st.session_state["crawled_site"]

        if not cat_urls:
            st.warning("No category pages found.")
        else:
            st.success(f"Found **{len(cat_urls)}** category pages.")
            with st.expander("Discovered categories", expanded=True):
                for i, u in enumerate(cat_urls, 1):
                    slug = u.rstrip("/").split("/")[-1]
                    st.markdown(f"{i}. **{slug.replace('-', ' ').title()}** — `{u}`")

            run_site_btn = st.button(
                f"Research keywords for all {len(cat_urls)} pages",
                key="run_site_btn",
                type="primary",
            )

            if run_site_btn:
                if not all_ok:
                    st.error("Configure all API credentials before running.")
                else:
                    from pipeline.scraper import extract_keywords
                    from pipeline.keyword_planner import get_search_volumes
                    from pipeline.categorizer import assign_keywords_to_categories
                    from pipeline.excel_writer import write_excel
                    from config.settings import TOP_KEYWORDS_PER_URL, MIN_SEARCH_VOLUME

                    log2  = st.empty()
                    prog2 = st.progress(0)
                    msgs2: list[str] = []

                    def _log2(msg: str):
                        msgs2.append(msg)
                        log2.markdown("  \n".join(msgs2[-10:]))

                    try:
                        category_names = [
                            u.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title()
                            for u in cat_urls
                        ]

                        all_candidates: list[str] = []
                        for idx, url in enumerate(cat_urls):
                            prog2.progress(int(5 + 40 * idx / len(cat_urls)))
                            _log2(f"Scraping {idx+1}/{len(cat_urls)}: `{url}`")
                            kws = extract_keywords(url, top_n=TOP_KEYWORDS_PER_URL)
                            all_candidates.extend(kws)

                        all_candidates = list(dict.fromkeys(all_candidates))
                        _log2(f"{len(all_candidates)} unique candidates across all pages.")

                        prog2.progress(50)
                        _log2("Fetching search volumes …")
                        volumes = get_search_volumes(
                            all_candidates,
                            geo_target_id=_GEO_OPTIONS[site_geo_label],
                            language_id=_LANG_OPTIONS[site_lang_label],
                        )

                        kw_volumes = {
                            kw: volumes.get(kw, 0)
                            for kw in all_candidates
                            if volumes.get(kw, 0) > MIN_SEARCH_VOLUME
                        }
                        _log2(f"{len(kw_volumes)} keywords passed volume filter.")

                        prog2.progress(70)
                        _log2("Categorizing with Claude …")
                        categorized = assign_keywords_to_categories(kw_volumes, category_names)

                        prog2.progress(90)
                        _log2("Writing Excel …")
                        results = [
                            {"url": url, "category": cat, "keywords": categorized.get(cat, [])}
                            for url, cat in zip(cat_urls, category_names)
                            if categorized.get(cat)
                        ]
                        out = _output_path(crawled_site)
                        write_excel(results, out)
                        prog2.progress(100)

                        del st.session_state["crawled_urls"]
                        del st.session_state["crawled_site"]

                        st.session_state["last_run"] = {
                            "domain": _domain(crawled_site),
                            "mode": "site",
                            "candidates": len(all_candidates),
                            "filtered": len(kw_volumes),
                        }

                        st.success(f"Done — {len(results)} categories written to `{out}`")
                        with open(out, "rb") as fh:
                            st.download_button(
                                "Download Excel",
                                fh,
                                file_name=Path(out).name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )

                        st.markdown("### Summary by category")
                        rows_html = "".join(
                            f"<tr><td>{r['category']}</td><td>{len(r['keywords'])}</td></tr>"
                            for r in results
                        )
                        st.markdown(
                            '<table class="kw-table"><thead><tr><th>Category</th>'
                            f"<th>Keywords</th></tr></thead><tbody>{rows_html}</tbody></table>",
                            unsafe_allow_html=True,
                        )

                    except Exception as exc:
                        st.error(f"Error: {exc}")
                        raise


# ── TAB 3: CSV Upload ─────────────────────────────────────────────────────────────
with tab3:
    st.markdown(
        "Upload a CSV file with one product/category URL per line. "
        "One sheet per URL in the output."
    )
    uploaded = st.file_uploader("CSV file", type=["csv"], key="csv_upload")

    col_geo3, col_lang3 = st.columns(2)
    with col_geo3:
        csv_geo_label = st.selectbox("Market (geo)", list(_GEO_OPTIONS.keys()), key="csv_geo")
    with col_lang3:
        csv_lang_label = st.selectbox("Language", list(_LANG_OPTIONS.keys()), key="csv_lang")
    run_csv_btn = st.button("Run", key="run_csv_btn", type="primary", disabled=not uploaded)

    if run_csv_btn and uploaded:
        if not all_ok:
            st.error("Configure all API credentials before running.")
        else:
            from pipeline.url_loader import load_urls
            from pipeline.scraper import extract_keywords
            from pipeline.keyword_planner import get_search_volumes
            from pipeline.excel_writer import write_excel
            from config.settings import TOP_KEYWORDS_PER_URL, MIN_SEARCH_VOLUME

            # Write upload to a temp file so url_loader can parse it
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            log3  = st.empty()
            prog3 = st.progress(0)
            msgs3: list[str] = []

            def _log3(msg: str):
                msgs3.append(msg)
                log3.markdown("  \n".join(msgs3[-10:]))

            try:
                urls = load_urls(tmp_path)
                if not urls:
                    st.error("No URLs found in the CSV file.")
                    st.stop()

                _log3(f"Loaded **{len(urls)}** URLs.")

                # Scrape each URL, track keywords per URL
                url_kws: dict[str, list[str]] = {}
                all_candidates: list[str] = []

                for idx, url in enumerate(urls):
                    prog3.progress(int(5 + 40 * idx / len(urls)))
                    _log3(f"Scraping {idx+1}/{len(urls)}: `{url}`")
                    kws = extract_keywords(url, top_n=TOP_KEYWORDS_PER_URL)
                    url_kws[url] = kws
                    all_candidates.extend(kws)

                all_candidates = list(dict.fromkeys(all_candidates))
                _log3(f"{len(all_candidates)} unique candidates.")

                prog3.progress(50)
                _log3("Fetching search volumes …")
                volumes = get_search_volumes(
                    all_candidates,
                    geo_target_id=_GEO_OPTIONS[csv_geo_label],
                    language_id=_LANG_OPTIONS[csv_lang_label],
                )

                prog3.progress(85)
                _log3("Building output …")

                # One result entry per URL (no category — sheet name derived from URL)
                results = []
                skipped = 0
                for url in urls:
                    kw_list = sorted(
                        [{"kw": kw, "volume": volumes.get(kw, 0)}
                         for kw in url_kws.get(url, [])
                         if volumes.get(kw, 0) > MIN_SEARCH_VOLUME],
                        key=lambda x: x["volume"],
                        reverse=True,
                    )
                    if kw_list:
                        results.append({"url": url, "keywords": kw_list})
                    else:
                        skipped += 1

                _log3(f"{len(results)} URLs with results, {skipped} skipped.")

                if not results:
                    st.warning("No keywords with sufficient search volume.")
                    st.stop()

                first_url = urls[0]
                out = _output_path(first_url)
                write_excel(results, out)
                prog3.progress(100)

                st.session_state["last_run"] = {
                    "domain": _domain(first_url),
                    "mode": "csv",
                    "candidates": len(all_candidates),
                    "filtered": sum(len(r["keywords"]) for r in results),
                }

                st.success(f"Done — {len(results)} sheets written to `{out}`")
                with open(out, "rb") as fh:
                    st.download_button(
                        "Download Excel",
                        fh,
                        file_name=Path(out).name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                st.markdown("### Summary by page")
                rows_html = "".join(
                    f"<tr><td><code>{r['url']}</code></td><td>{len(r['keywords'])}</td></tr>"
                    for r in results
                )
                st.markdown(
                    '<table class="kw-table"><thead><tr><th>URL</th>'
                    f"<th>Keywords</th></tr></thead><tbody>{rows_html}</tbody></table>",
                    unsafe_allow_html=True,
                )

            except Exception as exc:
                st.error(f"Error: {exc}")
                raise
            finally:
                os.unlink(tmp_path)
