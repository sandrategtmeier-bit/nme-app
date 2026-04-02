import streamlit as st
import pandas as pd
import requests
import io
from thefuzz import process, fuzz

st.set_page_config(page_title="NME Monitor Pro", layout="wide")

# --- CONFIGURATIE ---
URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=300)
def fetch_data():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r_s = requests.get(URL_SCHOLEN, headers=headers)
        r_r = requests.get(URL_ROOSTERS, headers=headers)
        # Gebruik lxml voor robuuste XML parsing
        df_s = pd.read_xml(io.BytesIO(r_s.content), parser='lxml')
        df_r = pd.read_xml(io.BytesIO(r_r.content), parser='lxml')
        return df_s, df_r
    except Exception as e:
        st.error(f"Fout bij laden van XML data: {e}")
        return pd.DataFrame(), pd.DataFrame()

st.title("🏫 NME Scholen & Limiet Controleur")

df_scholen_raw, df_roosters_raw = fetch_data()

if not df_scholen_raw.empty and not df_roosters_raw.empty:
    # Kolomnamen normaliseren (kleine letters)
    df_roosters = df_roosters_raw.copy()
    df_scholen = df_scholen_raw.copy()
    df_roosters.columns = [c.lower() for c in df_roosters.columns]
    df_scholen.columns = [c.lower() for c in df_scholen.columns]

    # --- 1. SCHOLEN DATA (Basis) ---
    # We pakken de schoolnaam, het aantal groepen en berekenen het limiet
    # 'aantalingevoerdegroepen' komt uit de scholen-XML
    df_basis = df_scholen[['schoolnaam', 'aantalingevoerdegroepen']].copy()
    df_basis = df_basis.rename(columns={'aantalingevoerdegroepen': 'Groepen'})
    df_basis['Limiet'] = df_basis['Groepen'] * 2

    # --- 2. ROOSTER DATA (Verbruik) ---
    # Filter op Gastles en Excursie
    type_col = next((c for c in df_roosters.columns if 'type' in c), None)
    if type_col:
        mask = df_roosters[type_col].str.contains('Gastles|Excursie', case=False, na=False)
        df_filtered = df_roosters[mask]
    else:
        df_filtered = df_roosters

    # Tell het aantal reserveringen (uidreservering / rijen) per school
    res_count = df_filtered.groupby('schoolnaam').size().reset_index(name='Reserveringen')

    # --- 3. SAMENVOEGEN ---
    df_final = pd.merge(df_basis, res_count, on='schoolnaam', how='left')
    df_final['Reserveringen'] = df_final['Reserveringen'].fillna(0).astype(int)

    # --- 4. EXCEL UPLOAD (Onbeperkt Limiet) ---
    st.sidebar.header("Instellingen")
    upload = st.sidebar.file_uploader("Upload Excel (Scholen met onbeperkt limiet)", type=['xlsx'])
    onbeperkt_scholen = []
    if upload:
        df_excel = pd.read_excel(upload)
        col_name = [c for c in df_excel.columns if 'naam' in c.lower()][0]
        onbeperkt_scholen = df_excel[col_name].astype(str).tolist()

    # --- 5. STYLING & CONTROLE ---
    def style_monitor(row):
        # Fuzzy match voor onbeperkt limiet
        is_onbeperkt = False
        if onbeperkt_scholen:
            match = process.extractOne(row['schoolnaam'], onbeperkt_scholen, scorer=fuzz.token_sort_ratio)
            if match and match[1] >= 85:
                is_onbeperkt = True

        # Logica:
        # ROOD: Reserveringen > Limiet (tenzij onbeperkt)
        if not is_onbeperkt and row['Reserveringen'] > row['Limiet']:
            return ['background-color: #ffcccc'] * len(row)
        
        # ORANJE: Groepen > 20
        if row['Groepen'] > 20:
            return ['background-color: #ffe5cc'] * len(row)
            
        return [''] * len(row)

    # Resultaten tonen
    st.subheader("Analyseoverzicht")
    st.write("_Rood: Reserveringen > Limiet | Oranje: Meer dan 20 groepen_")
    
    st.dataframe(
        df_final.style.apply(style_monitor, axis=1),
        column_config={
            "schoolnaam": "Schoolnaam",
            "Groepen": "Groepen (Basis)",
            "Limiet": "Limiet (Groepen * 2)",
            "Reserveringen": "Reserveringen (Gebruik)"
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Export
    csv = df_final.to_csv(index=False).encode('utf-8')
    st.download_button("Download Resultaten", csv, "nme_monitor_export.csv", "text/csv")

else:
    st.warning("Kon geen verbinding maken met de XML-feeds of de feeds zijn leeg.")
