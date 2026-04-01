import io
import streamlit as st
import pandas as pd
import requests  # Cruciaal: dit voorkomt de 'not defined' fout
from thefuzz import process, fuzz

# Pagina configuratie
st.set_page_config(page_title="NME Monitor 2026", layout="wide")

# --- CONFIGURATIE & URLS ---
NAMESPACES = {
    'ns1': 'https://www.nmegids.nl/algemeen/interface/xml',
    'xsi': 'https://www.w3.org/2001/XMLSchema-instance'
}

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

st.title("🏫 NME Scholen & Limiet Controleur")

# --- STAP 1: DATA OPHALEN UIT XML MET HEADERS ---
import io # Voeg deze import bovenaan toe!

@st.cache_data(ttl=300)
def fetch_nme_data():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        resp_s = requests.get(URL_SCHOLEN, headers=headers)
        resp_r = requests.get(URL_ROOSTERS, headers=headers)
        
        resp_s.raise_for_status()
        resp_r.raise_for_status()

        # FIX: We gebruiken io.BytesIO om de bytes om te zetten naar een 'file-like object'
        # Dit is wat pd.read_xml verwacht.
        df_s = pd.read_xml(io.BytesIO(resp_s.content), namespaces=NAMESPACES)
        df_r = pd.read_xml(io.BytesIO(resp_r.content), namespaces=NAMESPACES)
        
        return df_s, df_r
    except Exception as e:
        st.error(f"Fout bij verwerken XML: {e}")
        return pd.DataFrame(), pd.DataFrame()

with st.spinner("Data ophalen uit NME-gids..."):
    df_scholen, df_roosters = fetch_nme_data()

# --- STAP 2: DATA VERWERKEN ---
if not df_scholen.empty and not df_roosters.empty:
    # Groepeer reserveringen per school
    # We gaan uit van kolommen 'SCHOOL' in de rooster-XML en 'NAAM' in de scholen-XML
    res_count = df_roosters.groupby('SCHOOL').size().reset_index(name='Aantal Groepen')
    
    df_main = pd.merge(df_scholen[['NAAM']], res_count, left_on='NAAM', right_on='SCHOOL', how='left')
    df_main['Aantal Groepen'] = df_main['Aantal Groepen'].fillna(0).astype(int)
    df_main = df_main.rename(columns={'NAAM': 'Schoolnaam'}).drop(columns=['SCHOOL'])
else:
    st.error("Kon geen data laden van NME-gids. Controleer of de URL's nog kloppen.")
    st.stop()

# --- STAP 3: ABONNEES LADEN (EXCEL) ---
st.sidebar.header("Abonnee Check")
uploaded_file = st.sidebar.file_uploader("Upload Excel met abonnees (Kolom: 'NAAM')", type=['xlsx'])

abo_scholen = []
if uploaded_file:
    try:
        df_excel = pd.read_excel(uploaded_file, engine='openpyxl')
        if 'NAAM' in df_excel.columns:
            abo_scholen = df_excel['NAAM'].dropna().astype(str).tolist()
            st.sidebar.success(f"✅ {len(abo_scholen)} abonnees geladen.")
        else:
            st.sidebar.error("Kolom 'NAAM' niet gevonden in Excel!")
    except Exception as e:
        st.sidebar.error(f"Fout bij lezen Excel: {e}")

# --- STAP 4: LIMIETEN & FUZZY MATCHING ---
def bepaal_limiet(schoolnaam):
    if not abo_scholen:
        return 20
    
    # Zoek beste match (minimaal 85% overeenkomst)
    match, score = process.extractOne(schoolnaam, abo_scholen, scorer=fuzz.token_sort_ratio)
    
    if score >= 85:
        return float('inf')
    return 20

df_main['Limiet'] = df_main['Schoolnaam'].apply(bepaal_limiet)

# --- STAP 5: STYLING ---
def color_rule(row):
    styles = [''] * len(row)
    if row['Aantal Groepen'] > row['Limiet']:
        return ['background-color: #ffcccc'] * len(row) # Rood
    elif row['Aantal Groepen'] > 20 and row['Limiet'] == float('inf'):
        return ['background-color: #ffe5cc'] * len(row) # Oranje
    return styles

display_df = df_main.copy()
display_df['Limiet Status'] = display_df['Limiet'].apply(
    lambda x: "∞ (Abonnee)" if x == float('inf') else "20"
)

# --- STAP 6: OUTPUT ---
st.subheader("Resultaten Analyse")
styled_df = display_df.style.apply(color_rule, axis=1)

st.dataframe(
    styled_df,
    column_order=("Schoolnaam", "Aantal Groepen", "Limiet Status"),
    width="stretch",
    hide_index=True
)

# Download knop
csv = df_main.to_csv(index=False).encode('utf-8')
st.download_button("Download CSV Export", csv, "nme_check.csv", "text/csv")
