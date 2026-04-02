import streamlit as st
import pandas as pd
import requests
import io
from thefuzz import process, fuzz

st.set_page_config(page_title="NME Monitor PO", layout="wide")

# --- CONFIGURATIE ---
URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=300)
def fetch_data():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r_s = requests.get(URL_SCHOLEN, headers=headers)
        r_r = requests.get(URL_ROOSTERS, headers=headers)
        df_s = pd.read_xml(io.BytesIO(r_s.content), parser='lxml')
        df_r = pd.read_xml(io.BytesIO(r_r.content), parser='lxml')
        return df_s, df_r
    except Exception as e:
        st.error(f"Fout bij laden van XML data: {e}")
        return pd.DataFrame(), pd.DataFrame()

st.title("🏫 NME Monitor: Primair Onderwijs")

df_scholen_raw, df_roosters_raw = fetch_data()

if not df_scholen_raw.empty and not df_roosters_raw.empty:
    # Kolomnamen normaliseren
    df_roosters = df_roosters_raw.copy()
    df_scholen = df_scholen_raw.copy()
    df_roosters.columns = [c.lower() for c in df_roosters.columns]
    df_scholen.columns = [c.lower() for c in df_scholen.columns]

    # --- 1. FILTER OP SCHOOLTYPE PO ---
    if 'schooltype' in df_scholen.columns:
        df_scholen = df_scholen[df_scholen['schooltype'].str.lower() == 'po']
    
    # --- 2. SCHOLEN DATA (Basis) ---
    df_basis = df_scholen[['schoolnaam', 'aantalingevoerdegroepen']].copy()
    df_basis['aantalingevoerdegroepen'] = df_basis['aantalingevoerdegroepen'].fillna(0).astype(int)
    df_basis = df_basis.rename(columns={'aantalingevoerdegroepen': 'Groepen'})
    df_basis['Limiet_Num'] = df_basis['Groepen'] * 2

    # --- 3. ROOSTER DATA (Verbruik) ---
    type_col = next((c for c in df_roosters.columns if 'type' in c), None)
    if type_col:
        mask = df_roosters[type_col].str.contains('Gastles|Excursie', case=False, na=False)
        df_filtered = df_roosters[mask]
    else:
        df_filtered = df_roosters

    res_count = df_filtered.groupby('schoolnaam').size().reset_index(name='Reserveringen')

    # --- 4. SAMENVOEGEN ---
    df_final = pd.merge(df_basis, res_count, on='schoolnaam', how='left')
    df_final['Reserveringen'] = df_final['Reserveringen'].fillna(0).astype(int)

    # --- 5. EXCEL UPLOAD & ABONNEMENTEN ---
    st.sidebar.header("1. Abonnementen")
    upload = st.sidebar.file_uploader("Upload Excel", type=['xlsx'])
    
    onbeperkt_scholen = []
    if upload:
        df_excel = pd.read_excel(upload)
        col_name = [c for c in df_excel.columns if 'naam' in c.lower()][0]
        onbeperkt_scholen = df_excel[col_name].astype(str).tolist()

    def check_onbeperkt(schoolnaam):
        if not onbeperkt_scholen: return False
        match = process.extractOne(schoolnaam, onbeperkt_scholen, scorer=fuzz.token_sort_ratio)
        return match and match[1] >= 85

    df_final['is_onbeperkt'] = df_final['schoolnaam'].apply(check_onbeperkt)
    df_final['Limiet'] = df_final.apply(
        lambda x: "∞" if x['is_onbeperkt'] else str(int(x['Limiet_Num'])), axis=1
    )

    # --- 6. FILTERS (Knoppen/Checkboxes) ---
    st.sidebar.header("2. Filters")
    filter_oranje = st.sidebar.checkbox("Laat alleen zien: Veel groepen (> 20)")
    filter_rood = st.sidebar.checkbox("Laat alleen zien: Over limiet")

    # Toepassen van filters op de dataframe
    if filter_oranje:
        df_final = df_final[df_final['Groepen'] > 20]
    
    if filter_rood:
        # Alleen scholen die niet onbeperkt zijn EN over hun limiet gaan
        df_final = df_final[(df_final['is_onbeperkt'] == False) & (df_final['Reserveringen'] > df_final['Limiet_Num'])]

    # --- 7. STYLING ---
    def style_monitor(row):
        # ROOD: Reserveringen > Numerieke Limiet (behalve onbeperkt)
        if not row['is_onbeperkt'] and row['Reserveringen'] > row['Limiet_Num']:
            return ['background-color: #ffcccc'] * len(row)
        # ORANJE: Groepen > 20
        if row['Groepen'] > 20:
            return ['background-color: #ffe5cc'] * len(row)
        return [''] * len(row)

    # --- 8. TABEL TONEN ---
    st.subheader(f"Overzicht Analyse ({len(df_final)} scholen getoond)")
    
    # Volgorde aanpassen: Schoolnaam - Groepen - Reserveringen - Limiet
    show_cols = ['schoolnaam', 'Groepen', 'Reserveringen', 'Limiet']
    
    st.dataframe(
        df_final[show_cols + ['is_onbeperkt', 'Limiet_Num']].style.apply(style_monitor, axis=1),
        column_config={
            "schoolnaam": "Schoolnaam",
            "Groepen": st.column_config.NumberColumn("Groepen", format="%d"),
            "Reserveringen": st.column_config.NumberColumn("Reserveringen", format="%d"),
            "Limiet": "Limiet",
            "is_onbeperkt": None, 
            "Limiet_Num": None    
        },
        hide_index=True,
        use_container_width=True
    )

    # Export knop
    csv = df_final[show_cols].to_csv(index=False).encode('utf-8')
    st.download_button("Download Selectie", csv, "nme_export.csv", "text/csv")

else:
    st.info("De data wordt opgehaald. Upload een Excel-bestand om de abonnementen-check te activeren.")
