import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import io
from datetime import datetime, timedelta

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="KWORB by Miixii", layout="wide", page_icon="🎹")

# --- DESIGN ---
st.markdown("""
    <style>
    .main { background-color: #0c0e12; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    [data-testid="stMetricValue"] { font-size: 32px; color: #1DB954; font-weight: 800; }
    div.stMetric > div:first-child {
        background-color: #161a21; border-radius: 15px; padding: 25px 20px; 
        border: 1px solid #2a2f3a; min-height: 180px !important;
    }
    div.stButton > button { 
        width: 100%; background-color: #1DB954; color: white; border-radius: 50px;
        font-weight: 800; text-transform: uppercase; border: none; padding: 10px 20px;
    }
    .podium-container { display: flex; justify-content: center; align-items: flex-end; gap: 15px; margin: 40px auto; }
    .podium-block { background-color: #161a21; border-radius: 15px; padding: 20px; text-align: center; border: 1px solid #2a2f3a; flex: 1; }
    .block-1 { min-height: 180px; order: 2; border-bottom: 4px solid #FFD700; } 
    .block-2 { min-height: 150px; order: 1; border-bottom: 4px solid #C0C0C0; } 
    .block-3 { min-height: 130px; order: 3; border-bottom: 4px solid #CD7F32; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FONCTIONS ---
def clean_strict(text):
    if not isinstance(text, str): return ""
    text = re.sub(r'\(.*?\)|\[.*?\]', '', text).split(' - ')[0]
    return re.sub(r'[^a-z0-9]', '', text.lower().strip())

def clean_kworb_number(val, is_daily=False):
    s = re.sub(r'[^\d]', '', str(val).strip())
    if not s: return 0
    num = int(s)
    if is_daily and s.endswith('0') and num > 1000: return num // 10
    return num

def format_space(n):
    return f"{int(n):,}".replace(',', ' ')

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_kworb_data(artist_info, my_tracks_for_this_artist):
    name, a_id = artist_info
    url = f"https://kworb.net/spotify/artist/{a_id}_songs.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(io.StringIO(response.text))
        df_k = next(t for t in tables if any("Song" in str(c) or "Track" in str(c) for c in t.columns))
        col_t, col_s, col_d = [c for c in df_k.columns if "Song" in str(c) or "Track" in str(c)][0], [c for c in df_k.columns if "Streams" in str(c)][0], [c for c in df_k.columns if "Daily" in str(c)][0]
        results = []
        for _, row in df_k.iterrows():
            t_clean = clean_strict(str(row[col_t]))
            if any(t_clean in mt or mt in t_clean for mt in my_tracks_for_this_artist):
                results.append({'Track': str(row[col_t]), 'Streams': clean_kworb_number(row[col_s]), 'Daily': clean_kworb_number(row[col_d], True), 'Artist': name, 'Date_Fetch': datetime.now().strftime("%Y-%m-%d")})
        return pd.DataFrame(results)
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("📂 IMPORTATION")
    uploaded_files = st.file_uploader("Upload CSV", type="csv", accept_multiple_files=True)
    artist_to_tracks = {}
    history = []
    
    if uploaded_files:
        for f in uploaded_files:
            try:
                df_temp = pd.read_csv(f, encoding='utf-8')
            except:
                df_temp = pd.read_csv(f, encoding='latin-1')
            
            if 'Date_Fetch' in df_temp.columns: # Archive
                for d in df_temp['Date_Fetch'].unique():
                    history.append(df_temp[df_temp['Date_Fetch'] == d].copy())
            else: # Exportify
                df_temp = df_temp.rename(columns={"Track Name":"Track","Artist Name(s)":"Artists_Names","Artist URI(s)":"Artists_URIs"})
                for _, row in df_temp.iterrows():
                    names, uris = str(row['Artists_Names']).split(','), str(row['Artists_URIs']).split(',')
                    t_clean = clean_strict(str(row['Track']))
                    for n, u in zip(names, uris):
                        a_key = (n.strip(), u.split(':')[-1].strip())
                        if a_key not in artist_to_tracks: artist_to_tracks[a_key] = set()
                        artist_to_tracks[a_key].add(t_clean)
        
        st.session_state['history'] = history
        if artist_to_tracks and st.button("🚀 LANCER L'ANALYSE"):
            all_res = []
            bar = st.progress(0)
            with ThreadPoolExecutor(max_workers=5) as ex:
                futures = {ex.submit(fetch_kworb_data, k, tuple(v)): k for k, v in artist_to_tracks.items()}
                for i, f in enumerate(as_completed(futures)):
                    bar.progress(int(((i+1)/len(artist_to_tracks))*100))
                    res = f.result()
                    if res is not None: all_res.append(res)
            if all_res:
                st.session_state['data'] = pd.concat(all_res).drop_duplicates(subset=['Track', 'Artist'])
                st.session_state['history'].append(st.session_state['data'])
                st.rerun()
        elif history: st.session_state['data'] = history[-1]

# --- 4. DASHBOARD ---
tab1, tab2 = st.tabs(["📊 Tableau de Bord", "📈 Suivi"])
with tab1:
    if 'data' in st.session_state:
        df = st.session_state['data']
        daily = df['Daily'].sum()
        k1, k2, k3 = st.columns(3)
        k1.metric("Streams Totaux", format_space(df['Streams'].sum()))
        k2.metric("Streams (24h)", format_space(daily))
        k3.metric("Titres", len(df))
        st.divider()
        st.markdown("### 🏆 Podium")
        top3 = df.sort_values('Daily', ascending=False).head(3)
        st.write(top3[['Track', 'Artist', 'Daily']])
        st.divider()
        st.dataframe(df[['Track', 'Artist', 'Streams', 'Daily']].sort_values('Daily', ascending=False), use_container_width=True)

with tab2:
    if 'history' in st.session_state and len(st.session_state['history']) > 1:
        all_h = pd.concat(st.session_state['history'])
        st.download_button("📦 Sauvegarder l'Historique Global", all_h.to_csv(index=False).encode('utf-8'), "archive.csv")
        fig = px.line(pd.DataFrame([{'Date': d, 'Streams': dfh['Streams'].sum()} for dfh in st.session_state['history'] for d in dfh['Date_Fetch'].unique()]), x='Date', y='Streams', markers=True, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
