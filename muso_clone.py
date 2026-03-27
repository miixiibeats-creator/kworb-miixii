import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="KWORB by Miixii", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #1DB954; font-weight: bold; }
    div.stButton > button { width: 100%; background-color: #1DB954; color: white; border-radius: 20px; font-weight: bold; }
    a { color: #1DB954; text-decoration: none; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FONCTIONS TECHNIQUES ---
def clean_strict(text):
    if not isinstance(text, str): return ""
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

def fetch_kworb_data(artist_info, my_tracks_for_this_artist):
    name, a_id = artist_info
    url = f"https://kworb.net/spotify/artist/{a_id}_songs.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8' 
        tables = pd.read_html(response.text)
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
        for _, row in df_k.iterrows():
            title_clean = clean_strict(str(row[col_t]))
            if title_clean in my_tracks_for_this_artist:
                results.append({
                    'Track': str(row[col_t]),
                    'Streams': clean_kworb_number(row[col_s]),
                    'Daily': clean_kworb_number(row[col_d], is_daily=True),
                    'Artist': name
                })
        return pd.DataFrame(results) if results else None
    except: return None

# --- 3. SIDEBAR ---
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
    
    # --- AJOUT DES CRÉDITS ---
    st.markdown("---")
    st.caption("🚀 Developed by Miixii")
    st.caption("📊 Data sourced from Kworb.net")
    st.caption("© 2026 Miixii Production")

# --- 4. DASHBOARD ---
st.title("📊 KWORB by Miixii")

if 'data' not in st.session_state:
    st.session_state['data'] = None

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

        if st.sidebar.button("🚀 LANCER L'ANALYSE"):
            all_res = []
            with st.status("🔍 Récupération des données..."):
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futures = [ex.submit(fetch_kworb_data, art, tracks) for art, tracks in artist_to_tracks.items()]
                    for f in futures:
                        if f.result() is not None: all_res.append(f.result())
            if all_res:
                st.session_state['data'] = pd.concat(all_res).drop_duplicates(subset=['Track', 'Artist'])
                st.rerun()

if st.session_state['data'] is not None:
    # --- SECTION FILTRES ---
    st.markdown("### 🔍 Filtres")
    f_col1, f_col2, f_col3 = st.columns(3)
    df_filtered = st.session_state['data'].copy()
    
    with f_col1:
        search_query = st.text_input("Rechercher un Titre", "")
    with f_col2:
        artist_list = ["Tous"] + sorted(df_filtered['Artist'].unique().tolist())
        sel_artist = st.selectbox("Filtrer par Artiste", artist_list)
    with f_col3:
        max_s = int(df_filtered['Streams'].max()) if not df_filtered.empty else 1000
        min_s = st.slider("Streams Minimum", 0, max_s, 0)

    # Application des filtres
    if search_query:
        df_filtered = df_filtered[df_filtered['Track'].str.contains(search_query, case=False, na=False)]
    if sel_artist != "Tous":
        df_filtered = df_filtered[df_filtered['Artist'] == sel_artist]
    df_filtered = df_filtered[df_filtered['Streams'] >= min_s]

    st.markdown("### 🚀 Chiffres Clés")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Streams Totaux", format_space(df_filtered['Streams'].sum()))
    k2.metric("Streams (24h)", format_space(df_filtered['Daily'].sum()))
    k3.metric("Titres Trouvés", len(df_filtered))
    k4.metric("Moyenne/Titre", format_space(df_filtered['Streams'].mean() if not df_filtered.empty else 0))

    st.divider()

    col_g, col_d = st.columns([1.2, 0.8])
    with col_g:
        st.markdown("#### 🔥 Top 15 - Performance 24h")
        top_15 = df_filtered.sort_values('Daily', ascending=False).head(15)
        fig_bar = px.bar(top_15, x='Daily', y='Track', color='Daily', orientation='h', 
                         template="plotly_dark", color_continuous_scale='Greens',
                         text=top_15['Daily'].apply(format_space))
        fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_d:
        st.markdown("#### 🎤 Parts / Artiste")
        art_sums = df_filtered.groupby('Artist')['Streams'].sum().reset_index()
        fig_pie = px.pie(art_sums, values='Streams', names='Artist', hole=0.5, template="plotly_dark")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()
    st.markdown("#### 📋 Détails des Productions")
    df_table = df_filtered.sort_values('Daily', ascending=False).copy()
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
