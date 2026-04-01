import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

# Pagina-instellingen voor een mooi dashboard
st.set_page_config(page_title="NME Scholen Analyse", layout="wide")

# De exacte namespaces uit jouw XML
NAMESPACES = {
    'ns1': 'https://www.nmegids.nl/algemeen/interface/xml',
    'xsi': 'https://www.w3.org/2001/XMLSchema-instance'
}

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=600)
def laad_data():
    # 1. Roosters ophalen (voor reserveringen)
    try:
        r_roosters = requests.get(URL_ROOSTERS)
        root_r = ET.fromstring(r_roosters.content)
        
        res_data = []
        # We zoeken naar alle 'item' elementen binnen de ns1 namespace
        for item in root_r.findall('.//ns1:item', NAMESPACES):
            school = item.find('ns1:schoolnaam', NAMESPACES)
            type_act = item.find('ns1:type', NAMESPACES)
            
            if school is not None and type_act is not None:
                # Alleen Gastlessen en Excursies tellen
                if type_act.text in ['Gastles', 'Excursie']:
                    res_data.append(school.text)
        
        df_res = pd.DataFrame(res_data, columns=['Schoolnaam']).value_counts().reset_index()
        df_res.columns = ['Schoolnaam', 'Reserveringen']
    except Exception as e:
        st.error(f"Fout bij laden roosters: {e}")
        df_res = pd.DataFrame(columns=['Schoolnaam', 'Reserveringen'])

    # 2. Scholen ophalen (voor groepen en type)
    try:
        r_scholen = requests.get(URL_SCHOLEN)
        root_s = ET.fromstring(r_scholen.content)
        
        scholen_list = []
        # Hier zoeken we naar 'school' elementen binnen de ns1 namespace
        for school_node in root_s.findall('.//ns1:school', NAMESPACES):
            naam = school_node.find('ns1:schoolnaam', NAMESPACES)
            stype = school_node.find('ns1:schooltype', NAMESPACES)
            groepen = school_node.find('ns1:aantalingevoerdegroepen', NAMESPACES)
            
            # Filter op type 'po' (Primair Onderwijs)
            if naam is not None and stype is not None and stype.text.lower() == 'po':
                scholen_list.append({
                    'Schoolnaam': naam.text,
                    'Ingevoerde groepen': int(groepen.text) if (groepen is not None and groepen.text) else 0
                })
        
        df_scholen = pd.DataFrame(scholen_list)
    except Exception as e:
        st.error(f"Fout bij laden scholen: {e}")
        df_scholen = pd.DataFrame(columns=['Schoolnaam', 'Ingevoerde groepen'])

    # 3. Data combineren
    if not df_scholen.empty:
        # Koppel de reserveringen aan de scholenlijst
        final = pd.merge(df_scholen, df_res, on='Schoolnaam', how='left').fillna(0)
        final['Reserveringen'] = final['Reserveringen'].astype(int)
        final['Limiet'] = final['Ingevoerde groepen'] * 2
        return final
    else:
        return pd.DataFrame()

# --- UI GEDEELTE ---
st.title("📊 NME Scholen Analyse")
st.markdown("Overzicht van reserveringen vs. groepen voor PO scholen.")

data = laad_data()

if not data.empty:
    # Sidebar Filters
    st.sidebar.header("Filter Instellingen")
    check_limiet = st.sidebar.checkbox("Toon alleen: Reserveringen > Limiet")
    check_groepen = st.sidebar.checkbox("Toon alleen: Groepen > 20")

    # Toepassen filters
    df_filtered = data.copy()
    if check_limiet:
        df_filtered = df_filtered[df_filtered['Reserveringen'] > df_filtered['Limiet']]
    if check_groepen:
        df_filtered = df_filtered[df_filtered['Ingevoerde groepen'] > 20]

    # Statistieken bovenin
    c1, c2, c3 = st.columns(3)
    c1.metric("Aantal scholen", len(df_filtered))
    c2.metric("Totaal reserveringen", df_filtered['Reserveringen'].sum())
    c3.metric("Totaal groepen", df_filtered['Ingevoerde groepen'].sum())

    # De Tabel
    st.subheader("Schoolgegevens")
    st.dataframe(
        df_filtered.sort_values('Reserveringen', ascending=False),
        use_container_width=True,
        hide_index=True
    )
    
    # Download knop voor de collega
    csv = df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button("Download deze lijst (CSV)", csv, "nme_analyse.csv", "text/csv")
else:
    st.warning("Geen data kunnen ophalen. Controleer of de XML links en token nog geldig zijn.")
