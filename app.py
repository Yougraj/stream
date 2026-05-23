import base64
import os
import re
import subprocess
from urllib.parse import quote

import cloudscraper
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup

# --- Try loading the live search plugin ---
try:
    from st_keyup import st_keyup

    HAS_KEYUP = True
except ImportError:
    HAS_KEYUP = False

# --- Configuration & Metadata ---
VERSION = "0.0.9 (Mobile Deep Links Edition)"
BASE_URL = "https://kisskh.buzz/"
AJAX_URL = BASE_URL + "wp-admin/admin-ajax.php"
BLOGGER_BLOG_ID = "1422331367239821646"
BLOGGER_FEED_URL = f"https://www.blogger.com/feeds/{BLOGGER_BLOG_ID}/posts/default"

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)
scraper.headers.update(
    {
        "Referer": BASE_URL,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
)

# --- State Management Initialization ---
if "selected_drama" not in st.session_state:
    st.session_state.selected_drama = None
if "ep_idx" not in st.session_state:
    st.session_state.ep_idx = 0
if "last_query" not in st.session_state:
    st.session_state.last_query = ""


# --- Helper Functions ---
def srt_to_vtt(subtitle_text):
    if not subtitle_text:
        return ""
    text = subtitle_text.strip()
    if text.startswith("WEBVTT"):
        return text
    vtt = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
    return vtt


def render_custom_player(video_url, subtitle_text=None):
    sub_track_js = ""
    if subtitle_text:
        vtt_text = srt_to_vtt(subtitle_text)
        b64_sub = base64.b64encode(vtt_text.encode("utf-8")).decode("utf-8")
        sub_track_js = f"""
        const subText = decodeURIComponent(escape(window.atob('{b64_sub}')));
        const blob = new Blob([subText], {{ type: 'text/vtt' }});
        const track = document.createElement('track');
        track.src = URL.createObjectURL(blob);
        track.kind = 'captions';
        track.srclang = 'en';
        track.label = 'English';
        track.default = true;
        video.appendChild(track);
        """

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            body {{ margin: 0; background: #0e1117; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; overflow: hidden; }}
            video {{ width: 100%; height: 100%; max-height: 100vh; outline: none; border-radius: 8px; }}
            #error-msg {{ display: none; color: #ff4b4b; font-family: sans-serif; padding: 20px; text-align: center; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div id="error-msg">
            <b>⚠️ Video Blocked by Server (CORS Error)</b><br><br>
            The host server prevents this video from playing inside the web browser.<br><br>
            👇 <b>Scroll down to the "Play in External App" section to open it directly!</b> 👇
        </div>
        <video id="video" controls crossorigin="anonymous" playsinline></video>
        <script>
            var video = document.getElementById('video');
            var videoSrc = "{video_url}";
            {sub_track_js}
            if (Hls.isSupported() && videoSrc.includes('.m3u8')) {{
                var hls = new Hls();
                hls.loadSource(videoSrc);
                hls.attachMedia(video);
                hls.on(Hls.Events.ERROR, function (event, data) {{
                    if (data.fatal) {{
                        document.getElementById('video').style.display = 'none';
                        document.getElementById('error-msg').style.display = 'block';
                    }}
                }});
            }} else if (video.canPlayType('application/vnd.apple.mpegurl') || !videoSrc.includes('.m3u8')) {{
                video.src = videoSrc;
            }} else {{
                document.getElementById('video').style.display = 'none';
                document.getElementById('error-msg').style.display = 'block';
            }}
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=500)


@st.cache_data(show_spinner=False)
def get_search_results(query):
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
        res = scraper.post(AJAX_URL, data=payload, timeout=15)
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
            img_src = (
                (img_tag.get("data-src") or img_tag.get("src"))
                if img_tag
                else "https://via.placeholder.com/300x400.png?text=No+Image"
            )
            results.append({"title": title, "link": link, "ep": ep, "img": img_src})
        return results
    except Exception:
        return []


def fetch_links(drama_title):
    clean_title = re.sub(r"\(.*?\)", "", drama_title)
    words = re.findall(r"\w+", clean_title)
    search_queries = []
    if len(words) >= 4:
        search_queries.append(" ".join(words[:4]))
    if len(words) >= 2:
        search_queries.append(" ".join(words[:2]))
    if len(words) > 0:
        search_queries.append(" ".join(words[:1]))
    search_queries = list(dict.fromkeys(search_queries))

    for sq in search_queries:
        feed_url = f"{BLOGGER_FEED_URL}?q={quote(sq)}&alt=json&max-results=3"
        try:
            data = scraper.get(feed_url, timeout=10).json()
            if "entry" in data.get("feed", {}):
                for entry in data["feed"]["entry"]:
                    raw_content = entry["content"]["$t"]
                    clean_content = BeautifulSoup(raw_content, "html.parser").get_text()

                    if "|" in clean_content and "http" in clean_content:
                        eps = []
                        for i, part in enumerate(clean_content.split(";"), 1):
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
                                    eps.append(
                                        {
                                            "label": f"Episode {i}",
                                            "url": v_url,
                                            "sub": s_url,
                                        }
                                    )

                        if eps:
                            return eps
        except Exception:
            continue
    return []


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_subtitle_content(url):
    if not url:
        return None
    try:
        r = scraper.get(url, timeout=15)
        r.raise_for_status()
        content = r.text.strip()
        if "-->" in content or content.startswith("WEBVTT"):
            return content
        return None
    except Exception:
        return None


def play_video_native_local(url, sub_url, platform):
    if not url:
        return
    try:
        if platform == "1":
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
        elif platform == "2":
            os.system(f"open vlc://{url}")
        elif platform == "3":
            cmd = ["mpv", url]
            if sub_url:
                cmd.append(f"--sub-file={sub_url}")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        st.error(f"Failed to launch native player: {e}")


# --- Streamlit UI Main App ---
def main():
    st.set_page_config(page_title="Deha Drama Streamer", layout="wide", page_icon="🎬")

    st.title("🎬 Deha Drama Streamer")

    st.sidebar.header("⚙️ Configuration")
    platform_map = {
        "Browser (Web Player)": "0",
        "Local Android (Termux)": "1",
        "Local iOS (Terminal)": "2",
        "Local Linux (MPV)": "3",
        "URL Only": "4",
    }
    selected_platform_name = st.sidebar.selectbox(
        "Select Environment:", list(platform_map.keys())
    )
    platform = platform_map[selected_platform_name]

    if HAS_KEYUP:
        query = st_keyup(
            "🔍 Live Search Drama:",
            placeholder="Start typing a drama name...",
            debounce=500,
        )
    else:
        query = st.text_input(
            "🔍 Search Drama (Press Enter):", placeholder="Type a drama name here..."
        )

    st.divider()

    if query != st.session_state.last_query:
        st.session_state.selected_drama = None
        st.session_state.ep_idx = 0
        st.session_state.last_query = query

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

    elif st.session_state.selected_drama is not None:
        selected_drama = st.session_state.selected_drama

        if st.button("⬅️ Back to Search Results", use_container_width=True):
            st.session_state.selected_drama = None
            st.rerun()

        with st.spinner("Fetching episodes from Blogger..."):
            episodes = fetch_links(selected_drama["title"])

        if not episodes:
            st.error(
                f"No streamable episodes found in the database for '{selected_drama['title']}'."
            )
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

        current_ep = episodes[st.session_state.ep_idx]
        video_url = current_ep["url"]
        sub_url = current_ep["sub"]

        if platform == "0":
            # NATIVE BROWSER PLAYER (With HLS support)
            raw_sub_text = None
            if sub_url:
                with st.spinner("Downloading subtitles..."):
                    raw_sub_text = fetch_subtitle_content(sub_url)
                st.caption(
                    f"{current_ep['label']} — ✅ Subtitles Loaded"
                    if raw_sub_text
                    else f"{current_ep['label']} — ❌ Failed to load subtitles."
                )
            else:
                st.caption(f"{current_ep['label']} — ❌ No Subtitles Available")

            # Render custom HLS Player
            render_custom_player(video_url, raw_sub_text)

            st.divider()
            # --- EXTERNAL APP DEEP LINKS (For Mobile Phones) ---
            st.markdown("### 📱 Play in External App (Bypasses CORS)")

            clean_video_url = video_url.strip().replace(" ", "%20")

            # 🔥 BYPASS TRICK: Append the Referer so servers don't block the stream
            # (Note: Not all Android video players support this syntax, but it prevents the 403 error on players that do)
            referer_url = f"{clean_video_url}|Referer={BASE_URL}"

            scheme = "https" if clean_video_url.startswith("https") else "http"
            url_no_scheme = referer_url.replace(f"{scheme}://", "")

            mime_type = (
                "application/x-mpegURL"
                if ".m3u8" in clean_video_url.lower()
                else "video/*"
            )
            mpv_mime_type = "video/*"

            html_url_no_scheme = url_no_scheme.replace("&", "&amp;")
            sub_param = f";S.subs={quote(sub_url.strip())}" if sub_url else ""

            intent_vlc_android = f"intent://{html_url_no_scheme}#Intent;scheme={scheme};package=org.videolan.vlc;action=android.intent.action.VIEW;type={mime_type};end"
            intent_vlc_ios = (
                f"vlc-x-callback://x-callback-url/stream?url={quote(clean_video_url)}"
            )
            intent_mpv = f"intent://{html_url_no_scheme}#Intent;scheme={scheme};package=is.xyz.mpv;action=android.intent.action.VIEW;type={mpv_mime_type}{sub_param};end"
            intent_mx = f"intent://{html_url_no_scheme}#Intent;scheme={scheme};package=com.mxtech.videoplayer.ad;action=android.intent.action.VIEW;type={mime_type};end"
            intent_chooser = f"intent://{html_url_no_scheme}#Intent;scheme={scheme};action=android.intent.action.VIEW;type={mime_type};end"

            st.markdown(
                f"""
            <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px;">
                <a href="{intent_vlc_android}" style="background-color: #FF8800; color: white; padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">🟠 VLC (Android)</a>
                <a href="{intent_mpv}" style="background-color: #3E3B51; color: white; padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">🟣 MPV (Android)</a>
                <a href="{intent_mx}" style="background-color: #1A73E8; color: white; padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">🔵 MX Player</a>
                <a href="{intent_chooser}" style="background-color: #4CAF50; color: white; padding: 12px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">🟢 Choose App</a>
            </div>
            """,
                unsafe_allow_html=True,
            )
        elif platform in ["1", "2", "3"]:
            st.caption(f"{current_ep['label']} — Ready for Local Execution")
            player_name = (
                selected_platform_name.split()[1].replace("(", "").replace(")", "")
            )
            if st.button(
                f"🎬 Execute {player_name} Command on Host Device",
                use_container_width=True,
            ):
                play_video_native_local(video_url, sub_url, platform)
                st.success(f"Command executed on server for {player_name}!")

        elif platform == "4":
            st.code(
                f"Video URL: {video_url}\nSubtitle URL: {sub_url if sub_url else 'None'}",
                language="http",
            )


if __name__ == "__main__":
    main()
