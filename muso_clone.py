import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import io

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="KWORB by Miixii", layout="wide", page_icon="🎹")

# --- DESIGN MODERNE (RETOUR VERSION SOBRE) ---
st.markdown("""
    <style>
    /* 1. Fond Global et Typo */
    .main { background-color: #0c0e12; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    
    /* OPTION 2 : OPTIMISATION MOBILE */
    @media (max-width: 768px) {
        [data-testid="stMetric"] { min-width: 100% !important; }
    }

    /* 2. Modernisation des Métriques (Cards) */
    [data-testid="stMetricValue"] { 
        font-size: 32px; 
        color: #1DB954; 
        font-weight: 800; 
        margin-top: 10px !important; 
    }
    [data-testid="stMetricLabel"] { 
        font-size: 14px; 
        color: #a0a0a0; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    
    div.stMetric > div:first-child {
        background-color: #161a21;
        border-radius: 15px;
        padding: 25px 20px; 
        border: 1px solid #2a2f3a;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 10px;
        display: flex;
        flex-direction: column;
        /* FIX : Aligne toutes les cases à la même taille */
        min-height: 180px !important;
        justify-content: center;
    }

    /* 3. FIX INPUTS (RECHERCHE / ARTISTE / STREAMS) */
    .stTextInput>div>div>input, 
    .stNumberInput>div>div>input,
    .stSelectbox div[data-baseweb="select"] > div {
        border-radius: 10px !important;
        background-color: #161a21 !important;
        border: 1px solid #2a2f3a !important;
        color: white !important;
        height: 45px;
    }
    div[data-baseweb="select"] {
        background-color: #161a21 !important;
        border-radius: 10px !important;
    }

    /* 5. Boutons, Sidebar et Tableaux */
    div.stButton > button { 
        width: 100%; background-color: #1DB954; color: white; border-radius: 50px;
        font-weight: 800; text-transform: uppercase; letter-spacing: 1px; border: none;
        padding: 10px 20px; transition: all 0.3s ease;
    }
    div.stButton > button:hover { background-color: #1ed760; transform: scale(1.02); }
    [data-testid="stSidebar"] { background-color: #11141a; border-right: 1px solid #2a2f3a; }
    [data-testid="stSidebar"] .stMarkdown h2 { color: #1DB954; }
    a { color: #1DB954; text-decoration: none; font-weight: bold; }
    h1, h2, h3 { font-weight: 800; color: white; }
    h4 { color: #a0a0a0; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;}
    .stDataFrame, .stTable { border-radius: 15px; overflow: hidden; border: 1px solid #2a2f3a; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FONCTIONS TECHNIQUES ---
def clean_strict(text):
    if not isinstance(text, str): return ""
    text = re.sub(r'\(.*?\)|\[.*?\]', '', text)
    text = text.split(' - ')[0]
    text = text.replace("’", "'").replace("œ", "oe")
    return re.sub(r'[^a-z0-9]', '', text.lower().strip())

def clean_kworb_number(val, is_daily=False):
    s = re.sub(r'[^\d]', '', str(val).strip())
    if not s: return 0
    num = int(s)
    if is_daily and s.endswith('0') and num > 1000: return num // 10
    return num

def format_space(n):
    return f"{int(n):,}".replace(',', ' ')

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_kworb_data(artist_info, my_tracks_for_this_artist):
    name, a_id = artist_info
    url = f"https://kworb.net/spotify/artist/{a_id}_songs.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 429: return "RATE_LIMIT"
        response.encoding = 'utf-8' 
        tables = pd.read_html(io.StringIO(response.text))
        df_k = pd.DataFrame()
        for t in tables:
            if any("Song" in str(c) or "Track" in str(c) for c in t.columns):
                df_k = t
                break
        if df_k.empty: return None

        col_t = [c for c in df_k.columns if "Song" in str(c) or "Track" in str(c)][0]
        col_s = [c for c in df_k.columns if "Streams" in str(c)][0]
        col_d = [c for c in df_k.columns if "Daily" in str(c)][0]

        results = []
        my_tracks_list = list(my_tracks_for_this_artist)
        for _, row in df_k.iterrows():
            title_raw = str(row[col_t])
            title_clean = clean_strict(title_raw)
            if any(title_clean in mt or mt in title_clean for mt in my_tracks_list):
                results.append({
                    'Track': title_raw,
                    'Streams': clean_kworb_number(row[col_s]),
                    'Daily': clean_kworb_number(row[col_d], is_daily=True),
                    'Artist': name
                })
        return pd.DataFrame(results) if results else None
    except: return None

# --- 3. UI PLACEHOLDERS ---
progress_placeholder = st.empty()
status_placeholder = st.empty()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("📖 GUIDE D'UTILISATION")
    st.info("""
    1. Rends-toi sur [Exportify](https://exportify.app).
    2. Connecte ton compte Spotify.
    3. Exporte ta playlist en **CSV**.
    4. Importe le fichier ci-dessous.
    """)
    st.divider()
    
    st.header("📂 IMPORTATION")
    uploaded_file = st.file_uploader("Upload ton fichier CSV", type="csv")
    
    if uploaded_file:
        try:
            df_liked = pd.read_csv(uploaded_file, encoding='utf-8')
        except UnicodeDecodeError:
            df_liked = pd.read_csv(uploaded_file, encoding='latin-1')

        df_liked = df_liked.rename(columns={
            "Track Name": "Track", "Nom du titre": "Track",
            "Artist Name(s)": "Artists_Names", "Nom(s) de l'artiste": "Artists_Names",
            "Artist URI(s)": "Artists_URIs", "URI(s) de l'artiste": "Artists_URIs"
        })
        
        artist_to_tracks = {}
        if "Track" in df_liked.columns:
            for _, row in df_liked.iterrows():
                names = [n.strip() for n in str(row['Artists_Names']).split(',')]
                uris = [u.strip() for u in str(row['Artists_URIs']).split(',')] if "Artists_URIs" in df_liked.columns else [f"none:{n}" for n in names]
                t_clean = clean_strict(str(row['Track']))
                for n, u in zip(names, uris):
                    a_id = u.split(':')[-1].strip()
                    a_key = (n, a_id)
                    if a_key not in artist_to_tracks: artist_to_tracks[a_key] = set()
                    artist_to_tracks[a_key].add(t_clean)

            if st.button("🚀 LANCER L'ANALYSE"):
                all_res = []
                total_artists = len(artist_to_tracks)
                bar = progress_placeholder.progress(0)
                txt = status_placeholder.empty()
                
                with ThreadPoolExecutor(max_workers=3) as ex:
                    futures = {ex.submit(fetch_kworb_data, art, tuple(tracks)): art for art, tracks in artist_to_tracks.items()}
                    completed = 0
                    for f in as_completed(futures):
                        completed += 1
                        percent = int((completed / total_artists) * 100)
                        bar.progress(percent)
                        res = f.result()
                        if isinstance(res, str) and res == "RATE_LIMIT":
                            txt.warning("Débit limité par Kworb. Pause automatique...")
                        else:
                            txt.text(f"Récupération : {percent}% (Artiste {completed}/{total_artists})")
                            if res is not None: all_res.append(res)
                
                if all_res:
                    st.session_state['data'] = pd.concat(all_res).drop_duplicates(subset=['Track', 'Artist'])
                    bar.empty()
                    txt.empty()
                    st.rerun()

    # Reset filtres
    has_filters = (st.session_state.get('search', "") != "" or 
                    st.session_state.get('artist_sel', "Tous") != "Tous" or 
                    st.session_state.get('min_streams', 0) > 0)

    if st.session_state.get('data') is not None and has_filters:
        st.divider()
        if st.button("🔄 Reset filtres"):
            st.session_state['search'] = ""
            st.session_state['artist_sel'] = "Tous"
            st.session_state['min_streams'] = 0
            st.rerun()

    st.divider()
    st.caption("🚀 Developed by Miixii")
    st.caption("📊 Data sourced from Kworb.net")
    st.caption("© 2026 Miixii Production")

# --- 5. DASHBOARD ---
with st.container():
    st.title("📊 KWORB by Miixii")

    if 'data' not in st.session_state:
        st.session_state['data'] = None

    if st.session_state['data'] is not None:
        st.markdown("### 🔍 Filtres")
        f_col1, f_col2, f_col3 = st.columns(3)
        df_filtered = st.session_state['data'].copy()
        
        with f_col1:
            search_query = st.text_input("Rechercher un Titre", key="search")
        with f_col2:
            artist_list = ["Tous"] + sorted(df_filtered['Artist'].unique().tolist())
            sel_artist = st.selectbox("Filtrer par Artiste", artist_list, key="artist_sel")
        with f_col3:
            min_s = st.number_input("Streams Minimum", min_value=0, value=0, step=100000, key="min_streams")

        if search_query:
            df_filtered = df_filtered[df_filtered['Track'].str.contains(search_query, case=False, na=False)]
        if sel_artist != "Tous":
            df_filtered = df_filtered[df_filtered['Artist'] == sel_artist]
        df_filtered = df_filtered[df_filtered['Streams'] >= min_s]

        # PROJECTION MENSUELLE
        daily_sum = df_filtered['Daily'].sum()
        monthly_proj = daily_sum * 30.5

        st.markdown("### 🚀 Chiffres Clés")
        k1, k2, k3, k4 = st.columns(4)
        
        with k1:
            st.metric("Streams Totaux", format_space(df_filtered['Streams'].sum()))
        with k2:
            st.metric("Streams (24h)", format_space(daily_sum))
        with k3:
            st.metric("Projection 30j", format_space(monthly_proj), delta=f"+{format_space(daily_sum)} / jour")
        with k4:
            st.metric("Titres Trouvés", len(df_filtered))

        st.divider()

        # THEME DYNAMIQUE 
        color_theme = 'Viridis' if sel_artist != "Tous" else 'Greens'

        col_g, col_d = st.columns([1.2, 0.8])
        with col_g:
            st.markdown("#### 🔥 Top 15 - Performance 24h")
            top_15 = df_filtered.sort_values('Daily', ascending=False).head(15)
            
            # --- VERSION OPTIMISÉE SANS "TITRE=" ET "TEXT=" ---
            fig_bar = px.bar(top_15, x='Daily', y='Track', color='Daily', orientation='h', 
                             template="plotly_dark", color_continuous_scale=color_theme,
                             text=top_15['Daily'].apply(format_space))
            
            # On définit un template de survol ultra-pro : Titre en gras, puis les streams.
            fig_bar.update_traces(
                hovertemplate="<b>%{y}</b><br>Streams : %{x:,}<extra></extra>"
            )
            # --------------------------------------------------
            
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_d:
            with st.expander("🔍 Focus Parts Artistes", expanded=True):
                art_sums = df_filtered.groupby('Artist')['Streams'].sum().reset_index()
                fig_pie = px.pie(art_sums, values='Streams', names='Artist', hole=0.5, template="plotly_dark")
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()
        
        d_col1, d_col2 = st.columns([0.8, 0.2])
        with d_col1:
            st.markdown("#### 📋 Détails des Productions")
        with d_col2:
            csv = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Export CSV", data=csv, file_name='stats_kworb_miixii.csv', mime='text/csv')
        
        sort_choice = st.radio("Trier par :", ["Top Daily (24h)", "Top Streams (Total)"], horizontal=True)
        sort_col = 'Daily' if "Daily" in sort_choice else 'Streams'
        
        df_table = df_filtered.sort_values(sort_col, ascending=False).copy()
        df_table['Streams Totaux'] = df_table['Streams'].apply(format_space)
        df_table['Daily (24h)'] = df_table['Daily'].apply(format_space)
        st.dataframe(df_table[['Track', 'Artist', 'Streams Totaux', 'Daily (24h)']], use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### 🏆 Classement Top Artistes")
        art_stats = df_filtered.groupby('Artist').agg({'Streams': 'sum', 'Daily': 'sum', 'Track': 'count'}).reset_index()
        art_stats = art_stats.sort_values('Streams', ascending=False).reset_index(drop=True)
        art_stats.index = art_stats.index + 1
        art_stats.insert(0, 'Rang', art_stats.index.map(lambda x: f"#{x}"))
        art_stats['Total Streams'] = art_stats['Streams'].apply(format_space)
        art_stats['Daily Global'] = art_stats['Daily'].apply(format_space)
        st.table(art_stats[['Rang', 'Artist', 'Total Streams', 'Daily Global', 'Track']].rename(columns={'Artist': 'Artiste', 'Track': 'Nb Titres'}))

    else:
        st.info("👈 Importe ton CSV pour commencer.")
