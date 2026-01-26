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
    """Hent unikke kommuner med navn til filter dropdowns"""
    # Kommune kode til navn mapping
    kommune_navne = {
        '0101': 'København', '0147': 'Frederiksberg', '0151': 'Ballerup', '0153': 'Brøndby',
        '0155': 'Dragør', '0157': 'Gentofte', '0159': 'Gladsaxe', '0161': 'Glostrup',
        '0163': 'Herlev', '0165': 'Albertslund', '0167': 'Hvidovre', '0169': 'Høje-Taastrup',
        '0173': 'Lyngby-Taarbæk', '0175': 'Rødovre', '0183': 'Ishøj', '0185': 'Tårnby',
        '0187': 'Vallensbæk', '0190': 'Furesø', '0201': 'Allerød', '0210': 'Fredensborg',
        '0217': 'Helsingør', '0219': 'Hillerød', '0223': 'Hørsholm', '0230': 'Rudersdal',
        '0240': 'Egedal', '0250': 'Frederikssund', '0253': 'Greve', '0259': 'Køge',
        '0260': 'Halsnæs', '0265': 'Roskilde', '0269': 'Solrød', '0270': 'Gribskov',
        '0306': 'Odsherred', '0316': 'Holbæk', '0320': 'Faxe', '0326': 'Kalundborg',
        '0329': 'Ringsted', '0330': 'Slagelse', '0336': 'Stevns', '0340': 'Sorø',
        '0350': 'Lejre', '0360': 'Lolland', '0370': 'Næstved', '0376': 'Guldborgsund',
        '0390': 'Vordingborg', '0400': 'Bornholm', '0410': 'Middelfart', '0411': 'Christiansø',
        '0420': 'Assens', '0430': 'Faaborg-Midtfyn', '0440': 'Kerteminde', '0450': 'Nyborg',
        '0461': 'Odense', '0479': 'Svendborg', '0480': 'Nordfyns', '0482': 'Langeland',
        '0492': 'Ærø', '0510': 'Haderslev', '0530': 'Billund', '0540': 'Sønderborg',
        '0550': 'Tønder', '0561': 'Esbjerg', '0563': 'Fanø', '0573': 'Varde',
        '0575': 'Vejen', '0580': 'Aabenraa', '0607': 'Fredericia', '0615': 'Horsens',
        '0621': 'Kolding', '0630': 'Vejle', '0657': 'Herning', '0661': 'Holstebro',
        '0665': 'Lemvig', '0671': 'Struer', '0706': 'Syddjurs', '0707': 'Norddjurs',
        '0710': 'Favrskov', '0727': 'Odder', '0730': 'Randers', '0740': 'Silkeborg',
        '0741': 'Samsø', '0746': 'Skanderborg', '0751': 'Aarhus', '0756': 'Ikast-Brande',
        '0760': 'Ringkøbing-Skjern', '0766': 'Hedensted', '0773': 'Morsø', '0779': 'Skive',
        '0787': 'Thisted', '0791': 'Viborg', '0810': 'Brønderslev', '0813': 'Frederikshavn',
        '0820': 'Vesthimmerlands', '0825': 'Læsø', '0840': 'Rebild', '0846': 'Mariagerfjord',
        '0849': 'Jammerbugt', '0851': 'Aalborg', '0860': 'Hjørring'
    }
    
    kommuner = query_df(f"""
        SELECT DISTINCT kommunekode 
        FROM {SCHEMA}.bbr_potentiale 
        WHERE kommunekode IS NOT NULL 
        ORDER BY kommunekode
    """)
    
    # Returner dict med kode som nøgle og navn som værdi
    result = {}
    for kode in kommuner['kommunekode'].tolist():
        navn = kommune_navne.get(kode, f"Kommune {kode}")
        result[kode] = f"{navn} ({kode})"
    return result

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
    # Hent antal sensorer per type i bygningen
    sensor_df = get_sensor_summary(bygning_id)
    if len(sensor_df) == 0:
        return []
    
    # Hent pris per stk fra iot_sensor_types
    try:
        pris_sql = f"""
        SELECT sensor_type, pris_min_kr, pris_max_kr
        FROM {SCHEMA}.iot_sensor_types
        """
        pris_df = query_df(pris_sql)
        pris_lookup = {row['sensor_type']: {'pris_min': float(row['pris_min_kr']), 'pris_max': float(row['pris_max_kr'])} 
                       for _, row in pris_df.iterrows()}
    except Exception:
        return []
    
    # Hent aktive kombos med deres komponent-priser
    try:
        kombo_sql = f"""
        SELECT 
            k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr,
            ARRAY_AGG(ist.sensor_type ORDER BY ist.sensor_type) AS komponenter,
            SUM(ist.pris_min_kr) AS enkelt_pris_min,
            SUM(ist.pris_max_kr) AS enkelt_pris_max
        FROM {SCHEMA}.iot_sensor_kombos k
        JOIN {SCHEMA}.kombo_komponenter kk ON kk.kombo_id = k.id
        JOIN {SCHEMA}.iot_sensor_types ist ON ist.id = kk.sensor_type_id
        WHERE k.aktiv = TRUE
        GROUP BY k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr
        """
        kombo_df = query_df(kombo_sql)
    except Exception:
        return []
    
    if len(kombo_df) == 0:
        return []
    
    # Byg sensor antal lookup (kun antal, ikke pris)
    sensor_antal = {}
    for _, row in sensor_df.iterrows():
        sensor_antal[row['sensor_type']] = int(row['antal'])
    
    # Alias: Bevægelsessensor og Tilstedeværelsessensor er ens (PIR)
    pir_aliases = ['Bevægelsessensor', 'Tilstedeværelsessensor']
    pir_antal = None
    pir_name = None
    for alias in pir_aliases:
        if alias in sensor_antal:
            pir_antal = sensor_antal[alias]
            pir_name = alias
            break
    
    # Tilføj aliaser
    if pir_antal is not None:
        for alias in pir_aliases:
            if alias not in sensor_antal:
                sensor_antal[alias] = pir_antal
    
    alternativer = []
    for _, kombo in kombo_df.iterrows():
        komponenter = kombo['komponenter']
        if komponenter is None or (hasattr(komponenter, '__len__') and len(komponenter) == 0):
            continue
        
        if hasattr(komponenter, 'tolist'):
            komponenter = komponenter.tolist()
        elif not isinstance(komponenter, list):
            komponenter = list(komponenter)
        
        # Fjern duplikater (f.eks. både Bevægelsessensor og Tilstedeværelsessensor)
        unique_komponenter = []
        has_pir = False
        for k in komponenter:
            if k in pir_aliases:
                if not has_pir:
                    has_pir = True
                    unique_komponenter.append(k)
            else:
                unique_komponenter.append(k)
        
        # Tjek om alle komponenter findes i bygningen
        matched_komponenter = []
        all_found = True
        for k in unique_komponenter:
            if k in sensor_antal:
                matched_komponenter.append(k)
            elif k in pir_aliases and pir_antal is not None:
                matched_komponenter.append(pir_name)
            else:
                all_found = False
                break
        
        if not all_found or len(matched_komponenter) == 0:
            continue
        
        # Antal kombos = minimum antal af alle komponenter
        try:
            antal = min(sensor_antal.get(k, 0) for k in matched_komponenter)
        except (ValueError, KeyError):
            continue
        if antal <= 0:
            continue
        
        # Beregn enkelt-pris per stk (sum af komponenternes priser fra iot_sensor_types)
        enkelt_pris_per_stk_min = sum(pris_lookup.get(k, {'pris_min': 0})['pris_min'] for k in matched_komponenter)
        enkelt_pris_per_stk_max = sum(pris_lookup.get(k, {'pris_max': 0})['pris_max'] for k in matched_komponenter)
        
        # Kombo-pris per stk
        kombo_pris_per_stk_min = float(kombo['pris_min_kr'])
        kombo_pris_per_stk_max = float(kombo['pris_max_kr'])
        
        # Vis hvis der er POTENTIEL besparelse (enkelt_max > kombo_min)
        if enkelt_pris_per_stk_max > kombo_pris_per_stk_min:
            alternativer.append({
                'kombo_navn': kombo['kombo_navn'],
                'erstatter': matched_komponenter,
                'antal': antal,
                'kombo_pris_min': kombo_pris_per_stk_min * antal,
                'kombo_pris_max': kombo_pris_per_stk_max * antal,
                'enkelt_pris_min': enkelt_pris_per_stk_min * antal,
                'enkelt_pris_max': enkelt_pris_per_stk_max * antal,
                'besparelse_min': (enkelt_pris_per_stk_min - kombo_pris_per_stk_max) * antal,
                'besparelse_max': (enkelt_pris_per_stk_max - kombo_pris_per_stk_min) * antal
            })
    
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
kommune_kode = None  # Til SQL queries
selected_kommune = None  # Kommune navn til visning

