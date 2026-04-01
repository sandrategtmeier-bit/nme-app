import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

# Pagina instellingen
st.set_page_config(page_title="NME Dashboard", layout="wide")

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=600)
def fetch_data():
    # Namespace definitie
    ns = {'ns1': 'http://www.w3.org/2001/XMLSchema-instance'}
    
    # 1. Roosters ophalen (Reserveringen)
    r_roosters = requests.get(URL_ROOSTERS)
    root_r = ET.fromstring(r_roosters.content)
    
    res_list = []
    # In de roosters XML zoeken we naar de types Gastles/Excursie
    for item in root_r.findall('.//ns1:item', ns) or root_r.findall('.//item', ns):
        school = item.find('ns1:schoolnaam', ns)
        type_act = item.find('ns1:type', ns)
        
        if school is not None and type_act is not None:
            if type_act.text in ['Gastles', 'Excursie']:
                res_list.append(school.text)
    
    df_res = pd.DataFrame(res_list, columns=['Schoolnaam']).value_counts().reset_index()
    df_res.columns = ['Schoolnaam', 'Reserveringen']

    # 2. Scholen ophalen (Groepen & Type)
    r_scholen = requests.get(URL_SCHOLEN)
    root_s = ET.fromstring(r_scholen.content)
    
    scholen_list = []
    # Op basis van jouw fragment zoeken we nu naar 'ns1:school'
    for school_node in root_s.findall('.//ns1:school', ns):
        naam = school_node.find('ns1:schoolnaam', ns)
        stype = school_node.find('ns1:schooltype', ns)
        # Let op: ik gebruik hier 'ns1:aantalingevoerdegroepen'. 
        # Mocht deze tag anders heten in de scholen-xml, pas dit dan aan.
        groepen = school_node.find('ns1:aantalingevoerdegroepen', ns)
        
        if naam is not None and stype is not None and stype.text.lower() == 'po':
            scholen_list.append({
                'Schoolnaam': naam.text,
                'Ingevoerde groepen': int(groepen.text) if groepen is not None and groepen.text else 0
            })
            
    df_scholen = pd.DataFrame(scholen_list)
    
    # 3. Mergen
    final = pd.merge(df_scholen, df_res, on='Schoolnaam', how='left').fillna(0)
    final['Reserveringen'] = final['Reserveringen'].astype(int)
    final['Limiet'] = final['Ingevoerde groepen'] * 2
    return final

# --- UI ---
st.title("📊 NME Dashboard")

try:
    df = fetch_data()

    # Sidebar filters
    st.sidebar.header("Filters")
    f_limiet = st.sidebar.checkbox("Reserveringen > Limiet")
    f_groepen = st.sidebar.checkbox("Ingevoerde groepen > 20")

    # Filter logica
    display_df = df.copy()
    if f_limiet:
        display_df = display_df[display_df['Reserveringen'] > display_df['Limiet']]
    if f_groepen:
        display_df = display_df[display_df['Ingevoerde groepen'] > 20]

    # Dashboard weergave
    c1, c2 = st.columns(2)
    c1.metric("Geselecteerde scholen", len(display_df))
    c2.metric("Totaal aantal reserveringen", display_df['Reserveringen'].sum())

    st.dataframe(display_df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Fout bij verwerken data: {e}")