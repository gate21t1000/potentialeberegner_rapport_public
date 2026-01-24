"""
Potentialeberegner - IoT Investeringsrapport
Streamlit App til visualisering af BBR-data og investeringspotentiale
Version 2: Med detalje-mode for enkelt bygning
"""

import streamlit as st
import pandas as pd
import geopandas as gpd
import numpy as np
from sqlalchemy import create_engine, text
import folium
from folium import plugins
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="IoT Investeringspotentiale",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# DATABASE CONNECTION (credentials fra Streamlit Secrets)
# =============================================================================

@st.cache_resource
def get_engine():
    """Opret database connection med credentials fra secrets"""
    db = st.secrets["database"]
    connection_string = f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}"
    return create_engine(connection_string)

def query_df(sql):
    """Kør SQL og returner DataFrame"""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)

def query_gdf(sql):
    """Kør SQL og returner GeoDataFrame"""
    engine = get_engine()
    with engine.connect() as conn:
        return gpd.read_postgis(text(sql), conn, geom_col='the_geom')

# =============================================================================
# CONSTANTS
# =============================================================================

SCHEMA = st.secrets.get("schema", "potentialeberegner")
KORT_MAX_PUNKTER = 2000

# Farvepalette for anvendelser
ANVENDELSE_FARVER = {
    'Daginstitution': '#e41a1c',
    '(UDFASES) Daginstitution.': '#e41a1c',
    'Grundskole': '#377eb8',
    'Universitet': '#4daf4a',
    'Anden enhed til undervisning og forskning': '#4daf4a',
    'Enhed til kontor': '#984ea3',
    '(UDFASES) Offentlig administration.': '#984ea3',
    'Bibliotek': '#ff7f00',
    'Forsamlingshus': '#ffff33',
    'Anden enhed til kulturelle formål': '#a65628',
    'Sundhedscenter, lægehus, fødeklinik mv.': '#f781bf',
    'Svømmehal': '#00bcd4',
    'Idrætshal': '#2196f3',
    'Anden enhed til idrætsformål': '#03a9f4',
    'Klubhus i forbindelse med fritid- og idræt': '#009688',
    'Feriecenter, center til campingplads mv.': '#8bc34a',
    'Bolig i etageejendom, flerfamiliehus eller to-familiehus': '#795548',
    'Bolig i døgninstitution': '#9e9e9e',
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_color(anvendelse):
    """Returner farve for anvendelse"""
    if pd.isna(anvendelse):
        return '#999999'
    first_type = anvendelse.split(',')[0].strip()
    return ANVENDELSE_FARVER.get(first_type, '#999999')

def get_radius(investering):
    """Beregn radius baseret på investering"""
    if pd.isna(investering) or investering <= 0:
        return 4
    return min(4 + np.sqrt(investering) / 50, 20)

@st.cache_data(ttl=300)
def find_bygning_id(filter_type, filter_value):
    """Find bygnings-ID baseret på filter - returnerer None hvis flere/ingen bygninger"""
    if filter_type == 'Bygning ID':
        return filter_value
    elif filter_type == 'Adresse' and filter_value:
        sql = f"""
        SELECT DISTINCT bygning 
        FROM {SCHEMA}.bbr_potentiale 
        WHERE adressebetegnelse ILIKE '%{filter_value}%'
        AND bygning IS NOT NULL
        LIMIT 2
        """
        result = query_df(sql)
        if len(result) == 1:
            return result['bygning'].iloc[0]
    return None

def build_filter_clause(filter_type, filter_value, bygning_id=None, use_bygning_view=False):
    """Bygger WHERE clause baseret på filter"""
    if filter_type == 'Alle' or not filter_value:
        return ''
    
    # Hvis vi har fundet et specifikt bygnings-ID, brug det
    if bygning_id and filter_type in ['Adresse', 'Bygning ID']:
        if use_bygning_view:
            return f"AND bygning_id = '{bygning_id}'"
        else:
            return f"AND bp.bygning = '{bygning_id}'"
    
    if use_bygning_view:
        if filter_type == 'Bygning ID':
            return f"AND bygning_id = '{filter_value}'"
        elif filter_type == 'Adresse':
            return f"AND adresse ILIKE '%{filter_value}%'"
        elif filter_type == 'Kommune':
            return f"AND kommunekode = '{filter_value}'"
    else:
        if filter_type == 'Bygning ID':
            return f"AND bp.bygning = '{filter_value}'"
        elif filter_type == 'Adresse':
            return f"AND bp.adressebetegnelse ILIKE '%{filter_value}%'"
        elif filter_type == 'Kommune':
            return f"AND bp.kommunekode = '{filter_value}'"
    
    return ''

# =============================================================================
# CACHED DATA FUNCTIONS - OVERBLIK MODE
# =============================================================================

@st.cache_data(ttl=300)
def get_filter_options():
    """Hent unikke værdier til filter dropdowns"""
    kommuner = query_df(f"""
        SELECT DISTINCT kommunekode 
        FROM {SCHEMA}.bbr_potentiale 
        WHERE kommunekode IS NOT NULL 
        ORDER BY kommunekode
    """)
    return kommuner['kommunekode'].tolist()

@st.cache_data(ttl=300)
def get_adresse_options():
    """Hent unikke adresser til dropdown (begrænset til unikke bygnings-adresser)"""
    adresser = query_df(f"""
        SELECT DISTINCT ON (bygning)
            adressebetegnelse AS adresse
        FROM {SCHEMA}.bbr_potentiale 
        WHERE adressebetegnelse IS NOT NULL
          AND bygning IS NOT NULL
        ORDER BY bygning, adressebetegnelse
        LIMIT 5000
    """)
    return sorted(adresser['adresse'].dropna().tolist())

@st.cache_data(ttl=300)
def get_statistik(filter_clause):
    """Hent overordnet statistik"""
    sql = f"""
    SELECT 
        COUNT(DISTINCT bp.bygning) AS antal_bygninger,
        COUNT(*) AS antal_enheder,
        ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT bp.bygning), 0), 1) AS gns_enheder_per_bygning,
        COALESCE(SUM(bp.total_antal_sensorer), 0) AS total_sensorer,
        COALESCE(SUM(bp.samlet_investering_min_kr), 0) AS total_investering_min,
        COALESCE(SUM(bp.samlet_investering_max_kr), 0) AS total_investering_max,
        ROUND(COALESCE(SUM(bp.samlet_investering_max_kr), 0) / NULLIF(COUNT(DISTINCT bp.bygning), 0), 0) AS gns_investering_per_bygning
    FROM {SCHEMA}.bbr_potentiale bp
    WHERE bp.bygning IS NOT NULL
    {filter_clause}
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_anvendelse_data(filter_clause):
    """Hent data per anvendelse"""
    sql = f"""
    SELECT 
        bp.enh020_enhedens_anvendelse_txt AS anvendelse,
        COUNT(DISTINCT bp.bygning) AS antal_bygninger,
        COUNT(*) AS antal_enheder,
        ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT bp.bygning), 0), 1) AS gns_enheder_per_bygning,
        COALESCE(SUM(bp.total_antal_sensorer), 0) AS total_sensorer,
        COALESCE(SUM(bp.samlet_investering_min_kr), 0) AS investering_min_kr,
        COALESCE(SUM(bp.samlet_investering_max_kr), 0) AS investering_max_kr
    FROM {SCHEMA}.bbr_potentiale bp
    WHERE bp.bygning IS NOT NULL
      AND bp.enh020_enhedens_anvendelse_txt IS NOT NULL
    {filter_clause}
    GROUP BY bp.enh020_enhedens_anvendelse_txt
    ORDER BY investering_max_kr DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_sensor_data(filter_clause):
    """Hent sensor data aggregeret"""
    sql = f"""
    SELECT 
        sensor_elem->>'type' AS sensor_type,
        COUNT(DISTINCT bp.id) AS antal_enheder,
        SUM((sensor_elem->>'antal')::INTEGER) AS total_antal_sensorer,
        SUM((sensor_elem->>'pris_total_min')::NUMERIC) AS total_pris_min,
        SUM((sensor_elem->>'pris_total_max')::NUMERIC) AS total_pris_max
    FROM {SCHEMA}.bbr_potentiale bp,
         jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
    WHERE bp.bygning IS NOT NULL
    {filter_clause}
    GROUP BY sensor_elem->>'type'
    ORDER BY total_antal_sensorer DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_kommune_data(filter_clause):
    """Hent kommune data"""
    sql = f"""
    SELECT 
        bp.kommunekode,
        COUNT(DISTINCT bp.bygning) AS antal_bygninger,
        COUNT(*) AS antal_enheder,
        COALESCE(SUM(bp.total_antal_sensorer), 0) AS total_sensorer,
        COALESCE(SUM(bp.samlet_investering_min_kr), 0) AS investering_min_kr,
        COALESCE(SUM(bp.samlet_investering_max_kr), 0) AS investering_max_kr
    FROM {SCHEMA}.bbr_potentiale bp
    WHERE bp.bygning IS NOT NULL
      AND bp.kommunekode IS NOT NULL
    {filter_clause}
    GROUP BY bp.kommunekode
    ORDER BY investering_max_kr DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_geodata(filter_clause_view):
    """Hent geodata til kort"""
    sql = f"""
    SELECT 
        bygning_id,
        antal_enheder,
        anvendelsestyper,
        adresse,
        kommunekode,
        total_sensorer,
        investering_min_kr,
        investering_max_kr,
        investerings_niveau,
        the_geom,
        latitude,
        longitude
    FROM {SCHEMA}.v_bygning_geomap
    WHERE the_geom IS NOT NULL
    {filter_clause_view}
    LIMIT {KORT_MAX_PUNKTER}
    """
    return query_gdf(sql)