if filter_type == "Kommune":
    try:
        kommuner_dict = get_filter_options()
        kommune_options = [""] + list(kommuner_dict.values())
        selected_kommune = st.sidebar.selectbox("Vælg kommune", kommune_options)
        
        # Find kommunekode fra valgt navn
        if selected_kommune:
            for kode, navn in kommuner_dict.items():
                if navn == selected_kommune:
                    kommune_kode = kode
                    filter_value = kode  # Brug kode til SQL
                    break
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
elif filter_type == "Kommune" and selected_kommune:
    filter_beskrivelse = f"Kommune: {selected_kommune}"
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
    show_sensorer = st.sidebar.checkbox("Sensoroversigt", value=True)
    show_kommuner = False  # Irrelevant for enkelt bygning
    show_kort = st.sidebar.checkbox("Kort", value=True)
    show_top_bygninger = False  # Irrelevant for enkelt bygning
    show_use_cases = st.sidebar.checkbox("Use cases (detaljeret)", value=True)
    show_faciliteter = False  # Irrelevant for enkelt bygning - data vises i Bygningsoversigt
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

**Formålet** med potentialeberegneren er at give bud på mulige use cases og estimater på pris for relaterede IoT-sensorer, 
som kan give indsigt i brug og drift af bygningen. Målet er reduktion af energiforbrug, CO₂-udledning, vandforbrug m.m.
Brug menuen i venstre side til at vælge en kommune eller adresse og se data på use cases og investeringsbehov.
""")

# Ordforklaring
with st.expander("📖 Ordforklaring", expanded=False):
    st.markdown("""
    **BBR-enhed:** En enhed er f.eks. en bolig i et parcelhus, en lejlighed eller et erhvervslejemål. 
    Enfamiliehuse har typisk én enhed, mens etageejendomme har én enhed per lejlighed. 
    Hver enhed har registreret areal, anvendelse og faciliteter (toiletter, badeværelser, køkkener).
    
    **Use case:** Et konkret anvendelsesscenarie for IoT-sensorer, f.eks. "Behovsstyret ventilation via CO₂-måling" 
    eller "Lækageovervågning af vandrør".
    
    **Kombo-sensor:** En kombinationssensor der indeholder flere sensortyper i én enhed (f.eks. temperatur + luftfugtighed + CO₂). 
    Disse er typisk billigere end at købe sensorerne enkeltvis.
    """)

if detalje_mode:
    st.success(f"🔍 **Detalje-visning** for bygning: `{str(bygning_id)[:8]}...`")

# =============================================================================
# DETALJE MODE - ENKELT BYGNING
# =============================================================================

if detalje_mode and show_statistik:
    st.header("🏠 Bygningsoversigt")
    st.caption("Samlet oversigt over bygningen med faciliteter, sensorbehov og investeringsmuligheder.")
    
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
            
            # FACILITETER
            st.markdown("""
            <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; 
                        border-left: 4px solid #666; margin-bottom: 15px;">
                <p style="margin: 0; color: #333; font-weight: bold;">🏗️ Faciliteter i bygningen</p>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Enheder", f"{info['antal_enheder']:,.0f}")
            with col2:
                areal = info['samlet_areal_m2'] or 0
                st.metric("Areal", f"{areal:,.0f} m²")
            with col3:
                st.metric("Toiletter", f"{info['total_toiletter']:,.0f}")
            with col4:
                st.metric("Badeværelser", f"{info['total_badevaerelser']:,.0f}")
            with col5:
                st.metric("Køkkener", f"{info['total_koekken']:,.0f}")
        else:
            st.warning("Kunne ikke finde bygningsinfo")
            info = None
            
    except Exception as e:
        st.error(f"Kunne ikke hente bygningsinfo: {e}")
        info = None

