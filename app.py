import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

st.set_page_config(page_title="NME Dashboard PO", layout="wide")

# Exacte namespaces uit jouw bron
NAMESPACES = {
    'ns1': 'https://www.nmegids.nl/algemeen/interface/xml',
    'xsi': 'https://www.w3.org/2001/XMLSchema-instance'
}

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=600)
def laad_data():
    # 1. Scholen ophalen (Basislijst: alleen PO)
    try:
        r_scholen = requests.get(URL_SCHOLEN)
        root_s = ET.fromstring(r_scholen.content)
        
        scholen_data = []
        for school_node in root_s.findall('.//ns1:school', NAMESPACES):
            naam = school_node.find('ns1:schoolnaam', NAMESPACES)
            stype = school_node.find('ns1:schooltype', NAMESPACES)
            groepen = school_node.find('ns1:aantalingevoerdegroepen', NAMESPACES)
            
            # Filter: Alleen PO scholen
            if naam is not None and stype is not None and stype.text.lower() == 'po':
                scholen_data.append({
                    'Schoolnaam': naam.text,
                    'Ingevoerde groepen': int(groepen.text) if (groepen is not None and groepen.text) else 0
                })
        df_scholen = pd.DataFrame(scholen_data)
    except:
        df_scholen = pd.DataFrame(columns=['Schoolnaam', 'Ingevoerde groepen'])

    # 2. Roosters ophalen (Specifiek uidreservering tellen)
    try:
        r_roosters = requests.get(URL_ROOSTERS)
        root_r = ET.fromstring(r_roosters.content)
        
        rooster_records = []
        for item in root_r.findall('.//ns1:item', NAMESPACES):
            school_r = item.find('ns1:schoolnaam', NAMESPACES)
            type_act = item.find('ns1:type', NAMESPACES)
            uid_res = item.find('ns1:uidreservering', NAMESPACES)
            
            # Alleen data verzamelen als alle velden bestaan en type klopt
            if school_r is not None and type_act is not None and uid_res is not None:
                if type_act.text in ['Gastles', 'Excursie']:
                    rooster_records.append({
                        'Schoolnaam': school_r.text,
                        'uidreservering': uid_res.text
                    })
        
        df_rooster_raw = pd.DataFrame(rooster_records)
        
        # Tel het aantal UNIEKE uidreserveringen per schoolnaam
        if not df_rooster_raw.empty:
            df_counts = df_rooster_raw.groupby('Schoolnaam')['uidreservering'].nunique().reset_index()
            df_counts.columns = ['Schoolnaam', 'Aantal Reserveringen']
        else:
            df_counts = pd.DataFrame(columns=['Schoolnaam', 'Aantal Reserveringen'])
    except:
        df_counts = pd.DataFrame(columns=['Schoolnaam', 'Aantal Reserveringen'])

    # 3. Samenvoegen
    if not df_scholen.empty:
        final = pd.merge(df_scholen, df_counts, on='Schoolnaam', how='left').fillna(0)
        final['Aantal Reserveringen'] = final['Aantal Reserveringen'].astype(int)
        final['Limiet'] = final['Ingevoerde groepen'] * 2
        return final
    return pd.DataFrame()

# --- Dashboard Layout ---
st.title("🏫 PO Scholen: Reserveringen vs Groepen")
st.caption("Telling op basis van unieke uidreservering voor Gastlessen en Excursies.")

data = laad_data()

if not data.empty:
    # Sidebar Filters
    st.sidebar.header("Filter Instellingen")
    f_limiet = st.sidebar.checkbox("Aantal Reserveringen > Limiet (2x groepen)")
    f_groepen = st.sidebar.checkbox("Ingevoerde groepen > 20")

    # Filter acties
    df_disp = data.copy()
    if f_limiet:
        df_disp = df_disp[df_disp['Aantal Reserveringen'] > df_disp['Limiet']]
    if f_groepen:
        df_disp = df_disp[df_disp['Ingevoerde groepen'] > 20]

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Aantal PO Scholen", len(df_disp))
    c2.metric("Totaal unieke reserveringen", df_disp['Aantal Reserveringen'].sum())
    c3.metric("Totaal groepen", df_disp['Ingevoerde groepen'].sum())

    # Tabelweergave
    st.dataframe(
        df_disp.sort_values(by=['Aantal Reserveringen', 'Ingevoerde groepen'], ascending=[False, False]),
        use_container_width=True,
        hide_index=True
    )
    
    # Export
    csv = df_disp.to_csv(index=False).encode('utf-8')
    st.download_button("Download Selectie (CSV)", csv, "nme_analyse_export.csv", "text/csv")
else:
    st.error("Kon geen data verwerken. Controleer of de XML bronnen bereikbaar zijn.")
