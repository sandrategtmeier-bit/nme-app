import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

st.set_page_config(page_title="NME Monitor PO", layout="wide")

# Exacte namespaces van NMEgids
NAMESPACES = {
    'ns1': 'https://www.nmegids.nl/algemeen/interface/xml',
    'xsi': 'https://www.w3.org/2001/XMLSchema-instance'
}

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=300)
def laad_data():
    # --- 1. SCHOLEN OPHALEN ---
    r_s = requests.get(URL_SCHOLEN)
    root_s = ET.fromstring(r_s.content)
    scholen_data = []
    
    # We zoeken alle elementen die een schoolnaam hebben
    for s in root_s.findall('.//*', NAMESPACES):
        naam = s.find('ns1:schoolnaam', NAMESPACES)
        stype = s.find('ns1:schooltype', NAMESPACES)
        groepen = s.find('ns1:aantalingevoerdegroepen', NAMESPACES)
        
        if naam is not None and stype is not None:
            if stype.text and stype.text.lower() == 'po':
                scholen_data.append({
                    'Schoolnaam': naam.text.strip(),
                    'MatchNaam': naam.text.strip().lower(),
                    'Ingevoerde groepen': int(groepen.text) if (groepen is not None and groepen.text) else 0
                })
    
    df_base = pd.DataFrame(scholen_data).drop_duplicates(subset=['Schoolnaam'])

    # --- 2. ROOSTERS OPHALEN (Universele zoekmethode) ---
    r_r = requests.get(URL_ROOSTERS)
    root_r = ET.fromstring(r_r.content)
    rooster_lijst = []
    
    # We lopen door ALLE elementen in de XML
    for elem in root_r.iter():
        # Verwijder de namespace-prefix uit de tagnaam voor makkelijke check
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        # Als we een 'item' of 'rooster' achtig element vinden, check de inhoud
        s_naam = elem.find('ns1:schoolnaam', NAMESPACES)
        s_type_act = elem.find('ns1:type', NAMESPACES)
        
        if s_naam is not None and s_type_act is not None:
            if s_type_act.text in ['Gastles', 'Excursie']:
                rooster_lijst.append(s_naam.text.strip().lower())
    
    df_counts = pd.DataFrame(rooster_lijst, columns=['MatchNaam']).value_counts().reset_index()
    df_counts.columns = ['MatchNaam', 'Reserveringen']

    # --- 3. SAMENVOEGEN ---
    if not df_base.empty:
        final = pd.merge(df_base, df_counts, on='MatchNaam', how='left').fillna(0)
        final['Reserveringen'] = final['Reserveringen'].astype(int)
        final['Limiet'] = final['Ingevoerde groepen'] * 2
        return final.drop(columns=['MatchNaam']), rooster_lijst
    
    return pd.DataFrame(), []

# --- DASHBOARD ---
st.title("📊 NME Monitor: PO Scholen")

df, debug_rooster = laad_data()

if not df.empty:
    # Filters
    st.sidebar.header("Filteren")
    f_limiet = st.sidebar.checkbox("Reserveringen > Limiet")
    f_groepen = st.sidebar.checkbox("Ingevoerde groepen > 20")

    df_disp = df.copy()
    if f_limiet:
        df_disp = df_disp[df_disp['Reserveringen'] > df_disp['Limiet']]
    if f_groepen:
        df_disp = df_disp[df_disp['Ingevoerde groepen'] > 20]

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Aantal PO Scholen", len(df_disp))
    c2.metric("Totaal Reserveringen", df_disp['Reserveringen'].sum())
    c3.metric("Data regels in Rooster XML", len(debug_rooster))
    
    # Tabel
    st.dataframe(df_disp.sort_values(by='Reserveringen', ascending=False), use_container_width=True, hide_index=True)

    if len(debug_rooster) == 0:
        st.error("⚠️ De app kan de reserveringen niet vinden in de XML. Dit komt waarschijnlijk omdat de tags anders heten dan 'schoolnaam' of 'type' in de Rooster-link.")
else:
    st.error("Geen PO scholen gevonden. Controleer de Scholen-XML link.")