# -----------------------------------------------------------------------------
# DETALJE MODE: SENSOROVERSIGT (rykket op - vises FØR kombo-sensorer)
# -----------------------------------------------------------------------------

if detalje_mode and show_sensorer:
    st.divider()
    st.subheader("📡 Sensoroversigt – behov per sensortype")
    st.caption("Samme sensor kan bruges til flere use cases. Antal viser det faktiske behov.")
    
    try:
        # Hent breakdown data og aggreger til unikke sensortyper
        breakdown_df = get_sensor_usecase_breakdown(bygning_id)
        
        if len(breakdown_df) > 0:
            # Aggreger til unikke sensortyper (MAX antal per type, da samme sensor bruges til flere use cases)
            # Priserne i breakdown_df er ALLEREDE totaler, så vi skal ikke gange igen
            sensor_summary = breakdown_df.groupby('sensor_type').agg({
                'antal_sensorer': 'max',  # MAX fordi samme sensor bruges til flere use cases
                'pris_min': 'max',        # MAX af totalpris (da den allerede er antal × stykpris)
                'pris_max': 'max',        # MAX af totalpris
                'use_case_navn': lambda x: ', '.join(sorted(set(x)))
            }).reset_index()
            
            sensor_summary.columns = ['Sensortype', 'Antal', 'Pris total min', 'Pris total max', 'Use cases']
            sensor_summary['Pris (min-max)'] = sensor_summary.apply(
                lambda r: f"{r['Pris total min']:,.0f} - {r['Pris total max']:,.0f} kr", axis=1
            )
            sensor_summary = sensor_summary.sort_values('Antal', ascending=False)
            
            # Hovedtabel
            st.dataframe(
                sensor_summary[['Sensortype', 'Antal', 'Pris (min-max)', 'Use cases']],
                hide_index=True,
                use_container_width=True,
                height=min(400, 50 + len(sensor_summary) * 35)
            )
            
            # Fodnoter
            st.caption("""
            **Fodnoter:**  
            ¹ *CO₂-måler:* Antal beregnet ud fra 1 sensor per 500 m² – justeres efter faktiske forhold.  
            ² *Bevægelsessensor:* Antal beregnet ud fra 1 sensor per 100 m² – justeres efter faktiske forhold.
            """)
            
            # Samlet estimat - UDEN at gange med antal (priserne er allerede totaler)
            total_sensorer = sensor_summary['Antal'].sum()
            total_pris_min = sensor_summary['Pris total min'].sum()
            total_pris_max = sensor_summary['Pris total max'].sum()
            
            st.info(f"""
            **Samlet for separate enkelt-sensorer:** {total_sensorer:.0f} sensorer | {total_pris_min:,.0f} - {total_pris_max:,.0f} kr  
            *Se "Kombo-sensorer" nedenfor for lavere investering.*
            """)
            
        else:
            st.info("Ingen sensordata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente sensordata: {e}")