@st.cache_data(ttl=300)
def get_top_bygninger(filter_clause_view):
    """Hent top bygninger"""
    sql = f"""
    SELECT 
        adresse,
        anvendelsestyper,
        kommunekode,
        antal_enheder,
        total_sensorer,
        investering_min_kr,
        investering_max_kr
    FROM {SCHEMA}.v_bygning_geomap
    WHERE 1=1
    {filter_clause_view}
    ORDER BY investering_max_kr DESC
    LIMIT 20
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_usecase_data(filter_clause):
    """Hent use case data aggregeret"""
    sql = f"""
    SELECT 
        uc_elem->>'navn' AS use_case_navn,
        uc_elem->>'kategori' AS kategori,
        COUNT(DISTINCT bp.id) AS antal_enheder
    FROM {SCHEMA}.bbr_potentiale bp,
         jsonb_array_elements(bp.use_cases) AS uc_elem
    WHERE bp.bygning IS NOT NULL
    {filter_clause}
    GROUP BY uc_elem->>'navn', uc_elem->>'kategori'
    ORDER BY antal_enheder DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_facilitet_data(filter_clause):
    """Hent facilitet data"""
    sql = f"""
    SELECT 
        bp.enh020_enhedens_anvendelse_txt AS anvendelse,
        COUNT(*) AS antal_enheder,
        COALESCE(SUM(bp.antal_toiletter), 0) AS total_toiletter,
        COALESCE(SUM(bp.antal_badevaerelser), 0) AS total_badevaerelser,
        COALESCE(SUM(bp.antal_koekken), 0) AS total_koekken,
        COALESCE(SUM(bp.antal_toiletter + bp.antal_badevaerelser + bp.antal_koekken), 0) AS total_faciliteter
    FROM {SCHEMA}.bbr_potentiale bp
    WHERE bp.enh020_enhedens_anvendelse_txt IS NOT NULL
    {filter_clause}
    GROUP BY bp.enh020_enhedens_anvendelse_txt
    ORDER BY total_faciliteter DESC
    LIMIT 15
    """
    return query_df(sql)

# =============================================================================
# CACHED DATA FUNCTIONS - DETALJE MODE (enkelt bygning)
# =============================================================================

