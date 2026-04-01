import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

st.set_page_config(page_title="NME Monitor Pro", layout="wide")

NAMESPACES = {
    'ns1': 'https://www.nmegids.nl/algemeen/interface/xml',
    'xsi': 'https://www.w3.org/2001/XMLSchema-instance'
}

URL_ROOSTERS = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-roosters.php?aanbieder=we&token=143fe43ad3750bdewe&schooljaar=2025-2026"
URL_SCHOLEN = "https://nmegids.nl/algemeen/interface/xml/excelanalyse-scholen.php?aanbieder=we&token=143fe43ad3750bdewe"

@st.cache_data(ttl=300)
def laad_xml_data():
    # 1. Scholen XML
    r_s = requests.get(URL_SCHOLEN)
    root_s = ET.fromstring(r_s.content)
    scholen_list = []
    for s in root_s.findall('.//ns1:school', NAMESPACES):
        naam = s.find('ns1:schoolnaam', NAMESPACES)
        stype = s.find('ns1:schooltype', NAMESPACES)
        groepen = s.find('ns1:aantalingevoerdegroepen', NAMESPACES)
        if naam is not None and stype is not None and stype.text.lower() == 'po':
            scholen_list.append({
                'Schoolnaam': naam.text.strip(),
                'Match': naam.text.strip().lower(),
                'Ingevoerde groepen': int(groepen.text) if groepen is not None and groepen.text else 0
            })
    df_base = pd.DataFrame(scholen_list)

    # 2. Roosters XML
    r_r = requests.get(URL_ROOSTERS)
    root_r = ET.fromstring(r_r.content)
    rooster_namen = []
    for item in root_r.iter():
        s_naam = item.find('ns1:schoolnaam', NAMESPACES)
        s_type = item.find('ns1:type', NAMESPACES)
        if s_naam is not None and s_type is not None:
            if s_type.text in ['Gastles', 'Excursie']:
                rooster_namen.append(s_naam.text.strip().lower())
    
    df_counts = pd.DataFrame(rooster_namen, columns=['Match']).value_counts().reset_index()
    df_counts.columns = ['Match', 'Reserveringen']
    
    return pd.merge(df_base, df_counts, on='Match', how='left').fillna(0)

def kleur_rijen(row):
    # Logica voor kleuren
    if row['Reserveringen'] > row['Limiet']:
        return ['background-color: #ffcccc'] * len(row) # Rood
    elif row['Ingevoerde groepen'] > 20:
        return ['background-color: #ffe5cc'] * len(row) # Oranje
    return [''] * len(row)

# --- UI ---
st.title("📊 NME Monitor: PO Dashboard")

# Excel Upload in Sidebar
st.sidebar.header("Abonnementen Import")
uploaded_file = st.sidebar.file_uploader("Upload Excel met 'NAAM' kolom", type=["xlsx"])

df_xml = laad_xml_data()

if not df_xml.empty:
    # Verwerk Excel voor Oneindig Limiet
    abo_scholen = []
    if uploaded_file:
        df_excel = pd.read_excel(uploaded_file)
        if 'NAAM' in df_excel.columns:
            abo_scholen = df_excel['NAAM'].str.strip().str.lower().tolist()
            st.sidebar.success(f"{len(abo_scholen)} scholen met abonnement geladen.")

    # Bereken Limiet
    df_xml['Is_Abonnee'] = df_xml['Match'].isin(abo_scholen)
    df_xml['Limiet'] = df_xml.apply(lambda x: 999 if x['Is_Abonnee'] else (x['Ingevoerde groepen'] * 2), axis=1)
    df_xml['Reserveringen'] = df_xml['Reserveringen'].astype(int)

    # Filters
    st.sidebar.header("Filters")
    f_limiet = st.sidebar.checkbox("Alleen > Limiet")
    f_groepen = st.sidebar.checkbox("Alleen Groepen > 20")

    df_final = df_xml.copy()
    if f_limiet:
        df_final = df_final[df_final['Reserveringen'] > df_final['Limiet']]
    if f_groepen:
        df_final = df_final[df_final['Ingevoerde groepen'] > 20]

    # Opschonen voor weergave
    display_df = df_final[['Schoolnaam', 'Ingevoerde groepen', 'Reserveringen', 'Limiet']].copy()
    display_df['Limiet'] = display_df['Limiet'].replace(999, "∞")

    # Styling toepassen
    styled_df = display_df.style.apply(kleur_rijen, axis=1)

    # Metrics
    c1, c2 = st.columns(2)
    c1.metric("Aantal Scholen", len(display_df))
    c2.metric("Totaal Reserveringen", display_df['Reserveringen'].sum())

    st.write("### Schooloverzicht")
    st.write("_Rood: over limiet | Oranje: > 20 groepen_")
    st.table(styled_df) # Gebruik st.table voor vaste styling, of st.dataframe(styled_df)

    # Download
    csv = display_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Lijst", csv, "nme_rapport.csv", "text/csv")