# -----------------------------------------------------------------------------
# DETALJE MODE: KOMBO-SENSORER (rykket ned - vises EFTER sensoroversigt)
# -----------------------------------------------------------------------------

if detalje_mode and show_statistik:
    st.divider()
    st.subheader("💰 Kombo-sensorer – den bedste investering")
    st.caption("Kombinationssensorer dækker flere funktioner i én enhed og giver lavere samlet investering.")
    
    try:
        kombos = get_kombo_alternativer(bygning_id)
        
        if isinstance(kombos, dict) and 'error' in kombos:
            st.warning(f"Kombo-beregning fejlede: {kombos['error']}")
            st.caption("Kør `kombo_sensorer.sql` i databasen for at aktivere.")
        elif kombos and len(kombos) > 0:
            # Beregn samlet investering for kombo-sensorer
            total_kombo_min = sum(k['kombo_pris_min'] for k in kombos)
            total_kombo_max = sum(k['kombo_pris_max'] for k in kombos)
            total_besparelse = sum(k['besparelse_max'] for k in kombos)
            antal_kombos = len(kombos)
            
            # Fremhævet investerings-boks
            st.markdown("""
            <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; 
                        border-left: 4px solid #2e7d32; margin-bottom: 15px;">
                <p style="margin: 0; color: #1b5e20; font-weight: bold;">✅ Anbefalet investering med kombo-sensorer</p>
            </div>
            """, unsafe_allow_html=True)
            
            col_inv1, col_inv2, col_inv3 = st.columns(3)
            with col_inv1:
                st.metric("Investering (kombo)", f"{total_kombo_min:,.0f} - {total_kombo_max:,.0f} kr")
            with col_inv2:
                st.metric("Antal kombo-sensorer", f"{antal_kombos}")
            with col_inv3:
                st.metric("Besparelse vs. enkelt", f"{total_besparelse:,.0f} kr", delta=f"-{total_besparelse:,.0f} kr")
            
            st.info("""
            **Sådan læses tabellen:**
            - **Erstatter**: De sensortyper som kombo-sensoren erstatter
            - **Kombo-pris**: Prisen for kombinationssensoren
            - **Besparelse**: Hvad du sparer vs. at købe enkelt-sensorer
            """)
            
            # Kombo tabel MED erstatter-info
            kombo_df = pd.DataFrame(kombos)
            
            # Tilføj "Erstatter" kolonne fra 'erstatter' listen
            kombo_df['Erstatter'] = kombo_df['erstatter'].apply(
                lambda x: ', '.join(x) if isinstance(x, list) else str(x)
            )
            
            kombo_display = kombo_df[['kombo_navn', 'antal', 'Erstatter', 'enkelt_pris_max', 'kombo_pris_max', 'besparelse_max']].copy()
            kombo_display.columns = ['Kombo-sensor', 'Antal', 'Erstatter (sensortyper)', 'Enkelt-pris', 'Kombo-pris', 'Besparelse']
            kombo_display['Enkelt-pris'] = kombo_display['Enkelt-pris'].apply(lambda x: f"{x:,.0f} kr")
            kombo_display['Kombo-pris'] = kombo_display['Kombo-pris'].apply(lambda x: f"{x:,.0f} kr")
            kombo_display['Besparelse'] = kombo_display['Besparelse'].apply(lambda x: f"{x:,.0f} kr")
            
            st.dataframe(kombo_display, hide_index=True, use_container_width=True, height=min(350, 50 + len(kombo_display) * 35))
            
            # Samlet besparelse med mere detalje
            kombo_liste = ', '.join([f"{k['kombo_navn']} ({k['antal']} stk)" for k in kombos])
            st.success(f"""
            💰 **Samlet potentiel besparelse:** {total_besparelse:,.0f} kr  
            *Ved at bruge: {kombo_liste}*
            """)
            
            # Forklaring
            with st.expander("⚠️ Vigtigt om besparelsesberegningen"):
                st.markdown("""
                **Hvorfor kan besparelserne ikke altid summeres direkte?**
                
                Flere kombo-sensorer kan indeholde de samme sensortyper. For eksempel:
                - "Temperatur + Luftfugtighed" indeholder temperaturføler
                - "Temperatur + CO2" indeholder også temperaturføler
                
                Hvis du vælger begge, får du **to** temperaturfølere – men har måske kun brug for **én**.
                
                **Anbefaling:** Vælg den kombo-sensor der bedst matcher dit behov, eller kontakt en rådgiver.
                """)
        else:
            # Ingen kombo-sensorer matcher
            if info is not None:
                st.markdown("""
                <div style="background: #fff3e0; padding: 15px; border-radius: 8px; 
                            border-left: 4px solid #ff9800; margin-bottom: 15px;">
                    <p style="margin: 0; color: #e65100; font-weight: bold;">💡 Ingen kombo-sensorer matcher</p>
                </div>
                """, unsafe_allow_html=True)
                
                st.info("Bygningens sensortyper matcher ikke tilgængelige kombo-sensorer. Se Sensoroversigt ovenfor for enkelt-sensor investering.")
                
    except Exception as e:
        st.warning(f"Kombo-beregning fejlede: {e}")
        st.caption("Kør `kombo_sensorer.sql` i databasen for at aktivere.")

