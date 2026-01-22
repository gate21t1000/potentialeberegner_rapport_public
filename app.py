"""
Potentialeberegner - IoT Investeringsrapport
Streamlit App til visualisering af BBR-data og investeringspotentiale
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

def build_filter_clause(filter_type, filter_value, use_bygning_view=False):
    """Bygger WHERE clause baseret på filter"""
    if filter_type == 'Alle' or not filter_value:
        return ''
    
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

# =============================================================================
# CACHED DATA FUNCTIONS
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
    """Hent sensor data"""
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
    """Hent use case data"""
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
    filter_value = st.sidebar.text_input("Søg adresse", placeholder="f.eks. Vestergade")
elif filter_type == "Bygning ID":
    filter_value = st.sidebar.text_input("Bygning ID", placeholder="UUID")

# Byg filter clauses
filter_clause = build_filter_clause(filter_type, filter_value, use_bygning_view=False)
filter_clause_view = build_filter_clause(filter_type, filter_value, use_bygning_view=True)

# Filter beskrivelse
if filter_type == "Alle":
    filter_beskrivelse = "Alle bygninger"
elif filter_value:
    filter_beskrivelse = f"{filter_type}: {filter_value}"
else:
    filter_beskrivelse = "Alle bygninger"

st.sidebar.divider()

st.sidebar.header("📊 Sektioner")

show_statistik = st.sidebar.checkbox("Overordnet statistik", value=True)
show_anvendelse = st.sidebar.checkbox("Anvendelsestyper", value=True)
show_sensorer = st.sidebar.checkbox("Sensoroversigt", value=True)
show_kommuner = st.sidebar.checkbox("Kommuneoversigt", value=True)
show_kort = st.sidebar.checkbox("Kort", value=True)
show_top_bygninger = st.sidebar.checkbox("Top bygninger", value=True)
show_use_cases = st.sidebar.checkbox("Use cases", value=True)
show_faciliteter = st.sidebar.checkbox("Faciliteter", value=True)

# =============================================================================
# MAIN CONTENT
# =============================================================================

st.title("🏢 IoT Investeringspotentiale")
st.caption(f"Rapport genereret: {datetime.now().strftime('%d-%m-%Y %H:%M')} | Filter: {filter_beskrivelse}")

# -----------------------------------------------------------------------------
# STATISTIK
# -----------------------------------------------------------------------------

if show_statistik:
    st.header("📈 Overordnet Statistik")
    
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
# ANVENDELSE
# -----------------------------------------------------------------------------

if show_anvendelse:
    st.header("🏛️ Investering per Anvendelsestype")
    
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
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with col2:
                fig_pie = px.pie(
                    anvendelse_df.head(10),
                    values='antal_bygninger',
                    names='anvendelse',
                    title='Fordeling af bygninger (Top 10)',
                    hole=0.4
                )
                fig_pie.update_layout(height=500)
                st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Ingen data fundet for dette filter")
            
    except Exception as e:
        st.error(f"Kunne ikke hente anvendelsesdata: {e}")

# -----------------------------------------------------------------------------
# SENSORER
# -----------------------------------------------------------------------------

if show_sensorer:
    st.header("📡 Sensoroversigt")
    
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
            st.plotly_chart(fig_sensor, use_container_width=True)
        else:
            st.info("Ingen sensordata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente sensordata: {e}")

# -----------------------------------------------------------------------------
# KOMMUNER
# -----------------------------------------------------------------------------

if show_kommuner:
    st.header("🗺️ Kommuneoversigt")
    
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
            st.plotly_chart(fig_kommune, use_container_width=True)
        else:
            st.info("Ingen kommunedata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente kommunedata: {e}")

# -----------------------------------------------------------------------------
# KORT
# -----------------------------------------------------------------------------

if show_kort:
    st.header("🗺️ Kort over bygninger")
    
    try:
        gdf = get_geodata(filter_clause_view)
        
        if len(gdf) > 0:
            # Konverter til WGS84
            gdf = gdf.to_crs(epsg=4326)
            
            # Beregn center
            center_lat = gdf.geometry.centroid.y.mean()
            center_lon = gdf.geometry.centroid.x.mean()
            
            # Juster zoom baseret på filter
            if filter_type == 'Bygning ID' and filter_value:
                zoom = 16
            elif filter_type == 'Adresse' and filter_value:
                zoom = 14
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
            
            # Tilføj markers
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
                
                popup_html = f"""
                <b>{row['adresse'] or 'Ukendt adresse'}</b><br>
                <b>Anvendelse:</b> {row['anvendelsestyper']}<br>
                <b>Enheder:</b> {row['antal_enheder']}<br>
                <b>Sensorer:</b> {row['total_sensorer']}<br>
                <b>Investering:</b> {row['investering_min_kr']:,.0f} - {row['investering_max_kr']:,.0f} kr
                """
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    weight=1,
                    popup=folium.Popup(popup_html, max_width=300)
                ).add_to(m)
            
            # Vis kort
            st_folium(m, width=None, height=500, use_container_width=True)
            
            st.caption(f"Viser {len(gdf)} bygninger (max {KORT_MAX_PUNKTER})")
        else:
            st.info("Ingen bygninger med geometri fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente kortdata: {e}")

# -----------------------------------------------------------------------------
# TOP BYGNINGER
# -----------------------------------------------------------------------------

if show_top_bygninger:
    st.header("🏆 Top 20 Bygninger")
    
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
                use_container_width=True
            )
        else:
            st.info("Ingen bygninger fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente top bygninger: {e}")

# -----------------------------------------------------------------------------
# USE CASES
# -----------------------------------------------------------------------------

if show_use_cases:
    st.header("💡 Use Cases")
    
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
            st.plotly_chart(fig_usecase, use_container_width=True)
        else:
            st.info("Ingen use case data fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente use case data: {e}")

# -----------------------------------------------------------------------------
# FACILITETER
# -----------------------------------------------------------------------------

if show_faciliteter:
    st.header("🚿 Faciliteter")
    
    try:
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
            
            st.plotly_chart(fig_facilitet, use_container_width=True)
        else:
            st.info("Ingen facilitetdata fundet")
            
    except Exception as e:
        st.error(f"Kunne ikke hente facilitetdata: {e}")

# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.caption("Potentialeberegner v2 | Data fra BBR")
