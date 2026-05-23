import os
import subprocess
from urllib.parse import quote

import requests
import streamlit as st
from bs4 import BeautifulSoup

# --- Configuration & Metadata ---
VERSION = "0.0.1 (Web Edition)"
BASE_URL = "https://kisskh.buzz/"
AJAX_URL = BASE_URL + "wp-admin/admin-ajax.php"
BLOGGER_BLOG_ID = "1422331367239821646"
BLOGGER_FEED_URL = f"https://www.blogger.com/feeds/{BLOGGER_BLOG_ID}/posts/default"


@st.cache_data(show_spinner=False)
def get_search_results(query):
    """Search for dramas via AJAX."""
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
            title = card.select_one(".movie-title").get_text(strip=True)
            link = card["href"]
            ep_tag = card.select_one(".episode")
            ep = ep_tag.get_text(strip=True) if ep_tag else "Movie"
            results.append({"title": title, "link": link, "display": f"{title} [{ep}]"})
        return results
    except Exception as e:
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
                if v_url.startswith("http"):
                    eps.append({"label": f"Episode {i}", "url": v_url, "sub": s_url})
        return eps
    except Exception as e:
        return []


def play_video(url, sub_url, platform):
    """Triggers external players with subtitle support (Requires Local Hosting)."""
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

    # Header
    st.title("🎬 Deha Drama Streamer")
    st.markdown(f"**Version:** {VERSION}")
    st.divider()

    # Sidebar for Platform Configuration
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

    st.sidebar.info(
        "⚠️ *Android, iOS, and Linux local options only work if this app is running locally on the device (e.g. localhost via Termux/Terminal).*"
    )

    # Search Bar
    query = st.text_input("🔍 Search Drama:", placeholder="Type a drama name here...")

    if query:
        with st.spinner("Searching..."):
            results = get_search_results(query)

        if not results:
            st.warning("No results found. Try a different search term.")
            return

        drama_options = {r["display"]: r for r in results}
        selected_display = st.selectbox(
            "📺 Select Title:", options=["-- Select --"] + list(drama_options.keys())
        )

        if selected_display != "-- Select --":
            selected_drama = drama_options[selected_display]

            # Reset episode index if a new drama is selected
            if (
                "last_drama" not in st.session_state
                or st.session_state.last_drama != selected_drama["title"]
            ):
                st.session_state.ep_idx = 0
                st.session_state.last_drama = selected_drama["title"]

            with st.spinner("Fetching episodes..."):
                episodes = fetch_links(selected_drama["title"])

            if not episodes:
                st.error("No streamable episodes found for this drama.")
                return

            st.divider()

            # Episode Navigation Controller
            ep_labels = [e["label"] for e in episodes]

            # Layout for Next/Prev Controls
            col1, col2, col3 = st.columns([1, 2, 1])

            with col1:
                if st.button("⬅️ Previous", disabled=(st.session_state.ep_idx == 0)):
                    st.session_state.ep_idx -= 1
                    st.rerun()

            with col2:
                # Synchronize selectbox with session state index
                selected_ep_label = st.selectbox(
                    "▶️ Select Episode:",
                    options=ep_labels,
                    index=st.session_state.ep_idx,
                    label_visibility="collapsed",
                )
                # Update session state if user manually changes the dropdown
                new_idx = ep_labels.index(selected_ep_label)
                if new_idx != st.session_state.ep_idx:
                    st.session_state.ep_idx = new_idx
                    st.rerun()

            with col3:
                if st.button(
                    "Next ➡️", disabled=(st.session_state.ep_idx == len(episodes) - 1)
                ):
                    st.session_state.ep_idx += 1
                    st.rerun()

            # Playback View
            current_ep = episodes[st.session_state.ep_idx]
            sub_status = (
                "✅ Subtitles Loaded" if current_ep["sub"] else "❌ No Subtitles"
            )

            st.subheader(f"{selected_drama['title']} - {current_ep['label']}")
            st.caption(sub_status)

            # URLs
            st.code(
                f"Video URL: {current_ep['url']}\nSubtitle URL: {current_ep['sub'] if current_ep['sub'] else 'None'}",
                language="http",
            )

            # Execute Playback based on Platform
            if platform == "0":
                # Web Player Native
                st.video(current_ep["url"])
                if current_ep["sub"]:
                    st.info(
                        "💡 Note: Streamlit's native video player doesn't currently support embedding external subtitle URLs natively. Please use local player modes or cast it for subs."
                    )

            elif platform in ["1", "2", "3"]:
                player_name = (
                    selected_platform_name.split()[1].replace("(", "").replace(")", "")
                )
                if st.button(f"🎬 Launch {player_name} Player"):
                    play_video(current_ep["url"], current_ep["sub"], platform)
                    st.success(f"Command sent to {player_name}! Check your device.")

            elif platform == "4":
                st.info("URL Only Mode Selected. Copy the links from the box above.")


if __name__ == "__main__":
    main()
