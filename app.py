import streamlit as st
import pandas as pd
import requests
from thefuzz import process, fuzz

# Pagina configuratie
st.set_page_config(page_title="NME Monitor 2026", layout="wide")

# --- CONFIGURATIE & URLS ---
URL_SCHOLEN = "https://jouw-api-url.com/scholen" # Vervang door de echte URL
URL_RESERVERINGEN = "https://jouw-api-url.com/reserveringen" # Vervang door de echte URL

st.title("🏫 NME Scholen & Limiet Controleur")

# --- STAP 1: DATA OPHALEN ---
@st.cache_data(ttl=3600)  # Cache de data voor 1 uur om snelheid te behouden
def fetch_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return pd.DataFrame(response.json())
    except Exception as e:
        st.error(f"Fout bij ophalen van {url}: {e}")
        return pd.DataFrame()

with st.spinner("Data ophalen van servers..."):
    df_scholen = fetch_data(URL_SCHOLEN)
    df_reserveringen = fetch_data(URL_RESERVERINGEN)

# --- STAP 2: DATA SAMENVOEGEN ---
if not df_scholen.empty and not df_reserveringen.empty:
    # We gaan ervan uit dat beide DF's een kolom 'school_id' of 'Schoolnaam' hebben
    # Hier voegen we de reserveringen (aantallen) toe aan de scholenlijst
    df_main = pd.merge(df_scholen, df_reserveringen, on="Schoolnaam", how="left")
    df_main['Aantal Groepen'] = df_main['Aantal Groepen'].fillna(0)
else:
    st.warning("Kon geen data combineren. Gebruik tijdelijke dummy data voor demo.")
    # Fallback naar dummy data als de URL's nog niet werken
    df_main = pd.DataFrame({
        'Schoolnaam': ['BS De Vlieger', 'Sint Jozefschool', 'OBS De Regenboog', 'De Klimop'],
        'Aantal Groepen': [22, 15, 28, 12]
    })

# --- STAP 3: ABONNEES LADEN (EXCEL) ---
st.sidebar.header("Abonnee Check")
uploaded_file = st.sidebar.file_uploader("Upload Excel met abonnees (Kolom: 'NAAM')", type=['xlsx'])

abo_scholen = []
if uploaded_file:
    try:
        df_excel = pd.read_excel(uploaded_file, engine='openpyxl')
        if 'NAAM' in df_excel.columns:
            abo_scholen = df_excel['NAAM'].dropna().astype(str).tolist()
            st.sidebar.success(f"✅ {len(abo_scholen)} abonnees herkend.")
        else:
            st.sidebar.error("Kolom 'NAAM' niet gevonden!")
    except Exception as e:
        st.sidebar.error(f"Excel fout: {e}")

# --- STAP 4: LIMIETEN BEPALEN (FUZZY) ---
def bepaal_limiet(schoolnaam):
    if not abo_scholen:
        return 20 # Standaard limiet
    
    # Zoek beste match
    match, score = process.extractOne(schoolnaam, abo_scholen, scorer=fuzz.token_sort_ratio)
    
    if score >= 85:
        return float('inf')
    return 20

df_main['Limiet'] = df_main['Schoolnaam'].apply(bepaal_limiet)

# --- STAP 5: STYLING & WEERGAVE ---
def color_rule(row):
    styles = [''] * len(row)
    # Rood: meer groepen dan limiet
    if row['Aantal Groepen'] > row['Limiet']:
        styles = ['background-color: #ffcccc'] * len(row)
    # Oranje: meer dan 20 groepen, maar wel abonnee (limiet is inf)
    elif row['Aantal Groepen'] > 20 and row['Limiet'] == float('inf'):
        styles = ['background-color: #ffe5cc'] * len(row)
    return styles

# Maak een kopie voor de weergave (inf -> ∞)
display_df = df_main.copy()
display_df['Limiet Status'] = display_df['Limiet'].apply(lambda x: "∞ (Abonnee)" if x == float('inf') else "20 (Standaard)")

# Toon de tabel
st.subheader("Overzicht Scholen en Reserveringen")
styled_df = display_df.style.apply(color_rule, axis=1)

st.dataframe(
    styled_df,
    column_order=("Schoolnaam", "Aantal Groepen", "Limiet Status"),
    width="stretch",
    hide_index=True
)

# Download sectie
csv = df_main.to_csv(index=False).encode('utf-8')
st.download_button("Download Data (CSV)", csv, "nme_export.csv", "text/csv")
