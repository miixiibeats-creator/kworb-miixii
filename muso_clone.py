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

# --- DESIGN MODERNE ---
st.markdown("""
    <style>
    .main { background-color: #0c0e12; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    @media (max-width: 768px) { [data-testid="stMetric"] { min-width: 100% !important; } }
    [data-testid="stMetricValue"] { font-size: 32px; color: #1DB954; font-weight: 800; margin-top: 10px !important; }
    [data-testid="stMetricLabel"] { font-size: 14px; color: #a0a0a0; text-transform: uppercase; letter-spacing: 1px; }
    div.stMetric > div:first-child {
        background-color: #161a21; border-radius: 15px; padding: 25px 20px; 
        border: 1px solid #2a2f3a; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 10px; display: flex; flex-direction: column; min-height: 180px !important; justify-content: center;
    }
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox div[data-baseweb="select"] > div {
        border-radius: 10px !important; background-color: #161a21 !important; border: 1px solid #2a2f3a !important; color: white !important; height: 45px;
    }
    div[data-baseweb="select"] { background-color: #161a21 !important; border-radius: 10px !important; }
    div.stButton > button { 
        width: 100%; background-color: #1DB954; color: white; border-radius: 50px;
        font-weight: 800; text-transform: uppercase; letter-spacing: 1px; border: none; padding: 10px 20px; transition: all 0.3s ease;
    }
    div.stButton > button:hover { background-color: #1ed760; transform: scale(1.02); }
    [data-testid="stSidebar"] { background-color: #11141a; border-right: 1px solid #2a2f3a; }
    [data-testid="stSidebar"] .stMarkdown h2 { color: #1DB954; }
    a { color: #1DB954; text-decoration: none; font-weight: bold; }
    h1, h2, h3 { font-weight: 800; color: white; }
    h4 { color: #a0a0a0; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;}
    .stDataFrame, .stTable { border-radius: 15px; overflow: hidden; border: 1px solid #2a2f3a; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: transparent; border-radius: 4px 4px 0px 0px; color: #a0a0a0; font-weight: 700; }
    .stTabs [aria-selected="true"] { color: #1DB954 !important; border-bottom-color: #1DB954 !important; }
    
    /* --- STYLE DU PODIUM CORRIGÉ --- */
    .podium-container { display: flex; justify-content: center; align-items: flex-end; gap: 15px; margin: 40px auto; max-width: 900px; }
    .podium-block { background-color: #161a21; border-radius: 15px 15px 10px 10px; padding: 20px; text-align: center; border: 1px solid #2a2f3a; flex: 1; position: relative; transition: all 0.3s ease; min-width: 0; }
    .podium-block:hover { transform: translateY(-5px); border-color: #1DB954; }
    .podium-rank { font-size: 40px; font-weight: 900; position: absolute; top: -25px; left: 15px; text-shadow: 2px 2px 10px rgba(0,0,0,0.8); }
    .podium-track { font-size: 16px; font-weight: 700; color: white; margin-top: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .podium-artist { font-size: 13px; color: #a0a0a0; margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .podium-streams { font-size: 22px; font-weight: 800; color: #1DB954; }
    .podium-label { font-size: 10px; color: #808080; text-transform: uppercase; letter-spacing: 1px; }
    .rank-1 { color: #FFD700; } 
    .rank-2 { color: #C0C0C0; } 
    .rank-3 { color: #CD7F32; }
    
    .block-1 { min-height: 180px; order: 2; border-bottom: 4px solid #FFD700; } 
    .block-2 { min-height: 150px; order: 1; border-bottom: 4px solid #C0C0C0; } 
    .block-3 { min-height: 130px; order: 3; border-bottom: 4px solid #CD7F32; padding-bottom: 25px; }
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

def safe_parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        if "-02-29" in date_str:
            new_date = date_str.replace("-02-29", "-02-28")
            return datetime.strptime(new_date, "%Y-%m-%d")
        return datetime.now()

@st.cache_data(show_spinner=False, ttl=86400)
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
                    'Track': title_raw, 'Streams': clean_kworb_number(row[col_s]),
                    'Daily': clean_kworb_number(row[col_d], is_daily=True),
                    'Artist': name, 'Date_Fetch': datetime.now().strftime("%Y-%m-%d")
                })
        return pd.DataFrame(results) if results else None
    except: return None

# --- 3. UI PLACEHOLDERS ---
progress_placeholder = st.empty()
status_placeholder = st.empty()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("📖 GUIDE D'UTILISATION")
    st.info("1. Rends-toi sur [Exportify](https://exportify.app).\n2. Connecte Spotify.\n3. Exporte en CSV.\n4. Importe ici.")
    st.divider()
    st.header("📂 IMPORTATION")
    uploaded_files = st.file_uploader("Upload ton fichier CSV (Exportify ou Archive)", type="csv", accept_multiple_files=True)
    
    if uploaded_files:
        artist_to_tracks = {}
        current_upload_history = []
        for uploaded_file in uploaded_files:
            fname = uploaded_file.name
            date_found = re.findall(r'\d{4}-\d{2}-\d{2}', fname)
            file_date = date_found[-1] if date_found else datetime.now().strftime("%Y-%m-%d")
            
            try:
                try: df_temp = pd.read_csv(uploaded_file, encoding='utf-8')
                except: df_temp = pd.read_csv(uploaded_file, encoding='latin-1')
                
                # CAS 1 : C'est une archive générée par l'app (déjà formatée avec Date_Fetch)
                if 'Date_Fetch' in df_temp.columns and 'Track' in df_temp.columns and 'Streams' in df_temp.columns:
                    unique_dates = df_temp['Date_Fetch'].unique()
                    if len(unique_dates) > 1:
                        # On sépare l'archive en plusieurs dataframes par date pour simuler plusieurs imports
                        for d in sorted(unique_dates):
                            current_upload_history.append(df_temp[df_temp['Date_Fetch'] == d].copy())
                    else:
                        current_upload_history.append(df_temp)
                
                # CAS 2 : C'est un export direct d'Exportify
                else:
                    df_temp['Date_Fetch'] = file_date
                    df_temp = df_temp.rename(columns={
                        "Track Name": "Track", "Nom du titre": "Track",
                        "Artist Name(s)": "Artists_Names", "Nom(s) de l'artiste": "Artists_Names",
                        "Artist URI(s)": "Artists_URIs", "URI(s) de l'artiste": "Artists_URIs"
                    })
                    if "Track" in df_temp.columns:
                        for _, row in df_temp.iterrows():
                            names = [n.strip() for n in str(row['Artists_Names']).split(',')]
                            uris = [u.strip() for u in str(row['Artists_URIs']).split(',')] if "Artists_URIs" in df_temp.columns else [f"none:{n}" for n in names]
                            t_clean = clean_strict(str(row['Track']))
                            for n, u in zip(names, uris):
                                a_id = u.split(':')[-1].strip()
                                a_key = (n, a_id)
                                if a_key not in artist_to_tracks: artist_to_tracks[a_key] = set()
                                artist_to_tracks[a_key].add(t_clean)
            except Exception as e:
                st.error(f"Erreur fichier {fname}: {e}")
        
        st.session_state['history'] = current_upload_history

        if artist_to_tracks and st.button("🚀 LANCER L'ANALYSE"):
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
                    txt.text(f"Récupération : {percent}% (Artiste {completed}/{total_artists})")
                    res = f.result()
                    if res is not None and not isinstance(res, str): all_res.append(res)
            if all_res:
                st.session_state['data'] = pd.concat(all_res).drop_duplicates(subset=['Track', 'Artist'])
                st.session_state['data']['Date_Fetch'] = datetime.now().strftime("%Y-%m-%d")
                st.session_state['history'].append(st.session_state['data'])
                bar.empty()
                txt.empty()
                st.rerun()
        elif current_upload_history and not artist_to_tracks:
            # Si on a chargé une archive sans nouveaux titres à chercher sur Kworb
            st.session_state['data'] = current_upload_history[-1]
            st.success("Archive chargée avec succès !")

    st.divider()
    st.caption("🚀 Developed by Miixii | © 2026")

# --- 5. DASHBOARD ---
tab1, tab2 = st.tabs(["📊 Tableau de Bord", "📈 Suivi de Progression"])

with tab1:
    st.title("📊 KWORB by Miixii")
    if 'data' in st.session_state and st.session_state['data'] is not None:
        df_filtered = st.session_state['data'].copy()
        
        f1, f2, f3 = st.columns([1, 1, 1])
        with f1: search = st.text_input("Rechercher un Titre", key="s_main")
        with f2:
            alist = sorted(df_filtered['Artist'].unique().tolist())
            sel_art = st.multiselect("Filtrer par Artiste(s)", options=alist, key="a_main")
        with f3: min_s = st.number_input("Streams Minimum", min_value=0, step=100000, key="m_main")
        
        def clear_filters():
            st.session_state["s_main"] = ""
            st.session_state["a_main"] = []
            st.session_state["m_main"] = 0

        if search or sel_art or min_s > 0:
            st.button("🔄 Réinitialiser les filtres", on_click=clear_filters)

        if search: df_filtered = df_filtered[df_filtered['Track'].str.contains(search, case=False)]
        if sel_art: df_filtered = df_filtered[df_filtered['Artist'].isin(sel_art)]
        df_filtered = df_filtered[df_filtered['Streams'] >= min_s]

        daily_sum = df_filtered['Daily'].sum()
        monthly_proj = daily_sum * 30.5
        est_royalties = monthly_proj * 0.0035

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Streams Totaux", format_space(df_filtered['Streams'].sum()), help="Somme cumulée de tous les streams détectés sur Kworb.")
        k2.metric("Streams (24h)", format_space(daily_sum), help="Nombre total de streams générés sur les dernières 24h.")
        k3.metric("Projection 30j", format_space(monthly_proj), delta=f"{format_space(est_royalties)} €/mois est.", help="Estimation mensuelle basée sur le Daily actuel.")
        k4.metric("Titres Trouvés", len(df_filtered), help="Nombre de titres identifiés.")

        st.divider()
        st.markdown("### 🏆 Podium - Performance 24h")
        top_3 = df_filtered.sort_values('Daily', ascending=False).head(3)
        
        p_data = {i: {"Track": "-", "Artist": "-", "Daily": 0} for i in [1, 2, 3]}
        for i in range(len(top_3)):
            row = top_3.iloc[i]
            p_data[i+1] = {"Track": row['Track'], "Artist": row['Artist'], "Daily": row['Daily']}

        podium_html = f"""
        <div class="podium-container">
            <div class="podium-block block-2">
                <div class="podium-rank rank-2">#2</div>
                <div class="podium-track">{p_data[2]['Track']}</div>
                <div class="podium-artist">{p_data[2]['Artist']}</div>
                <div class="podium-streams">{format_space(p_data[2]['Daily']) if p_data[2]['Daily'] > 0 else '-'}</div>
                <div class="podium-label">Streams / 24h</div>
            </div>
            <div class="podium-block block-1">
                <div class="podium-rank rank-1">#1</div>
                <div class="podium-track">{p_data[1]['Track']}</div>
                <div class="podium-artist">{p_data[1]['Artist']}</div>
                <div class="podium-streams">{format_space(p_data[1]['Daily']) if p_data[1]['Daily'] > 0 else '-'}</div>
                <div class="podium-label">Streams / 24h</div>
            </div>
            <div class="podium-block block-3">
                <div class="podium-rank rank-3">#3</div>
                <div class="podium-track">{p_data[3]['Track']}</div>
                <div class="podium-artist">{p_data[3]['Artist']}</div>
                <div class="podium-streams">{format_space(p_data[3]['Daily']) if p_data[3]['Daily'] > 0 else '-'}</div>
                <div class="podium-label">Streams / 24h</div>
            </div>
        </div>
        """
        st.markdown(podium_html, unsafe_allow_html=True)

        st.divider()
        col_g, col_d = st.columns([1.2, 0.8])
        with col_g:
            st.markdown("#### 🔥 Top 15 - Performance 24h")
            top_15 = df_filtered.sort_values('Daily', ascending=False).head(15)
            fig = px.bar(top_15, x='Daily', y='Track', color='Daily', orientation='h', template="plotly_dark", color_continuous_scale='Greens', text=top_15['Daily'].apply(format_space))
            fig.update_traces(hovertemplate="<b>%{y}</b><br>Streams : %{x:,}<extra></extra>")
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
        with col_d:
            with st.expander("🔍 Focus Parts Artistes", expanded=True):
                art_sums = df_filtered.groupby('Artist')['Streams'].sum().reset_index()
                fig_pie = px.pie(art_sums, values='Streams', names='Artist', hole=0.5, template="plotly_dark")
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()
        d_c1, d_c2 = st.columns([0.8, 0.2])
        d_c1.markdown("#### 📋 Détails des Productions")
        csv_data = df_filtered.to_csv(index=False).encode('utf-8')
        d_c2.download_button("📥 Export CSV", data=csv_data, file_name=f"stats_kworb_miixii_{datetime.now().strftime('%Y-%m-%d')}.csv")
        
        sort_choice = st.radio("Trier par :", ["Top Daily (24h)", "Top Streams (Total)"], horizontal=True)
        sort_col = 'Daily' if "Daily" in sort_choice else 'Streams'
        df_table = df_filtered.sort_values(sort_col, ascending=False).copy()
        df_table['Streams Totaux'] = df_table['Streams'].apply(format_space)
        df_table['Daily (24h)'] = df_table['Daily'].apply(format_space)
        st.dataframe(df_table[['Track', 'Artist', 'Streams Totaux', 'Daily (24h)']], use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("#### 🏆 Classement Top Artistes")
        art_stats = df_filtered.groupby('Artist').agg({'Streams': 'sum', 'Daily': 'sum', 'Track': 'count'}).reset_index().sort_values('Streams', ascending=False)
        art_stats.insert(0, 'Rang', [f"#{i+1}" for i in range(len(art_stats))])
        art_stats['Streams Totaux'] = art_stats['Streams'].apply(format_space)
        art_stats['Daily Global'] = art_stats['Daily'].apply(format_space)
        st.table(art_stats[['Rang', 'Artist', 'Streams Totaux', 'Daily Global', 'Track']].rename(columns={'Artist': 'Artiste', 'Track': 'Nb Titres'}))
    else:
        st.info("👈 Importe ton CSV pour commencer.")

with tab2:
    st.title("📈 Suivi de Progression")
    
    with st.expander("ℹ️ COMMENT UTILISER LE SUIVI ?", expanded=False):
        st.markdown("""
        Cet onglet vous permet de comparer vos chiffres entre deux dates différentes pour mesurer votre croissance.
        
        **Comment ça marche ?**
        1. **Soit** vous importez plusieurs fichiers CSV d'Exportify (un par date).
        2. **Soit** vous ré-importez un seul fichier "Archive" sauvegardé précédemment qui contient déjà votre historique.
        
        **Indicateurs clés :**
        * **Gain Global :** Nombre total de nouveaux streams gagnés sur la période.
        * **Vitesse de Croissance :** Moyenne quotidienne des streams gagnés.
        """)
    
    if 'history' in st.session_state and len(st.session_state['history']) > 1:
        hist_sorted = sorted(st.session_state['history'], key=lambda x: safe_parse_date(x['Date_Fetch'].iloc[0]))
        df_old, df_new = hist_sorted[0], hist_sorted[-1]
        try:
            d1 = safe_parse_date(df_old['Date_Fetch'].iloc[0])
            d2 = safe_parse_date(df_new['Date_Fetch'].iloc[0])
            days_diff = max((d2 - d1).days, 1)
            diff_total = df_new['Streams'].sum() - df_old['Streams'].sum()
            growth_per_day = diff_total / days_diff
            m1, m2, m3 = st.columns(3)
            m1.metric("Gain de Streams Global", format_space(diff_total), delta=f"+{format_space(diff_total)}", help="Croissance totale sur la période.")
            m2.metric("Période d'Analyse", f"{days_diff} Jours", f"Du {d1.strftime('%Y-%m-%d')} au {d2.strftime('%Y-%m-%d')}", delta_color="off", help="Intervalle entre le premier et dernier import.")
            m3.metric("Vitesse de Croissance", f"~{format_space(growth_per_day)}", "Streams / jour", help="Gain moyen quotidien.")
            st.divider()
            all_history_df = pd.concat(st.session_state['history'])
            csv_history = all_history_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="📦 Sauvegarder l'Historique Global", data=csv_history, file_name=f"archive_complete_{datetime.now().strftime('%Y-%m-%d')}.csv")
            st.divider()
            df_comp = df_new[['Track', 'Artist', 'Streams']].merge(df_old[['Track', 'Streams']], on='Track', suffixes=('_Nouveau', '_Ancien'))
            df_comp['Evolution'] = df_comp['Streams_Nouveau'] - df_comp['Streams_Ancien']
            top_grower = df_comp.sort_values('Evolution', ascending=False).iloc[0]
            art_growth = df_comp.groupby('Artist')['Evolution'].sum().sort_values(ascending=False)
            s1, s2 = st.columns(2)
            s1.metric("🏆 Meilleure progression (Titre)", top_grower['Track'], f"+{format_space(top_grower['Evolution'])} streams")
            s2.metric("👑 Artiste en croissance", art_growth.index[0], f"+{format_space(art_growth.iloc[0])} streams")
            st.divider()
            st.markdown("#### 📉 Courbe d'Évolution des Streams")
            all_artists = ["Global (Tous)"] + sorted(df_new['Artist'].unique().tolist())
            sel_curve = st.selectbox("Visualiser la courbe pour :", all_artists)
            curve_data = []
            for df in hist_sorted:
                date_obj = safe_parse_date(df['Date_Fetch'].iloc[0])
                sub_df = df if sel_curve == "Global (Tous)" else df[df['Artist'] == sel_curve]
                val = sub_df['Streams'].sum()
                top_song = sub_df.sort_values('Streams', ascending=False).iloc[0]['Track'] if not sub_df.empty else "N/A"
                curve_data.append({'Date': date_obj.strftime('%Y-%m-%d'), 'Total Streams': val, 'Top Song': top_song})
            df_curve = pd.DataFrame(curve_data)
            fig_line = px.line(df_curve, x='Date', y='Total Streams', markers=True, template="plotly_dark", color_discrete_sequence=['#1DB954'], custom_data=['Top Song'])
            fig_line.update_traces(line_width=3, marker_size=10, hovertemplate="<b>Date:</b> %{x}<br><b>Streams:</b> %{y:,}<br><b>🔝 Top:</b> %{customdata[0]}<extra></extra>")
            fig_line.update_layout(xaxis_title="Date", yaxis_title="Streams", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_line, use_container_width=True)
            st.divider()
            st.markdown(f"#### 🚀 Top 10 des Meilleures Progressions")
            fig_p = px.bar(df_comp.sort_values('Evolution', ascending=False).head(10), x='Evolution', y='Track', orientation='h', template="plotly_dark", color='Evolution', color_continuous_scale='Viridis', text=df_comp.sort_values('Evolution', ascending=False).head(10)['Evolution'].apply(format_space))
            fig_p.update_traces(hovertemplate="<b>%{y}</b><br>Gain : %{x:,}<extra></extra>")
            fig_p.update_layout(yaxis={'categoryorder':'total ascending'}, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_p, use_container_width=True)
            st.divider()
            st.markdown("#### 📁 HISTORIQUE DES IMPORTS")
            for i, df in enumerate(hist_sorted):
                d_str = safe_parse_date(df['Date_Fetch'].iloc[0]).strftime('%Y-%m-%d')
                st.write(f"📁 Import #{i+1} : **{d_str}** — {format_space(df['Streams'].sum())} streams total")
        except Exception as e:
            st.error(f"Erreur d'analyse : {e}")
    else:
        st.warning("Importez au moins deux fichiers CSV (ou une Archive contenant plusieurs dates) pour voir l'évolution.")