import os
import subprocess
from urllib.parse import quote

import requests
import streamlit as st
from bs4 import BeautifulSoup

# --- Try loading the live search plugin ---
try:
    from st_keyup import st_keyup

    HAS_KEYUP = True
except ImportError:
    HAS_KEYUP = False

# --- Configuration & Metadata ---
VERSION = "0.0.5 (Live Search Edition)"
BASE_URL = "https://kisskh.buzz/"
AJAX_URL = BASE_URL + "wp-admin/admin-ajax.php"
BLOGGER_BLOG_ID = "1422331367239821646"
BLOGGER_FEED_URL = f"https://www.blogger.com/feeds/{BLOGGER_BLOG_ID}/posts/default"

# --- State Management Initialization ---
if "selected_drama" not in st.session_state:
    st.session_state.selected_drama = None
if "ep_idx" not in st.session_state:
    st.session_state.ep_idx = 0
if "last_query" not in st.session_state:
    st.session_state.last_query = ""


@st.cache_data(show_spinner=False)
def get_search_results(query):
    """Search for dramas via AJAX and extract thumbnails."""
    if not query:
        return []
    payload = {
        "action": "fetch_live_movies",
        "keyword": query,
        "filter": "all",
        "page": "1",
        "is_popular": "0",
    }
    try:
        res = requests.post(AJAX_URL, data=payload, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        results = []
        for card in soup.select("a.movie-card"):
            title = (
                card.select_one(".movie-title").get_text(strip=True)
                if card.select_one(".movie-title")
                else "Unknown"
            )
            link = card.get("href", "")

            ep_tag = card.select_one(".episode")
            ep = ep_tag.get_text(strip=True) if ep_tag else "Movie"

            img_tag = card.select_one("img")
            img_src = None
            if img_tag:
                img_src = img_tag.get("data-src") or img_tag.get("src")
            if not img_src:
                img_src = "https://via.placeholder.com/300x400.png?text=No+Image"

            results.append({"title": title, "link": link, "ep": ep, "img": img_src})
        return results
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def fetch_links(drama_title):
    """Extracts Video and Subtitle links from Blogger Feed."""
    feed_url = f"{BLOGGER_FEED_URL}?q={quote(drama_title)}&alt=json&max-results=1"
    try:
        data = requests.get(feed_url, timeout=10).json()
        if "entry" not in data["feed"]:
            return []
        content = data["feed"]["entry"][0]["content"]["$t"]
        eps = []
        for i, part in enumerate(content.split(";"), 1):
            if "|" in part:
                fields = part.split("|")
                v_url = fields[0].strip()

                s_url = ""
                if len(fields) > 2:
                    subs = fields[2].strip().split(",")
                    s_url = subs[0] if subs else ""
                    if not s_url.startswith("http"):
                        s_url = ""

                if v_url.startswith("http"):
                    eps.append({"label": f"Episode {i}", "url": v_url, "sub": s_url})
        return eps
    except Exception:
        return []


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_subtitle_content(url):
    """Downloads the raw subtitle text so Streamlit can read it natively."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        content = r.text.strip()
        if content.startswith("WEBVTT") or "-->" in content:
            return content
        return None
    except Exception:
        return None


def play_video(url, sub_url, platform):
    """Triggers external players for local OS usage."""
    if not url:
        return
    try:
        if platform == "1":  # Android (MPV)
            cmd = [
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                url,
                "-n",
                "io.mpv/.MPVActivity",
            ]
            if sub_url:
                cmd.extend(["--es", "subs", sub_url])
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif platform == "2":  # iOS (VLC)
            os.system(f"open vlc://{url}")
        elif platform == "3":  # Linux (MPV)
            cmd = ["mpv", url]
            if sub_url:
                cmd.append(f"--sub-file={sub_url}")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        st.error(f"Failed to launch player: {e}")


# --- Streamlit UI Main App ---
def main():
    st.set_page_config(page_title="Deha Drama Streamer", layout="wide", page_icon="🎬")

    st.title("🎬 Deha Drama Streamer")

    st.sidebar.header("⚙️ Configuration")
    platform_map = {
        "Browser (Web Player)": "0",
        "Android (MPV)": "1",
        "iOS (VLC)": "2",
        "Linux (MPV)": "3",
        "URL Only": "4",
    }
    selected_platform_name = st.sidebar.selectbox(
        "Select Environment:", list(platform_map.keys())
    )
    platform = platform_map[selected_platform_name]

    # --- LIVE SEARCH BAR ---
    if HAS_KEYUP:
        # debounce=500 means it waits half a second after you stop typing to search
        query = st_keyup(
            "🔍 Live Search Drama:",
            placeholder="Start typing a drama name...",
            debounce=500,
        )
    else:
        st.warning(
            "⚠️ Live search is disabled. Run `pip install streamlit-keyup` in your terminal to enable it."
        )
        query = st.text_input(
            "🔍 Search Drama (Press Enter):", placeholder="Type a drama name here..."
        )

    st.divider()

    # Reset view if user types a new query
    if query != st.session_state.last_query:
        st.session_state.selected_drama = None
        st.session_state.ep_idx = 0
        st.session_state.last_query = query

    # View 1: Display Grid of Thumbnails
    if query and st.session_state.selected_drama is None:
        with st.spinner("Searching..."):
            results = get_search_results(query)

        if not results:
            st.info("No results found. Try a different search term.")
            return

        cols = st.columns(4)
        for idx, r in enumerate(results):
            col = cols[idx % 4]
            with col:
                st.image(r["img"], use_container_width=True)
                st.markdown(f"**{r['title']}**\n\n`{r['ep']}`")

                if st.button(f"🍿 Watch", key=f"btn_{idx}", use_container_width=True):
                    st.session_state.selected_drama = r
                    st.session_state.ep_idx = 0
                    st.rerun()

    # View 2: Video Player and Episode Navigation
    elif st.session_state.selected_drama is not None:
        selected_drama = st.session_state.selected_drama

        if st.button("⬅️ Back to Search Results", use_container_width=True):
            st.session_state.selected_drama = None
            st.rerun()

        with st.spinner("Fetching episodes..."):
            episodes = fetch_links(selected_drama["title"])

        if not episodes:
            st.error("No streamable episodes found for this drama.")
            return

        ep_labels = [e["label"] for e in episodes]

        st.subheader(f"Watching: {selected_drama['title']}")
        col1, col2, col3 = st.columns([1, 2, 1])

        with col1:
            if st.button(
                "⬅️ Previous Episode",
                disabled=(st.session_state.ep_idx == 0),
                use_container_width=True,
            ):
                st.session_state.ep_idx -= 1
                st.rerun()
        with col2:
            selected_ep_label = st.selectbox(
                "Select Episode:",
                options=ep_labels,
                index=st.session_state.ep_idx,
                label_visibility="collapsed",
            )
            new_idx = ep_labels.index(selected_ep_label)
            if new_idx != st.session_state.ep_idx:
                st.session_state.ep_idx = new_idx
                st.rerun()
        with col3:
            if st.button(
                "Next Episode ➡️",
                disabled=(st.session_state.ep_idx == len(episodes) - 1),
                use_container_width=True,
            ):
                st.session_state.ep_idx += 1
                st.rerun()

        # Load Current Episode Data
        current_ep = episodes[st.session_state.ep_idx]
        has_sub_url = bool(current_ep["sub"])

        if platform == "0":
            # NATIVE WEB PLAYER
            if has_sub_url:
                with st.spinner("Downloading subtitles..."):
                    raw_sub_text = fetch_subtitle_content(current_ep["sub"])

                if raw_sub_text:
                    st.caption(f"{current_ep['label']} — ✅ Subtitles Loaded")
                    try:
                        st.video(current_ep["url"], subtitles={"English": raw_sub_text})
                    except Exception:
                        st.warning(
                            "⚠️ Streamlit rejected the subtitle format. Playing video without subtitles."
                        )
                        st.video(current_ep["url"])
                else:
                    st.caption(
                        f"{current_ep['label']} — ❌ Failed to process subtitle format."
                    )
                    st.video(current_ep["url"])
            else:
                st.caption(f"{current_ep['label']} — ❌ No Subtitles Available")
                st.video(current_ep["url"])

        elif platform in ["1", "2", "3"]:
            st.caption(f"{current_ep['label']} — Subtitle Link Attached")
            player_name = (
                selected_platform_name.split()[1].replace("(", "").replace(")", "")
            )
            if st.button(
                f"🎬 Launch {player_name} Native Player", use_container_width=True
            ):
                play_video(current_ep["url"], current_ep["sub"], platform)
                st.success(f"Sent to {player_name}!")

        elif platform == "4":
            st.code(
                f"Video URL: {current_ep['url']}\nSubtitle URL: {current_ep['sub'] if current_ep['sub'] else 'None'}",
                language="http",
            )


if __name__ == "__main__":
    main()
