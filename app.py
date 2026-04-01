import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

# Pagina instellingen
st.set_page_config(page_title="NME Monitor PO", layout="wide")

# Exacte namespaces uit jouw bronvermelding
NAMESPACES = {
    'ns1': 'https://www.nmegids.nl/algemeen/interface/xml',
    'xsi': 'https://www.w3.org/2001/XMLSchema-instance'
}

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=300)
def laad_data():
    # --- 1. SCHOLEN OPHALEN (Basislijst: Alleen PO) ---
    try:
        r_s = requests.get(URL_SCHOLEN)
        root_s = ET.fromstring(r_s.content)
        
        scholen_data = []
        for s in root_s.findall('.//ns1:school', NAMESPACES):
            naam = s.find('ns1:schoolnaam', NAMESPACES)
            stype = s.find('ns1:schooltype', NAMESPACES)
            groepen = s.find('ns1:aantalingevoerdegroepen', NAMESPACES)
            
            # Filter op PO
            if naam is not None and stype is not None and stype.text.lower() == 'po':
                scholen_data.append({
                    'Schoolnaam': naam.text.strip(),
                    'Ingevoerde groepen': int(groepen.text) if (groepen is not None and groepen.text) else 0
                })
        df_base = pd.DataFrame(scholen_data)
    except Exception as e:
        st.error(f"Fout bij scholen-XML: {e}")
        return pd.DataFrame()

    # --- 2. ROOSTERS OPHALEN (Tellen van alle regels/reserveringen) ---
    try:
        r_r = requests.get(URL_ROOSTERS)
        root_r = ET.fromstring(r_r.content)
        
        rooster_lijst = []
        for item in root_r.findall('.//ns1:item', NAMESPACES):
            s_naam = item.find('ns1:schoolnaam', NAMESPACES)
            s_type_act = item.find('ns1:type', NAMESPACES)
            
            if s_naam is not None and s_type_act is not None:
                # Alleen Gastles en Excursie
                if s_type_act.text in ['Gastles', 'Excursie']:
                    rooster_lijst.append(s_naam.text.strip())
        
        # Tel alle voorkomens per school (inclusief dubbele uids)
        df_counts = pd.DataFrame(rooster_lijst, columns=['Schoolnaam']).value_counts().reset_index()
        df_counts.columns = ['Schoolnaam', 'Reserveringen']
            
    except Exception as e:
        st.error(f"Fout bij rooster-XML: {e}")
        df_counts = pd.DataFrame(columns=['Schoolnaam', 'Reserveringen'])

    # --- 3. SAMENVOEGEN ---
    if not df_base.empty:
        # Koppel telling aan de PO-lijst
        final = pd.merge(df_base, df_counts, on='Schoolnaam', how='left').fillna(0)
        final['Reserveringen'] = final['Reserveringen'].astype(int)
        # Bereken limiet: 2 x aantal groepen
        final['Limiet'] = final['Ingevoerde groepen'] * 2
        return final
    
    return pd.DataFrame()

# --- DASHBOARD ---
st.title("📊 NME Dashboard: PO Scholen")
st.info("Dit dashboard toont alle PO scholen en telt het totaal aantal reserveringsregels (Gastles & Excursie).")

df = laad_data()

if not df.empty:
    # Filters in de sidebar
    st.sidebar.header("Filteren")
    f_limiet = st.sidebar.checkbox("Reserveringen > Limiet")
    f_groepen = st.sidebar.checkbox("Ingevoerde groepen > 20")

    # Filter logica
    df_disp = df.copy()
    if f_limiet:
        df_disp = df_disp[df_disp['Reserveringen'] > df_disp['Limiet']]
    if f_groepen:
        df_disp = df_disp[df_disp['Ingevoerde groepen'] > 20]

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Aantal Scholen", len(df_disp))
    c2.metric("Totaal Reserveringen", df_disp['Reserveringen'].sum())
    c3.metric("Totaal Groepen", df_disp['Ingevoerde groepen'].sum())

    # Tabel tonen
    st.dataframe(
        df_disp.sort_values(by='Reserveringen', ascending=False),
        use_container_width=True,
        hide_index=True
    )
    
    # Download knop
    csv = df_disp.to_csv(index=False).encode('utf-8')
    st.download_button("Download Selectie (CSV)", csv, "nme_analyse.csv", "text/csv")
else:
    st.warning("Geen data gevonden. Controleer de verbinding.")