@st.cache_data(ttl=300)
def get_bygning_info(bygning_id):
    """Hent detaljeret info om en enkelt bygning"""
    sql = f"""
    SELECT 
        bg.bygning_id,
        bg.adresse,
        bg.anvendelsestyper,
        bg.kommunekode,
        bg.antal_enheder,
        bg.total_sensorer,
        bg.investering_min_kr,
        bg.investering_max_kr,
        bg.investerings_niveau,
        bg.total_toiletter,
        bg.total_badevaerelser,
        bg.total_koekken,
        bg.samlet_areal_m2
    FROM {SCHEMA}.v_investering_per_bygning bg
    WHERE bg.bygning_id = '{bygning_id}'
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_sensor_usecase_breakdown(bygning_id):
    """Hent detaljeret sensor-breakdown per use case for en bygning"""
    sql = f"""
    WITH bygning_sensorer AS (
        SELECT 
            bp.id AS enhed_id,
            bp.enh020_enhedens_anvendelse_txt AS anvendelse,
            sensor_elem->>'type' AS sensor_type,
            (sensor_elem->>'antal')::INTEGER AS antal,
            (sensor_elem->>'pris_total_min')::NUMERIC AS pris_min,
            (sensor_elem->>'pris_total_max')::NUMERIC AS pris_max,
            sensor_elem->'for_use_cases' AS use_case_ids
        FROM {SCHEMA}.bbr_potentiale bp,
             jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
        WHERE bp.bygning = '{bygning_id}'
    ),
    sensor_med_usecases AS (
        SELECT 
            bs.sensor_type,
            bs.antal,
            bs.pris_min,
            bs.pris_max,
            uc.use_case_navn
        FROM bygning_sensorer bs,
             jsonb_array_elements_text(bs.use_case_ids) AS uc_id
        JOIN {SCHEMA}.use_cases uc ON uc.id = uc_id::INTEGER
    )
    SELECT 
        use_case_navn,
        sensor_type,
        SUM(antal) AS antal_sensorer,
        SUM(pris_min) AS pris_min,
        SUM(pris_max) AS pris_max
    FROM sensor_med_usecases
    GROUP BY use_case_navn, sensor_type
    ORDER BY use_case_navn, antal_sensorer DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_usecase_summary(bygning_id):
    """Hent use case summary med antal enheder og sensorer for en bygning"""
    sql = f"""
    WITH bygning_usecases AS (
        SELECT 
            bp.id AS enhed_id,
            uc_elem->>'navn' AS use_case_navn,
            uc_elem->>'kategori' AS kategori
        FROM {SCHEMA}.bbr_potentiale bp,
             jsonb_array_elements(bp.use_cases) AS uc_elem
        WHERE bp.bygning = '{bygning_id}'
    ),
    bygning_sensorer AS (
        SELECT 
            bp.id AS enhed_id,
            sensor_elem->>'type' AS sensor_type,
            (sensor_elem->>'antal')::INTEGER AS antal,
            (sensor_elem->>'pris_total_min')::NUMERIC AS pris_min,
            (sensor_elem->>'pris_total_max')::NUMERIC AS pris_max,
            sensor_elem->'for_use_cases' AS use_case_ids
        FROM {SCHEMA}.bbr_potentiale bp,
             jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
        WHERE bp.bygning = '{bygning_id}'
    ),
    usecase_sensor_count AS (
        SELECT 
            uc.use_case_navn,
            SUM(bs.antal) AS sensorer_til_usecase
        FROM bygning_sensorer bs,
             jsonb_array_elements_text(bs.use_case_ids) AS uc_id
        JOIN {SCHEMA}.use_cases uc ON uc.id = uc_id::INTEGER
        GROUP BY uc.use_case_navn
    )
    SELECT 
        bu.use_case_navn,
        bu.kategori,
        COUNT(DISTINCT bu.enhed_id) AS antal_enheder,
        COALESCE(usc.sensorer_til_usecase, 0) AS antal_sensorer
    FROM bygning_usecases bu
    LEFT JOIN usecase_sensor_count usc ON bu.use_case_navn = usc.use_case_navn
    GROUP BY bu.use_case_navn, bu.kategori, usc.sensorer_til_usecase
    ORDER BY antal_sensorer DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_sensor_summary(bygning_id):
    """Hent sensor summary for en bygning"""
    sql = f"""
    SELECT 
        sensor_elem->>'type' AS sensor_type,
        SUM((sensor_elem->>'antal')::INTEGER) AS antal,
        SUM((sensor_elem->>'pris_total_min')::NUMERIC) AS pris_min,
        SUM((sensor_elem->>'pris_total_max')::NUMERIC) AS pris_max
    FROM {SCHEMA}.bbr_potentiale bp,
         jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
    WHERE bp.bygning = '{bygning_id}'
    GROUP BY sensor_elem->>'type'
    ORDER BY antal DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_sensor_with_usecases(bygning_id):
    """Hent sensorer med tilhørende use cases for en bygning"""
    sql = f"""
    WITH sensor_usecase_data AS (
        SELECT 
            sensor_elem->>'type' AS sensor_type,
            (sensor_elem->>'antal')::INTEGER AS antal,
            (sensor_elem->>'pris_total_min')::NUMERIC AS pris_min,
            (sensor_elem->>'pris_total_max')::NUMERIC AS pris_max,
            sensor_elem->'for_use_cases' AS use_case_ids
        FROM {SCHEMA}.bbr_potentiale bp,
             jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
        WHERE bp.bygning = '{bygning_id}'
    ),
    sensor_with_uc_names AS (
        SELECT 
            s.sensor_type,
            s.antal,
            s.pris_min,
            s.pris_max,
            uc.use_case_navn
        FROM sensor_usecase_data s,
             jsonb_array_elements_text(s.use_case_ids) AS uc_id
        LEFT JOIN {SCHEMA}.use_cases uc ON uc.id = uc_id::INTEGER
    )
    SELECT 
        sensor_type,
        SUM(antal) AS antal,
        SUM(pris_min) AS pris_min,
        SUM(pris_max) AS pris_max,
        STRING_AGG(DISTINCT use_case_navn, ', ' ORDER BY use_case_navn) AS use_cases
    FROM sensor_with_uc_names
    GROUP BY sensor_type
    ORDER BY antal DESC
    """
    return query_df(sql)

@st.cache_data(ttl=300)
def get_kombo_alternativer(bygning_id):
    """Hent kombo-alternativer for en bygning via database-funktion"""
    try:
        sql = f"SELECT {SCHEMA}.get_kombo_alternativer('{bygning_id}'::UUID) AS kombos"
        result = query_df(sql)
        if len(result) > 0 and result['kombos'].iloc[0]:
            import json
            kombos = result['kombos'].iloc[0]
            if isinstance(kombos, str):
                return json.loads(kombos)
            if isinstance(kombos, list):
                return kombos
            return []
        return []
    except Exception as e:
        # Fallback hvis funktionen ikke findes - beregn i Python
        try:
            return get_kombo_alternativer_fallback(bygning_id)
        except Exception as e2:
            # Hvis fallback også fejler, returner tom liste med fejl-info
            return {'error': f"DB: {e}, Fallback: {e2}"}

