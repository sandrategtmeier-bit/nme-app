import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

st.set_page_config(page_title="NME Monitor PO", layout="wide")

# Exacte namespaces
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
    
    for s in root_s.findall('.//ns1:school', NAMESPACES):
        naam = s.find('ns1:schoolnaam', NAMESPACES)
        stype = s.find('ns1:schooltype', NAMESPACES)
        groepen = s.find('ns1:aantalingevoerdegroepen', NAMESPACES)
        
        if naam is not None and stype is not None and stype.text.lower() == 'po':
            originele_naam = naam.text.strip()
            scholen_data.append({
                'Schoolnaam': originele_naam,
                'MatchNaam': originele_naam.lower(), # Voor de koppeling
                'Ingevoerde groepen': int(groepen.text) if (groepen is not None and groepen.text) else 0
            })
    df_base = pd.DataFrame(scholen_data)

    # --- 2. ROOSTERS OPHALEN ---
    r_r = requests.get(URL_ROOSTERS)
    root_r = ET.fromstring(r_r.content)
    rooster_lijst = []
    
    for item in root_r.findall('.//ns1:item', NAMESPACES):
        s_naam = item.find('ns1:schoolnaam', NAMESPACES)
        s_type_act = item.find('ns1:type', NAMESPACES)
        
        if s_naam is not None and s_type_act is not None:
            if s_type_act.text in ['Gastles', 'Excursie']:
                rooster_lijst.append(s_naam.text.strip().lower())
    
    # Tellen op de 'MatchNaam'
    df_counts = pd.DataFrame(rooster_lijst, columns=['MatchNaam']).value_counts().reset_index()
    df_counts.columns = ['MatchNaam', 'Reserveringen']

    # --- 3. SAMENVOEGEN ---
    if not df_base.empty:
        # Koppelen op de opgeschoonde MatchNaam
        final = pd.merge(df_base, df_counts, on='MatchNaam', how='left').fillna(0)
        final['Reserveringen'] = final['Reserveringen'].astype(int)
        final['Limiet'] = final['Ingevoerde groepen'] * 2
        # Verwijder de hulpkolom voor weergave
        return final.drop(columns=['MatchNaam']), rooster_lijst
    
    return pd.DataFrame(), []

# --- DASHBOARD ---
st.title("📊 NME Monitor: PO Scholen")

df, ruwe_namen_rooster = laad_data()

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
    
    # Tabel
    st.dataframe(df_disp.sort_values(by='Reserveringen', ascending=False), use_container_width=True, hide_index=True)

    # --- DIAGNOSE SECTIE (Inklapbaar) ---
    with st.expander("Klik hier als je 0 ziet (Diagnose)"):
        st.write("Aantal gevonden namen in Roosters-XML:", len(ruwe_namen_rooster))
        if len(ruwe_namen_rooster) > 0:
            st.write("Eerste 5 namen uit Roosters-XML:", ruwe_namen_rooster[:5])
            
            # Check welke namen uit Roosters NIET in de Scholenlijst staan
            set_scholen = set(df['Schoolnaam'].str.lower())
            missing = [n for n in set(ruwe_namen_rooster) if n not in set_scholen]
            if missing:
                st.warning(f"Er zijn {len(missing)} schoolnamen in de roosters die niet exact overeenkomen met de scholenlijst.")
                st.write("Voorbeelden van namen die niet matchen:", missing[:10])
else:
    st.error("Geen PO scholen gevonden in de Scholen-XML.")