# -----------------------------------------------------------------------------
# DETALJE MODE: USE CASES (simplificeret - uden dublet-graf)
# -----------------------------------------------------------------------------

if detalje_mode and show_use_cases:
    st.header("💡 Use Cases")
    st.caption("IoT use cases identificeret for bygningen.")
    
    try:
        usecase_df = get_usecase_summary(bygning_id)
        
        if len(usecase_df) > 0:
            # Aggreger til unikke use cases (fjern sensor-dubletter)
            usecase_summary = usecase_df.groupby(['use_case_navn', 'kategori']).agg({
                'antal_enheder': 'first'
            }).reset_index()
            
            # Vis tabel direkte (uden graf med misvisende sensor-tal)
            st.markdown("""
            <div style="background: #fff8e1; padding: 15px; border-radius: 8px; 
                        border-left: 4px solid #ffc107; margin-bottom: 15px;">
                <p style="margin: 0; color: #f57f17; font-weight: bold;">💡 Identificerede use cases for bygningen</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.dataframe(
                usecase_summary.rename(columns={
                    'use_case_navn': 'Use Case',
                    'kategori': 'Kategori',
                    'antal_enheder': 'Antal enheder'
                }),
                hide_index=True,
                use_container_width=True,
                height=400
            )
            
            st.caption(f"*{len(usecase_summary)} use cases identificeret. Se Sensoroversigt for hvilke sensorer der kræves.*")
        else:
            st.info("Ingen use case data fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente use case data: {e}")

# -----------------------------------------------------------------------------
# DETALJE MODE: SENSOR/USE CASE BREAKDOWN (simplificeret)
# -----------------------------------------------------------------------------

if detalje_mode and show_sensor_usecase_breakdown:
    st.header("🔗 Sensor/Use Case Matrix")
    st.caption("Viser hvilke sensorer der bruges til hvilke use cases. Samme sensor kan dække flere use cases.")
    
    try:
        breakdown_df = get_sensor_usecase_breakdown(bygning_id)
        
        if len(breakdown_df) > 0:
            # Pivot tabel med MAX (ikke sum, da samme sensor bruges til flere)
            pivot_df = breakdown_df.pivot_table(
                index='use_case_navn',
                columns='sensor_type',
                values='antal_sensorer',
                fill_value=0,
                aggfunc='max'  # MAX fordi samme sensor bruges til flere use cases
            )
            
            # Heatmap
            fig_heatmap = px.imshow(
                pivot_df,
                labels=dict(x="Sensortype", y="Use Case", color="Antal"),
                title="Sensor/Use Case Matrix",
                color_continuous_scale='Blues',
                aspect='auto'
            )
            fig_heatmap.update_layout(height=500)
            st.plotly_chart(fig_heatmap, use_container_width=True)
            
        else:
            st.info("Ingen breakdown data fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente breakdown: {e}")

# =============================================================================
# OVERBLIK MODE - ALLE/KOMMUNE FILTER
# =============================================================================

if not detalje_mode and show_statistik:
    # Markant header for kommune/alle
    if filter_type == "Kommune" and filter_value:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #2e7d32 0%, #4caf50 100%); 
                    padding: 25px; border-radius: 12px; margin-bottom: 20px;">
            <h1 style="color: white; margin: 0; font-size: 2em;">📈 Statistik for {selected_kommune or filter_value}</h1>
            <p style="color: #c8e6c9; margin: 10px 0 0 0; font-size: 1.1em;">
                Aggregerede nøgletal for alle bygninger i kommunen
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.header("📈 Overordnet Statistik")
        st.caption("Aggregerede nøgletal for alle bygninger i det valgte filter.")
    
    try:
        statistik = get_statistik(filter_clause)
        
        # Hovedtal i fremhævet boks
        st.markdown("""
        <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; 
                    border-left: 4px solid #2e7d32; margin-bottom: 15px;">
            <p style="margin: 0; color: #1b5e20; font-weight: bold;">📊 Nøgletal for separate sensorer</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Bygninger", f"{statistik['antal_bygninger'].iloc[0]:,.0f}")
        with col2:
            st.metric("Enheder", f"{statistik['antal_enheder'].iloc[0]:,.0f}")
        with col3:
            st.metric("Sensorer", f"{statistik['total_sensorer'].iloc[0]:,.0f}")
        with col4:
            st.metric("Investering (max)", f"{statistik['total_investering_max'].iloc[0]:,.0f} kr")
        
        col5, col6 = st.columns(2)
        with col5:
            st.metric("Investering (min)", f"{statistik['total_investering_min'].iloc[0]:,.0f} kr")
        with col6:
            pass  # Tom kolonne for balance
        
        # Forklaring af tallene
        st.info("""
        **💡 Om tallene:** Ovenstående investering er baseret på **separate enkelt-sensorer** – én sensor per funktion. 
        Tallene viser hvad det ville koste, hvis hver sensortype købes individuelt.
        
        **Lavere investering mulig:** Ved at bruge **kombo-sensorer** (kombinationssensorer) kan den samlede investering 
        reduceres væsentligt. Vælg en specifik adresse i menuen for at se konkrete kombo-sensorer og besparelsesmuligheder.
        """)
        
        # Info om kombo-sensorer
        with st.expander("ℹ️ Hvad er en kombo-sensor?", expanded=False):
            st.markdown("""
            En **kombo-sensor** (kombinationssensor) er en IoT-enhed der indeholder flere sensortyper i samme fysiske enhed.
            
            **Eksempel:**
            - 4 separate sensorer: Temperatur (300 kr) + Luftfugtighed (400 kr) + CO₂ (800 kr) + PIR (400 kr) = **1.900 kr**
            - 1 kombo-sensor med alle 4 funktioner = **1.200-1.300 kr**
            - **Besparelse: ca. 600-700 kr per enhed**
            
            Kombo-sensorer giver typisk:
            - ✅ Lavere samlet investering
            - ✅ Færre enheder at installere og vedligeholde
            - ✅ Samme funktionalitet som enkelt-sensorer
            
            Vælg en specifik adresse for at se tilgængelige kombo-sensorer.
            """)
            
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