@st.cache_data(ttl=300)
def get_kombo_alternativer_fallback(bygning_id):
    """Fallback beregning af kombo-alternativer hvis DB-funktion ikke findes"""
    # Hent sensorer for bygningen
    sensor_df = get_sensor_summary(bygning_id)
    if len(sensor_df) == 0:
        return []
    
    # Hent aktive kombos
    try:
        kombo_sql = f"""
        SELECT 
            k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr,
            ARRAY_AGG(ist.sensor_type ORDER BY ist.sensor_type) AS komponenter
        FROM {SCHEMA}.iot_sensor_kombos k
        JOIN {SCHEMA}.kombo_komponenter kk ON kk.kombo_id = k.id
        JOIN {SCHEMA}.iot_sensor_types ist ON ist.id = kk.sensor_type_id
        WHERE k.aktiv = TRUE
        GROUP BY k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr
        """
        kombo_df = query_df(kombo_sql)
    except Exception:
        return []  # Kombo-tabeller findes ikke endnu
    
    if len(kombo_df) == 0:
        return []
    
    # Byg sensor lookup med aliaser for PIR/Bevægelsessensor
    # Konverter til simple dicts for at undgå pandas Series problemer
    sensor_dict = {}
    for _, row in sensor_df.iterrows():
        sensor_dict[row['sensor_type']] = {
            'sensor_type': row['sensor_type'],
            'antal': int(row['antal']),
            'pris_min': float(row['pris_min']),
            'pris_max': float(row['pris_max'])
        }
    
    # Alias: Bevægelsessensor og Tilstedeværelsessensor er ens (PIR)
    pir_aliases = ['Bevægelsessensor', 'Tilstedeværelsessensor']
    pir_sensor = None
    for alias in pir_aliases:
        if alias in sensor_dict:
            pir_sensor = sensor_dict[alias]
            break
    
    # Tilføj aliaser til sensor_dict
    if pir_sensor:
        for alias in pir_aliases:
            if alias not in sensor_dict:
                sensor_dict[alias] = pir_sensor
    
    alternativer = []
    for _, kombo in kombo_df.iterrows():
        komponenter = kombo['komponenter']
        # Håndter None, tom liste, eller pandas Series
        if komponenter is None or (hasattr(komponenter, '__len__') and len(komponenter) == 0):
            continue
        
        # Konverter til liste hvis det er et array
        if hasattr(komponenter, 'tolist'):
            komponenter = komponenter.tolist()
        elif not isinstance(komponenter, list):
            komponenter = list(komponenter)
        
        # Tjek om alle komponenter findes (med alias-support)
        matched_komponenter = []
        all_found = True
        for k in komponenter:
            if k in sensor_dict:
                matched_komponenter.append(k)
            elif k in pir_aliases and pir_sensor is not None:
                # Brug alias
                matched_komponenter.append(k)
            else:
                all_found = False
                break
        
        if not all_found or len(matched_komponenter) == 0:
            continue
        
        # Beregn antal kombos = min antal af komponenter
        try:
            antal = min(int(sensor_dict[k]['antal']) for k in matched_komponenter)
        except (ValueError, KeyError):
            continue
        if antal <= 0:
            continue
        
        # Beregn enkelt-priser
        enkelt_pris_min = sum(float(sensor_dict[k]['pris_min']) for k in matched_komponenter)
        enkelt_pris_max = sum(float(sensor_dict[k]['pris_max']) for k in matched_komponenter)
        
        # Beregn kombo-priser
        kombo_pris_min = float(kombo['pris_min_kr']) * antal
        kombo_pris_max = float(kombo['pris_max_kr']) * antal
        
        # Kun vis hvis der er besparelse
        if enkelt_pris_min > kombo_pris_max:
            # Find de faktiske sensornavne fra bygningen (ikke kombo-definitionens navne)
            faktiske_sensorer = [sensor_dict[k]['sensor_type'] for k in matched_komponenter]
            alternativer.append({
                'kombo_navn': kombo['kombo_navn'],
                'erstatter': faktiske_sensorer,
                'antal': antal,
                'kombo_pris_min': kombo_pris_min,
                'kombo_pris_max': kombo_pris_max,
                'enkelt_pris_min': enkelt_pris_min,
                'enkelt_pris_max': enkelt_pris_max,
                'besparelse_min': enkelt_pris_min - kombo_pris_max,
                'besparelse_max': enkelt_pris_max - kombo_pris_min
            })
    
    # Sorter efter besparelse
    alternativer.sort(key=lambda x: x['besparelse_max'], reverse=True)
    return alternativer

# =============================================================================
# SIDEBAR - FILTERS
# =============================================================================

st.sidebar.title("🔧 Indstillinger")

st.sidebar.header("📍 Filter")

filter_type = st.sidebar.selectbox(
    "Filtrer på",
    ["Alle", "Kommune", "Adresse", "Bygning ID"],
    help="Vælg hvordan du vil filtrere data"
)

filter_value = None
if filter_type == "Kommune":
    try:
        kommuner = get_filter_options()
        filter_value = st.sidebar.selectbox("Vælg kommune", [""] + kommuner)
    except Exception as e:
        st.sidebar.error(f"Kunne ikke hente kommuner: {e}")
elif filter_type == "Adresse":
    try:
        adresser = get_adresse_options()
        filter_value = st.sidebar.selectbox(
            "Vælg adresse", 
            [""] + adresser,
            help="Vælg en adresse fra listen"
        )
    except Exception as e:
        st.sidebar.error(f"Kunne ikke hente adresser: {e}")
        filter_value = st.sidebar.text_input("Søg adresse", placeholder="f.eks. Vestergade")
elif filter_type == "Bygning ID":
    filter_value = st.sidebar.text_input("Bygning ID", placeholder="UUID")

# Bestem om vi er i detalje-mode (enkelt bygning)
bygning_id = None
detalje_mode = False

if filter_type in ['Adresse', 'Bygning ID'] and filter_value:
    bygning_id = find_bygning_id(filter_type, filter_value)
    if bygning_id:
        detalje_mode = True

# Byg filter clauses
filter_clause = build_filter_clause(filter_type, filter_value, bygning_id, use_bygning_view=False)
filter_clause_view = build_filter_clause(filter_type, filter_value, bygning_id, use_bygning_view=True)

# Filter beskrivelse
if filter_type == "Alle":
    filter_beskrivelse = "Alle bygninger"
elif filter_value:
    filter_beskrivelse = f"{filter_type}: {filter_value}"
else:
    filter_beskrivelse = "Alle bygninger"

st.sidebar.divider()

st.sidebar.header("📊 Sektioner")

# I detalje-mode: skjul irrelevante sektioner automatisk
if detalje_mode:
    st.sidebar.info("📌 Enkelt bygning valgt - visse sektioner skjult")
    show_statistik = st.sidebar.checkbox("Bygningsoversigt", value=True)
    show_anvendelse = False  # Irrelevant for enkelt bygning
    show_sensorer = st.sidebar.checkbox("Sensoroversigt (inkl. kombos)", value=True)
    show_kommuner = False  # Irrelevant for enkelt bygning
    show_kort = st.sidebar.checkbox("Kort", value=True)
    show_top_bygninger = False  # Irrelevant for enkelt bygning
    show_use_cases = st.sidebar.checkbox("Use cases (detaljeret)", value=True)
    show_faciliteter = st.sidebar.checkbox("Faciliteter", value=True)
    show_sensor_usecase_breakdown = st.sidebar.checkbox("Sensor/Use case breakdown", value=True)
