import streamlit as st
import pandas as pd
import requests
import io
from thefuzz import process, fuzz

# Instellingen
st.set_page_config(page_title="NME Monitor", layout="wide")

# Gebruik de exacte tag die je aangaf: 'schoolnaam'
# We proberen zowel hoofdletters als kleine letters voor de zekerheid
XML_TAG = 'schoolnaam' 

@st.cache_data(ttl=300)
def fetch_nme_data():
    headers = {'User-Agent': 'Mozilla/5.0'}
    urls = {
        'scholen': "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe",
        'roosters': "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
    }
    
    try:
        # Haal data op
        r_s = requests.get(urls['scholen'], headers=headers)
        r_r = requests.get(urls['roosters'], headers=headers)
        
        # Zet om naar DataFrame
        # We laten pandas zelf de structuur zoeken, maar forceren lxml
        df_s = pd.read_xml(io.BytesIO(r_s.content), parser='lxml')
        df_r = pd.read_xml(io.BytesIO(r_r.content), parser='lxml')
        
        return df_s, df_r
    except Exception as e:
        st.error(f"Fout bij inlezen: {e}")
        return pd.DataFrame(), pd.DataFrame()

st.title("🏫 NME Monitor 2026")

df_scholen, df_roosters = fetch_nme_data()

if not df_scholen.empty and not df_roosters.empty:
    # --- DATA OPSCHONEN ---
    # We zoeken de kolom 'schoolnaam' (ongeacht hoofdletters)
    df_roosters.columns = [c.lower() for c in df_roosters.columns]
    df_scholen.columns = [c.lower() for c in df_scholen.columns]

    if 'schoolnaam' in df_roosters.columns:
        # Tell ritten per school
        res_count = df_roosters.groupby('schoolnaam').size().reset_index(name='ritten')
        
        # Merge met de hoofdenlijst van scholen
        df_final = pd.merge(df_scholen[['schoolnaam']], res_count, on='schoolnaam', how='left')
        df_final['ritten'] = df_final['ritten'].fillna(0).astype(int)
        
        # --- ABONNEE CHECK (Zijbalk) ---
        st.sidebar.header("Abonnementen")
        upload = st.sidebar.file_uploader("Upload Excel met abonnees", type=['xlsx'])
        
        abonnees = []
        if upload:
            df_abo = pd.read_excel(upload)
            # Zoek kolom die lijkt op naam
            abo_col = [c for c in df_abo.columns if 'naam' in c.lower()][0]
            abonnees = df_abo[abo_col].astype(str).tolist()

        # --- STYLING FUNCTIE ---
        def style_rows(row):
            # Standaard limiet
            limiet = 20
            is_abo = False
            
            if abonnees:
                match, score = process.extractOne(row['schoolnaam'], abonnees, scorer=fuzz.token_sort_ratio)
                if score >= 85:
                    is_abo = True
                    limiet = 999 # Geen limiet voor abonnees

            # Kleur bepalen
            if row['ritten'] > limiet:
                return ['background-color: #ffcccc'] * 2 # Rood: over de 20 (niet-abo)
            if is_abo and row['ritten'] > 20:
                return ['background-color: #ffe5cc'] * 2 # Oranje: abo boven de 20
            return [''] * 2

        # Toon Tabel
        st.subheader("Overzicht per school")
        st.dataframe(
            df_final.style.apply(style_rows, axis=1),
            column_config={
                "schoolnaam": "School",
                "ritten": "Aantal Groepen"
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.error(f"Kolom 'schoolnaam' niet gevonden. Beschikbaar: {list(df_roosters.columns)}")
else:
    st.info("App is verbonden. Upload de abonnee-lijst in de zijbalk om de controle te starten.")