else:
    show_statistik = st.sidebar.checkbox("Overordnet statistik", value=True)
    show_anvendelse = st.sidebar.checkbox("Anvendelsestyper", value=True)
    show_sensorer = st.sidebar.checkbox("Sensoroversigt", value=True)
    show_kommuner = st.sidebar.checkbox("Kommuneoversigt", value=True)
    show_kort = st.sidebar.checkbox("Kort", value=True)
    show_top_bygninger = st.sidebar.checkbox("Top bygninger", value=True)
    show_use_cases = st.sidebar.checkbox("Use cases", value=True)
    show_faciliteter = st.sidebar.checkbox("Faciliteter", value=True)
    show_sensor_usecase_breakdown = False

# =============================================================================
# MAIN CONTENT
# =============================================================================

st.title("🏢 IoT Investeringspotentiale")
st.caption(f"Rapport genereret: {datetime.now().strftime('%d-%m-%Y %H:%M')} | Filter: {filter_beskrivelse}")

# Intro-tekst
st.markdown("""
Dette værktøj beregner investeringspotentialet for IoT-sensorer baseret på data fra BBR (Bygnings- og Boligregistret).

**Hvad er en BBR-enhed?** En enhed er f.eks. en bolig i et parcelhus, en lejlighed eller et erhvervslejemål. 
Enfamiliehuse har typisk én enhed, mens etageejendomme har én enhed per lejlighed. 
Hver enhed har registreret areal, anvendelse og faciliteter (toiletter, badeværelser, køkkener).
""")

if detalje_mode:
    st.success(f"🔍 **Detalje-visning** for bygning: `{str(bygning_id)[:8]}...`")

# =============================================================================
# DETALJE MODE - ENKELT BYGNING
# =============================================================================

if detalje_mode and show_statistik:
    st.header("🏠 Bygningsoversigt")
    st.caption("Samlet oversigt over bygningen med antal enheder, sensorer og investeringsbehov.")
    
    try:
        bygning_info = get_bygning_info(bygning_id)
        
        if len(bygning_info) > 0:
            info = bygning_info.iloc[0]
            
            # Adresse og type i markant container
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); 
                        padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h2 style="color: white; margin: 0;">📍 {info['adresse'] or 'Ukendt adresse'}</h2>
                <p style="color: #a8d4ff; margin: 5px 0 0 0; font-size: 1.1em;">
                    {info['anvendelsestyper']} | Kommune: {info['kommunekode']}
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            # Investering i fremhævet box
            st.markdown("""
            <div style="background: #f0f7ff; padding: 15px; border-radius: 8px; 
                        border-left: 4px solid #1e3a5f; margin-bottom: 15px;">
                <p style="margin: 0; color: #1e3a5f; font-weight: bold;">💰 Samlet investeringsbehov</p>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Enheder", f"{info['antal_enheder']:,.0f}")
            with col2:
                st.metric("Sensorer (total)", f"{info['total_sensorer']:,.0f}")
            with col3:
                st.metric("Investering (min)", f"{info['investering_min_kr']:,.0f} kr")
            with col4:
                st.metric("Investering (max)", f"{info['investering_max_kr']:,.0f} kr")
            
            # Faciliteter
            st.markdown("""
            <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; 
                        border-left: 4px solid #666; margin: 15px 0;">
                <p style="margin: 0; color: #333; font-weight: bold;">🏗️ Faciliteter i bygningen</p>
            </div>
            """, unsafe_allow_html=True)
            
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("Toiletter", f"{info['total_toiletter']:,.0f}")
            with col6:
                st.metric("Badeværelser", f"{info['total_badevaerelser']:,.0f}")
            with col7:
                st.metric("Køkkener", f"{info['total_koekken']:,.0f}")
            with col8:
                areal = info['samlet_areal_m2'] or 0
                st.metric("Areal", f"{areal:,.0f} m²")
        else:
            st.warning("Kunne ikke finde bygningsinfo")
            
    except Exception as e:
        st.error(f"Kunne ikke hente bygningsinfo: {e}")

# -----------------------------------------------------------------------------
# DETALJE MODE: SENSOR OVERSIGT (med kombo-alternativer integreret)
# -----------------------------------------------------------------------------

if detalje_mode and show_sensorer:
    st.header("📡 Sensoroversigt")
    st.caption("Potentielle sensortyper til bygningens use cases. Cirkeldiagram viser fordeling, kombos viser besparelsesmuligheder.")
    
    try:
        # Hent sensorer med use cases
        sensor_df = get_sensor_with_usecases(bygning_id)
        
        if len(sensor_df) > 0:
            # Opret sensor label med use case i parentes (forkortet)
            def format_sensor_label(row):
                uc = row['use_cases'] if pd.notna(row['use_cases']) else ''
                # Forkort use case navne
                if uc:
                    uc_list = uc.split(', ')
                    if len(uc_list) > 2:
                        uc_short = ', '.join(uc_list[:2]) + f' +{len(uc_list)-2}'
                    else:
                        uc_short = uc
                    return f"{row['sensor_type']} ({uc_short})"
                return row['sensor_type']
            
            sensor_df['sensor_label'] = sensor_df.apply(format_sensor_label, axis=1)
            sensor_df['pris_spænd'] = sensor_df.apply(
                lambda r: f"{r['pris_min']:,.0f} - {r['pris_max']:,.0f} kr", axis=1
            )
            
            # Layout: Cirkeldiagram + Tabel side om side
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("Antal potentielle sensortyper")
                # Cirkeldiagram
                fig_pie = px.pie(
                    sensor_df,
                    values='antal',
                    names='sensor_type',
                    title='Fordeling af sensortyper',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_pie.update_traces(
                    textposition='inside',
                    textinfo='value+label',
                    hovertemplate='<b>%{label}</b><br>Antal: %{value}<br>Use cases: %{customdata}<extra></extra>',
                    customdata=sensor_df['use_cases'].fillna('Ingen')
                )
                fig_pie.update_layout(height=500, showlegend=False)
                st.plotly_chart(fig_pie, width="stretch")
            
            with col2:
                st.subheader("Sensortabel")
                st.dataframe(
                    sensor_df[['sensor_type', 'antal', 'pris_spænd', 'use_cases']].rename(columns={
                        'sensor_type': 'Sensortype',
                        'antal': 'Antal',
                        'pris_spænd': 'Pris (min-max)',
                        'use_cases': 'Use cases'
                    }),
                    hide_index=True,
                    width="stretch",
                    height=450
                )
            
            # Totaler
            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                st.metric("Total sensortyper", f"{len(sensor_df)}")
            with col_t2:
                st.metric("Total sensorer", f"{sensor_df['antal'].sum():,.0f}")
            with col_t3:
                st.metric("Total investering", f"{sensor_df['pris_min'].sum():,.0f} - {sensor_df['pris_max'].sum():,.0f} kr")
            
            # --- KOMBO-ALTERNATIVER INTEGRERET ---
            st.divider()
            st.subheader("🔄 Kombo-alternativer")
            st.caption("Kombinations-sensorer der kan erstatte flere enkelt-sensorer med potentielle besparelser.")
            
            try:
                kombos = get_kombo_alternativer(bygning_id)
                
                # Tjek for fejl
                if isinstance(kombos, dict) and 'error' in kombos:
                    st.warning(f"Kombo-beregning fejlede: {kombos['error']}")
                    st.caption("Kør `kombo_sensorer.sql` i databasen for at aktivere.")
                elif kombos and len(kombos) > 0:
                    # Forklaring af tabellen
                    st.info("""
                    **Sådan læses tabellen:**
                    - **Separate sensorer**: Hvad det ville koste at købe sensorerne enkeltvis
                    - **Kombo-pris**: Prisen for én kombinationssensor der dækker alle funktioner
                    - **Besparelse**: Forskellen mellem at købe enkelt-sensorer vs. en kombo-sensor
                    """)
                    
                    # Kombo oversigt som cirkeldiagram (besparelser)
                    kombo_df = pd.DataFrame(kombos)
                    
                    col_k1, col_k2 = st.columns([1, 1])
                    
                    with col_k1:
                        # Cirkeldiagram over besparelser
                        fig_kombo = px.pie(
                            kombo_df,
                            values='besparelse_max',
                            names='kombo_navn',
                            title='Potentiel besparelse per kombo',
                            hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Pastel
                        )
                        fig_kombo.update_traces(
                            textposition='inside',
                            textinfo='value+label',
                            hovertemplate='<b>%{label}</b><br>Besparelse: %{value:,.0f} kr<extra></extra>'
                        )
                        fig_kombo.update_layout(height=500, showlegend=False)
                        st.plotly_chart(fig_kombo, width="stretch")
                    
                    with col_k2:
                        # Kombo tabel med bedre kolonnenavne
                        kombo_display = kombo_df[['kombo_navn', 'antal', 'enkelt_pris_max', 'kombo_pris_max', 'besparelse_max']].copy()
                        kombo_display.columns = ['Kombo', 'Antal', 'Separate sensorer', 'Kombo-pris', 'Besparelse']
                        kombo_display['Separate sensorer'] = kombo_display['Separate sensorer'].apply(lambda x: f"{x:,.0f} kr")
                        kombo_display['Kombo-pris'] = kombo_display['Kombo-pris'].apply(lambda x: f"{x:,.0f} kr")
                        kombo_display['Besparelse'] = kombo_display['Besparelse'].apply(lambda x: f"{x:,.0f} kr")
                        
                        st.dataframe(kombo_display, hide_index=True, width="stretch", height=400)
                    
                    # Total besparelse
                    total_besparelse = sum(k['besparelse_max'] for k in kombos)
                    st.success(f"💰 **Samlet potentiel besparelse:** {total_besparelse:,.0f} kr (ved brug af alle kombos)")
                    
                    # Bedre forklaring af advarsel
                    with st.expander("⚠️ Vigtigt om besparelsesberegningen", expanded=False):
                        st.markdown("""
                        **Hvorfor kan besparelserne ikke bare lægges sammen?**
                        
                        Flere kombos kan indeholde de samme sensortyper. For eksempel:
                        - "Temperatur + Luftfugtighed" indeholder temperaturføler
                        - "Temperatur + CO2" indeholder også temperaturføler
                        
                        Hvis du vælger begge kombos, får du **to** temperaturfølere – men du har måske kun brug for **én**.
                        
                        **Anbefaling:** Vælg den kombo der bedst matcher dit behov, eller kontakt en rådgiver for at finde den optimale løsning.
                        """)
                    
                else:
                    st.info("Ingen kombo-alternativer fundet for denne bygning. Sensorerne matcher ikke tilgængelige kombinations-sensorer.")
                    
            except Exception as e:
                st.warning(f"Kombo-beregning fejlede: {e}")
                st.caption("Kør `kombo_sensorer.sql` i databasen for at aktivere.")
                
        else:
            st.info("Ingen sensordata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente sensordata: {e}")

# -----------------------------------------------------------------------------
# DETALJE MODE: USE CASES
# -----------------------------------------------------------------------------

if detalje_mode and show_use_cases:
    st.header("💡 Use Cases (detaljeret)")
    st.caption("IoT use cases identificeret for bygningen, med antal sensorer der kræves til hver.")
    
    try:
        usecase_df = get_usecase_summary(bygning_id)
        
        if len(usecase_df) > 0:
            fig_usecase = px.bar(
                usecase_df,
                x='antal_sensorer',
                y='use_case_navn',
                orientation='h',
                title='Use cases med antal sensorer',
                labels={'antal_sensorer': 'Antal sensorer', 'use_case_navn': 'Use case'},
                color='kategori',
                color_discrete_sequence=px.colors.qualitative.Set2,
                hover_data=['antal_enheder']
            )
            fig_usecase.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_usecase, width="stretch")
            
            # Tabel med detaljer
            with st.expander("📋 Se use case tabel"):
                st.dataframe(
                    usecase_df.rename(columns={
                        'use_case_navn': 'Use Case',
                        'kategori': 'Kategori',
                        'antal_enheder': 'Enheder',
                        'antal_sensorer': 'Sensorer'
                    }),
                    hide_index=True,
                    width="stretch"
                )
        else:
            st.info("Ingen use case data fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente use case data: {e}")

# -----------------------------------------------------------------------------
# DETALJE MODE: SENSOR/USE CASE BREAKDOWN
# -----------------------------------------------------------------------------

if detalje_mode and show_sensor_usecase_breakdown:
    st.header("🔗 Sensor/Use Case Breakdown")
    st.caption("Matrix der viser hvilke sensortyper der bruges til hvilke use cases.")
    st.caption("Viser hvilke sensorer der bruges til hvilke use cases")
    
    try:
        breakdown_df = get_sensor_usecase_breakdown(bygning_id)
        
        if len(breakdown_df) > 0:
            # Pivot tabel
            pivot_df = breakdown_df.pivot_table(
                index='use_case_navn',
                columns='sensor_type',
                values='antal_sensorer',
                fill_value=0,
                aggfunc='sum'
            )
            
            # Heatmap
            fig_heatmap = px.imshow(
                pivot_df,
                labels=dict(x="Sensortype", y="Use Case", color="Antal"),
                title="Sensor/Use Case Matrix",
                color_continuous_scale='Blues',
                aspect='auto'
            )
            fig_heatmap.update_layout(height=600)
            st.plotly_chart(fig_heatmap, width="stretch")
            
            # Detalje tabel
            with st.expander("📋 Se komplet breakdown tabel"):
                breakdown_df['pris_spænd'] = breakdown_df.apply(
                    lambda r: f"{r['pris_min']:,.0f} - {r['pris_max']:,.0f} kr", axis=1
                )
                st.dataframe(
                    breakdown_df[['use_case_navn', 'sensor_type', 'antal_sensorer', 'pris_spænd']].rename(columns={
                        'use_case_navn': 'Use Case',
                        'sensor_type': 'Sensortype',
                        'antal_sensorer': 'Antal',
                        'pris_spænd': 'Pris'
                    }),
                    hide_index=True,
                    width="stretch"
                )
        else:
            st.info("Ingen breakdown data fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente breakdown: {e}")

# =============================================================================
# OVERBLIK MODE - ALLE/KOMMUNE FILTER
# =============================================================================

if not detalje_mode and show_statistik:
    st.header("📈 Overordnet Statistik")
    st.caption("Aggregerede nøgletal for alle bygninger i det valgte filter.")
    
    try:
        statistik = get_statistik(filter_clause)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Bygninger", f"{statistik['antal_bygninger'].iloc[0]:,.0f}")
        with col2:
            st.metric("Enheder", f"{statistik['antal_enheder'].iloc[0]:,.0f}")
        with col3:
            st.metric("Sensorer", f"{statistik['total_sensorer'].iloc[0]:,.0f}")
        with col4:
            st.metric("Investering (max)", f"{statistik['total_investering_max'].iloc[0]:,.0f} kr")
        
        col5, col6, col7 = st.columns(3)
        with col5:
            st.metric("Gns. enheder/bygning", f"{statistik['gns_enheder_per_bygning'].iloc[0]:.1f}")
        with col6:
            st.metric("Investering (min)", f"{statistik['total_investering_min'].iloc[0]:,.0f} kr")
        with col7:
            st.metric("Gns. investering/bygning", f"{statistik['gns_investering_per_bygning'].iloc[0]:,.0f} kr")
            
    except Exception as e:
        st.error(f"Kunne ikke hente statistik: {e}")

# -----------------------------------------------------------------------------
# ANVENDELSE (kun overblik mode)
# -----------------------------------------------------------------------------

if not detalje_mode and show_anvendelse:
    st.header("🏛️ Investering per Anvendelsestype")
    st.caption("Fordeling af investeringsbehov på tværs af bygningsanvendelser (skoler, institutioner, boliger mv.).")
    
    try:
        anvendelse_df = get_anvendelse_data(filter_clause)
        
        if len(anvendelse_df) > 0:
            col1, col2 = st.columns(2)
            
            with col1:
                fig_bar = px.bar(
                    anvendelse_df.head(15),
                    x='investering_max_kr',
                    y='anvendelse',
                    orientation='h',
                    title='Investering per anvendelsestype (Top 15)',
                    labels={'investering_max_kr': 'Investering (max kr)', 'anvendelse': 'Anvendelse'},
                    color='antal_bygninger',
                    color_continuous_scale='Blues'
                )
                fig_bar.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig_bar, width="stretch")
            
            with col2:
                fig_pie = px.pie(
                    anvendelse_df.head(10),
                    values='antal_bygninger',
                    names='anvendelse',
                    title='Fordeling af bygninger (Top 10)',
                    hole=0.4
                )
                fig_pie.update_layout(height=500)
                st.plotly_chart(fig_pie, width="stretch")
        else:
            st.info("Ingen data fundet for dette filter")
            
    except Exception as e:
        st.error(f"Kunne ikke hente anvendelsesdata: {e}")

# -----------------------------------------------------------------------------
# SENSORER (overblik mode)
# -----------------------------------------------------------------------------

if not detalje_mode and show_sensorer:
    st.header("📡 Sensoroversigt")
    st.caption("De mest anvendte sensortyper på tværs af alle bygninger i filteret.")
    
    try:
        sensor_df = get_sensor_data(filter_clause)
        
        if len(sensor_df) > 0:
            fig_sensor = px.bar(
                sensor_df.head(15),
                x='total_antal_sensorer',
                y='sensor_type',
                orientation='h',
                title='Mest anvendte sensortyper (Top 15)',
                labels={'total_antal_sensorer': 'Antal sensorer', 'sensor_type': 'Sensortype'},
                color='total_pris_max',
                color_continuous_scale='Oranges'
            )
            fig_sensor.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_sensor, width="stretch")
        else:
            st.info("Ingen sensordata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente sensordata: {e}")

# -----------------------------------------------------------------------------
# KOMMUNER (kun overblik mode)
# -----------------------------------------------------------------------------

if not detalje_mode and show_kommuner:
    st.header("🗺️ Kommuneoversigt")
    st.caption("Investeringsbehov fordelt på kommuner.")
    
    try:
        kommune_df = get_kommune_data(filter_clause)
        
        if len(kommune_df) > 0:
            fig_kommune = px.bar(
                kommune_df.head(20),
                x='kommunekode',
                y='investering_max_kr',
                title='Investering per kommune (Top 20)',
                labels={'investering_max_kr': 'Investering (max kr)', 'kommunekode': 'Kommune'},
                color='antal_bygninger',
                color_continuous_scale='Greens'
            )
            fig_kommune.update_layout(height=400)
            st.plotly_chart(fig_kommune, width="stretch")
        else:
            st.info("Ingen kommunedata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente kommunedata: {e}")

# -----------------------------------------------------------------------------
# KORT (begge modes)
# -----------------------------------------------------------------------------

if show_kort:
    st.header("🗺️ Kort over bygninger")
    st.caption("Geografisk visning af bygninger. Markørernes størrelse viser investeringspotentialet – større markør = højere investering. Klik for detaljer.")
    
    try:
        gdf = get_geodata(filter_clause_view)
        
        if len(gdf) > 0:
            # Konverter til WGS84
            gdf = gdf.to_crs(epsg=4326)
            
            # Beregn center
            center_lat = gdf.geometry.centroid.y.mean()
            center_lon = gdf.geometry.centroid.x.mean()
            
            # Juster zoom baseret på filter
            if detalje_mode:
                zoom = 16
            elif filter_type == 'Kommune' and filter_value:
                zoom = 11
            else:
                zoom = 7
            
            # Opret kort
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=zoom,
                tiles='CartoDB positron'
            )
            
            # Tilføj markers med forbedret popup
            for idx in range(len(gdf)):
                row = gdf.iloc[idx]
                geom = gdf.geometry.iloc[idx]
                
                if geom is None:
                    continue
                
                if geom.geom_type == 'Point':
                    lat, lon = geom.y, geom.x
                else:
                    centroid = geom.centroid
                    lat, lon = centroid.y, centroid.x
                
                color = get_color(row['anvendelsestyper'])
                radius = get_radius(row['investering_max_kr'])
                
                # Forbedret popup med mere info
                popup_html = f"""
                <div style="min-width: 250px;">
                    <h4 style="margin: 0 0 10px 0;">{row['adresse'] or 'Ukendt adresse'}</h4>
                    <table style="width: 100%; font-size: 12px;">
                        <tr><td><b>Anvendelse:</b></td><td>{row['anvendelsestyper']}</td></tr>
                        <tr><td><b>Kommune:</b></td><td>{row['kommunekode']}</td></tr>
                        <tr><td><b>Enheder:</b></td><td>{row['antal_enheder']:,.0f}</td></tr>
                        <tr><td><b>Sensorer:</b></td><td>{row['total_sensorer']:,.0f}</td></tr>
                        <tr><td><b>Investering:</b></td><td>{row['investering_min_kr']:,.0f} - {row['investering_max_kr']:,.0f} kr</td></tr>
                        <tr><td><b>Niveau:</b></td><td>{row['investerings_niveau']}</td></tr>
                    </table>
                    <p style="margin: 10px 0 0 0; font-size: 10px; color: #666;">
                        Bygning ID: {str(row['bygning_id'])[:8]}...
                    </p>
                </div>
                """
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    weight=1,
                    popup=folium.Popup(popup_html, max_width=350)
                ).add_to(m)
            
            # Vis kort
            st_folium(m, height=500, width=None)
            
            st.caption(f"Viser {len(gdf)} bygninger (max {KORT_MAX_PUNKTER})")
        else:
            st.info("Ingen bygninger med geometri fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente kortdata: {e}")

# -----------------------------------------------------------------------------
# TOP BYGNINGER (kun overblik mode)
# -----------------------------------------------------------------------------

if not detalje_mode and show_top_bygninger:
    st.header("🏆 Top 20 Bygninger")
    st.caption("Bygninger med størst investeringspotentiale sorteret efter maksimal investering.")
    
    try:
        top_df = get_top_bygninger(filter_clause_view)
        
        if len(top_df) > 0:
            # Formater tal
            top_df['investering_min_kr'] = top_df['investering_min_kr'].apply(lambda x: f"{x:,.0f} kr")
            top_df['investering_max_kr'] = top_df['investering_max_kr'].apply(lambda x: f"{x:,.0f} kr")
            
            st.dataframe(
                top_df,
                column_config={
                    "adresse": "Adresse",
                    "anvendelsestyper": "Anvendelse",
                    "kommunekode": "Kommune",
                    "antal_enheder": "Enheder",
                    "total_sensorer": "Sensorer",
                    "investering_min_kr": "Investering (min)",
                    "investering_max_kr": "Investering (max)"
                },
                hide_index=True,
                width="stretch"
            )
        else:
            st.info("Ingen bygninger fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente top bygninger: {e}")

# -----------------------------------------------------------------------------
# USE CASES (overblik mode)
# -----------------------------------------------------------------------------

if not detalje_mode and show_use_cases:
    st.header("💡 Use Cases")
    st.caption("De mest anvendte IoT use cases på tværs af alle bygninger.")
    
    try:
        usecase_df = get_usecase_data(filter_clause)
        
        if len(usecase_df) > 0:
            fig_usecase = px.bar(
                usecase_df.head(15),
                x='antal_enheder',
                y='use_case_navn',
                orientation='h',
                title='Mest anvendte use cases (Top 15)',
                labels={'antal_enheder': 'Antal enheder', 'use_case_navn': 'Use case'},
                color='kategori',
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig_usecase.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_usecase, width="stretch")
        else:
            st.info("Ingen use case data fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente use case data: {e}")

# -----------------------------------------------------------------------------
# FACILITETER (begge modes, men forskellig visning)
# -----------------------------------------------------------------------------

if show_faciliteter:
    st.header("🚿 Faciliteter")
    st.caption("Antal toiletter, badeværelser og køkkener – bruges til at beregne sensorantal.")
    
    try:
        if detalje_mode:
            # Enkelt bygning - vis simpel oversigt
            bygning_info = get_bygning_info(bygning_id)
            if len(bygning_info) > 0:
                info = bygning_info.iloc[0]
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🚽 Toiletter", f"{info['total_toiletter']:,.0f}")
                with col2:
                    st.metric("🚿 Badeværelser", f"{info['total_badevaerelser']:,.0f}")
                with col3:
                    st.metric("🍳 Køkkener", f"{info['total_koekken']:,.0f}")
        else:
            # Overblik - vis graf
            facilitet_df = get_facilitet_data(filter_clause)
            
            if len(facilitet_df) > 0:
                fig_facilitet = go.Figure()
                
                fig_facilitet.add_trace(go.Bar(
                    name='Toiletter',
                    x=facilitet_df['anvendelse'],
                    y=facilitet_df['total_toiletter'],
                    marker_color='#2196f3'
                ))
                
                fig_facilitet.add_trace(go.Bar(
                    name='Badeværelser',
                    x=facilitet_df['anvendelse'],
                    y=facilitet_df['total_badevaerelser'],
                    marker_color='#4caf50'
                ))
                
                fig_facilitet.add_trace(go.Bar(
                    name='Køkkener',
                    x=facilitet_df['anvendelse'],
                    y=facilitet_df['total_koekken'],
                    marker_color='#ff9800'
                ))
                
                fig_facilitet.update_layout(
                    barmode='stack',
                    title='Faciliteter per anvendelsestype',
                    xaxis_title='Anvendelse',
                    yaxis_title='Antal',
                    height=450,
                    xaxis_tickangle=-45
                )
                
                st.plotly_chart(fig_facilitet, width="stretch")
            else:
                st.info("Ingen facilitetdata fundet")
                
    except Exception as e:
        st.error(f"Kunne ikke hente facilitetdata: {e}")

# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.caption("Potentialeberegner v2 | Data fra BBR")
