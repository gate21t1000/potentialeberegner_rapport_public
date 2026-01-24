-- ============================================================================
-- POTENTIALEBEREGNER v2 - GRAFANA QUERIES (Version 8.5.2)
-- ============================================================================
-- Formål: Investeringsoversigt - antal sensorer og prisspænd
-- Koordinater transformeres fra EPSG:25832 (UTM32N) til WGS84 (lat/lng)
-- ============================================================================


-- ============================================================================
-- QUERY 1: Enheder med størst investeringsbehov (Top 20)
-- ============================================================================
-- Grafana: Geomap, Table, Bar gauge
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh026_enhedenssamledeareal AS areal_m2,
    bp.antal_toiletter,
    bp.antal_badevaerelser,
    bp.antal_koekken,
    bp.antal_use_cases,
    bp.total_antal_sensorer,
    bp.samlet_investering_min_kr AS investering_min,
    bp.samlet_investering_max_kr AS investering_max,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.the_geom IS NOT NULL
  AND bp.total_antal_sensorer > 0
ORDER BY bp.samlet_investering_max_kr DESC
LIMIT 20;


-- ============================================================================
-- QUERY 2: Enheder med specifik use case
-- ============================================================================
-- Grafana: Geomap, Table
-- Variabel: Erstat use case navn med Grafana-variabel ${use_case}
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh026_enhedenssamledeareal AS areal_m2,
    bp.total_antal_sensorer,
    bp.samlet_investering_min_kr AS investering_min,
    bp.samlet_investering_max_kr AS investering_max,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.use_cases @> '[{"navn": "Behovsstyret ventilation via CO2-måling"}]'
  AND bp.the_geom IS NOT NULL;


-- ============================================================================
-- QUERY 3: Enheder der kræver specifik sensortype
-- ============================================================================
-- Grafana: Geomap, Table
-- Variabel: Erstat sensortype med Grafana-variabel ${sensor_type}
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh026_enhedenssamledeareal AS areal_m2,
    (SELECT SUM((s->>'antal')::INTEGER) 
     FROM jsonb_array_elements(bp.iot_sensorer) s 
     WHERE s->>'type' = 'CO2-måler') AS antal_af_sensor,
    bp.total_antal_sensorer,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.iot_sensorer @> '[{"type": "CO2-måler"}]'
  AND bp.the_geom IS NOT NULL;


-- ============================================================================
-- QUERY 4: Detaljeret use case oversigt (alle enheder, udfoldet)
-- ============================================================================
-- Grafana: Table, Pie chart (grupperet på kategori)
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    uc_elem->>'navn' AS use_case_navn,
    uc_elem->>'kategori' AS kategori,
    (uc_elem->>'relevans')::INTEGER AS relevans,
    uc_elem->>'link' AS link,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.use_cases) AS uc_elem
WHERE bp.the_geom IS NOT NULL
  AND jsonb_array_length(bp.use_cases) > 0;


-- ============================================================================
-- QUERY 5: Sensor-oversigt med antal og priser (alle enheder, udfoldet)
-- ============================================================================
-- Grafana: Table, Bar chart
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    sensor_elem->>'type' AS sensor_type,
    (sensor_elem->>'antal')::INTEGER AS antal,
    (sensor_elem->>'pris_min')::NUMERIC AS stk_pris_min,
    (sensor_elem->>'pris_max')::NUMERIC AS stk_pris_max,
    (sensor_elem->>'pris_total_min')::NUMERIC AS total_pris_min,
    (sensor_elem->>'pris_total_max')::NUMERIC AS total_pris_max,
    (sensor_elem->>'er_primaer')::BOOLEAN AS er_primaer,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
WHERE bp.the_geom IS NOT NULL
  AND jsonb_array_length(bp.iot_sensorer) > 0;


-- ============================================================================
-- QUERY 6: Enheder per anvendelsestype (til tematisk kort)
-- ============================================================================
-- Grafana: Geomap (farvekodet efter anvendelse), Table
-- Variabel: Erstat anvendelse med Grafana-variabel ${anvendelse}
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh026_enhedenssamledeareal AS areal_m2,
    bp.antal_toiletter,
    bp.antal_badevaerelser,
    bp.antal_koekken,
    bp.antal_use_cases,
    bp.total_antal_sensorer,
    bp.samlet_investering_min_kr AS investering_min,
    bp.samlet_investering_max_kr AS investering_max,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.enh020_enhedens_anvendelse_txt = 'Daginstitution'
  AND bp.the_geom IS NOT NULL;


-- ============================================================================
-- QUERY 7: Enheder per kommune
-- ============================================================================
-- Grafana: Geomap, Table
-- Variabel: Erstat kommunekode med Grafana-variabel ${kommune}
-- ============================================================================

SELECT 
    bp.id,
    bp.kommunekode,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh026_enhedenssamledeareal AS areal_m2,
    bp.total_antal_sensorer,
    bp.samlet_investering_min_kr AS investering_min,
    bp.samlet_investering_max_kr AS investering_max,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.kommunekode = '0265'
  AND bp.the_geom IS NOT NULL
ORDER BY bp.samlet_investering_max_kr DESC;


-- ============================================================================
-- QUERY 8: Aggregeret data per lokation (til heatmap)
-- ============================================================================
-- Grafana: Geomap (heatmap layer), Table
-- ============================================================================

SELECT 
    COUNT(*) AS antal_enheder,
    SUM(bp.total_antal_sensorer) AS total_sensorer,
    SUM(bp.samlet_investering_min_kr) AS investering_min,
    SUM(bp.samlet_investering_max_kr) AS investering_max,
    SUM(bp.antal_toiletter) AS total_toiletter,
    SUM(bp.antal_badevaerelser) AS total_badevaerelser,
    SUM(bp.antal_koekken) AS total_koekken,
    STRING_AGG(DISTINCT bp.enh020_enhedens_anvendelse_txt, ', ') AS anvendelsestyper,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.the_geom IS NOT NULL
GROUP BY ST_Centroid(bp.the_geom)
HAVING SUM(bp.total_antal_sensorer) > 0;


-- ============================================================================
-- QUERY 9: Enheder med faciliteter (toiletter, badeværelser, køkkener)
-- ============================================================================
-- Grafana: Geomap, Table
-- Formål: Vis enheder med specifikke faciliteter
-- ============================================================================

SELECT 
    bp.id,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh032_toiletforhold_txt AS toiletforhold,
    bp.enh034_koekkenforhold_txt AS koekkenforhold,
    bp.antal_toiletter,
    bp.antal_badevaerelser,
    bp.antal_koekken,
    bp.total_antal_sensorer,
    bp.samlet_investering_min_kr AS investering_min,
    bp.samlet_investering_max_kr AS investering_max,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.the_geom IS NOT NULL
  AND (bp.antal_toiletter > 0 OR bp.antal_badevaerelser > 0 OR bp.antal_koekken > 0);


-- ============================================================================
-- QUERY 10: Komplet datasæt til Geomap med investeringsniveau
-- ============================================================================
-- Grafana: Geomap (markers layer med tooltip)
-- ============================================================================

SELECT 
    bp.id,
    bp.id_lokalid,
    bp.kommunekode,
    bp.adressebetegnelse AS adresse,
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    bp.enh026_enhedenssamledeareal AS areal_m2,
    bp.antal_toiletter,
    bp.antal_badevaerelser,
    bp.antal_koekken,
    bp.antal_use_cases,
    bp.antal_sensor_typer,
    bp.total_antal_sensorer,
    bp.samlet_investering_min_kr AS investering_min,
    bp.samlet_investering_max_kr AS investering_max,
    -- Metric til farvekodning i Geomap
    CASE 
        WHEN bp.samlet_investering_max_kr >= 50000 THEN 'Høj (50.000+ kr)'
        WHEN bp.samlet_investering_max_kr >= 20000 THEN 'Medium (20.000-50.000 kr)'
        WHEN bp.samlet_investering_max_kr > 0 THEN 'Lav (< 20.000 kr)'
        ELSE 'Ingen'
    END AS investerings_niveau,
    ST_Y(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bp.the_geom), 4326)) AS longitude
FROM bbr_potentiale bp
WHERE bp.the_geom IS NOT NULL;


-- ============================================================================
-- SUPPLERENDE QUERIES TIL GRAFANA VARIABLER
-- ============================================================================

-- Liste over anvendelser (til dropdown)
SELECT DISTINCT 
    bp.enh020_enhedens_anvendelse_txt AS __value,
    bp.enh020_enhedens_anvendelse_txt AS __text
FROM bbr_potentiale bp
WHERE bp.enh020_enhedens_anvendelse_txt IS NOT NULL
ORDER BY bp.enh020_enhedens_anvendelse_txt;

-- Liste over kommuner (til dropdown)
SELECT DISTINCT 
    bp.kommunekode AS __value,
    bp.kommunekode AS __text
FROM bbr_potentiale bp
WHERE bp.kommunekode IS NOT NULL
ORDER BY bp.kommunekode;

-- Liste over use cases (til dropdown)
SELECT DISTINCT 
    uc.use_case_navn AS __value,
    uc.use_case_navn AS __text
FROM use_cases uc
ORDER BY uc.use_case_navn;

-- Liste over sensortyper (til dropdown)
SELECT DISTINCT 
    ist.sensor_type AS __value,
    ist.sensor_type AS __text
FROM iot_sensor_types ist
WHERE ist.aktiv = TRUE
ORDER BY ist.sensor_type;

-- Liste over kategorier (til dropdown)
SELECT DISTINCT 
    uc.kategori AS __value,
    uc.kategori AS __text
FROM use_cases uc
WHERE uc.kategori IS NOT NULL
ORDER BY uc.kategori;


-- ============================================================================
-- AGGREGEREDE QUERIES TIL DASHBOARD STATISTIK
-- ============================================================================

-- STAT: Samlet investeringsoversigt
SELECT 
    COUNT(*) AS antal_enheder,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(antal_use_cases) AS total_use_cases,
    SUM(samlet_investering_min_kr) AS total_investering_min,
    SUM(samlet_investering_max_kr) AS total_investering_max,
    SUM(antal_toiletter) AS total_toiletter,
    SUM(antal_badevaerelser) AS total_badevaerelser,
    SUM(antal_koekken) AS total_koekken
FROM bbr_potentiale
WHERE total_antal_sensorer > 0;


-- STAT: Investering per anvendelsestype
SELECT 
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    COUNT(*) AS antal_enheder,
    SUM(bp.total_antal_sensorer) AS total_sensorer,
    SUM(bp.samlet_investering_min_kr) AS investering_min,
    SUM(bp.samlet_investering_max_kr) AS investering_max
FROM bbr_potentiale bp
WHERE bp.enh020_enhedens_anvendelse_txt IS NOT NULL
GROUP BY bp.enh020_enhedens_anvendelse_txt
ORDER BY investering_max DESC;


-- STAT: Investering per kategori
SELECT 
    uc_elem->>'kategori' AS kategori,
    COUNT(DISTINCT bp.id) AS antal_enheder
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.use_cases) AS uc_elem
GROUP BY uc_elem->>'kategori'
ORDER BY antal_enheder DESC;


-- STAT: Top 10 mest anvendte sensorer med priser
SELECT 
    sensor_elem->>'type' AS sensor_type,
    COUNT(DISTINCT bp.id) AS antal_enheder,
    SUM((sensor_elem->>'antal')::INTEGER) AS total_antal,
    SUM((sensor_elem->>'pris_total_min')::NUMERIC) AS total_pris_min,
    SUM((sensor_elem->>'pris_total_max')::NUMERIC) AS total_pris_max
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
GROUP BY sensor_elem->>'type'
ORDER BY total_antal DESC
LIMIT 10;


-- STAT: Top 10 mest anvendte use cases
SELECT 
    uc_elem->>'navn' AS use_case,
    uc_elem->>'kategori' AS kategori,
    COUNT(DISTINCT bp.id) AS antal_enheder
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.use_cases) AS uc_elem
GROUP BY uc_elem->>'navn', uc_elem->>'kategori'
ORDER BY antal_enheder DESC
LIMIT 10;


-- STAT: Investering per kommune
SELECT 
    bp.kommunekode,
    COUNT(*) AS antal_enheder,
    SUM(bp.total_antal_sensorer) AS total_sensorer,
    SUM(bp.samlet_investering_min_kr) AS investering_min,
    SUM(bp.samlet_investering_max_kr) AS investering_max
FROM bbr_potentiale bp
WHERE bp.kommunekode IS NOT NULL
GROUP BY bp.kommunekode
ORDER BY investering_max DESC;


-- STAT: Facilitet-oversigt
SELECT 
    bp.enh020_enhedens_anvendelse_txt AS anvendelse,
    COUNT(*) AS antal_enheder,
    SUM(bp.antal_toiletter) AS total_toiletter,
    SUM(bp.antal_badevaerelser) AS total_badevaerelser,
    SUM(bp.antal_koekken) AS total_koekken
FROM bbr_potentiale bp
WHERE bp.enh020_enhedens_anvendelse_txt IS NOT NULL
GROUP BY bp.enh020_enhedens_anvendelse_txt
ORDER BY (SUM(bp.antal_toiletter) + SUM(bp.antal_badevaerelser) + SUM(bp.antal_koekken)) DESC;


-- ============================================================================
-- GRAFANA GEOMAP KONFIGURATION
-- ============================================================================
-- KOMBO-SENSORER QUERIES
-- ============================================================================

-- QUERY: Kombo oversigt
-- Viser alle tilgængelige kombinationssensorer
SELECT 
    k.kombo_navn,
    k.pris_min_kr,
    k.pris_max_kr,
    k.aktiv,
    STRING_AGG(ist.sensor_type, ' + ' ORDER BY ist.sensor_type) AS komponenter,
    COUNT(kk.sensor_type_id) AS antal_komponenter,
    SUM(ist.pris_min_kr) AS enkelt_pris_min_sum,
    SUM(ist.pris_max_kr) AS enkelt_pris_max_sum,
    SUM(ist.pris_max_kr) - k.pris_min_kr AS max_besparelse_per_stk
FROM iot_sensor_kombos k
JOIN kombo_komponenter kk ON kk.kombo_id = k.id
JOIN iot_sensor_types ist ON ist.id = kk.sensor_type_id
WHERE k.aktiv = TRUE
GROUP BY k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr, k.aktiv
ORDER BY max_besparelse_per_stk DESC;


-- ============================================================================
-- GRAFANA GEOMAP OPSÆTNING
-- ============================================================================
-- 
-- For at bruge disse queries i Grafana Geomap:
--
-- 1. Opret nyt panel → Vælg "Geomap"
-- 
-- 2. Under "Query" tab:
--    - Vælg din PostgreSQL data source
--    - Indsæt en af queries ovenfor
--    - Sæt Format til "Table"
--
-- 3. Under "Panel options" → "Data layer":
--    - Layer type: "Markers" eller "Heatmap"
--    - Location: "Coords"
--    - Latitude field: "latitude"
--    - Longitude field: "longitude"
--
-- 4. For Markers layer:
--    - Size: Kan sættes til "total_antal_sensorer" for varierende størrelse
--    - Color: Kan sættes til "investerings_niveau" for kategorisering
--
-- 5. For tooltips:
--    - Tilføj felter: adresse, anvendelse, total_antal_sensorer, 
--      investering_min, investering_max
--
-- ============================================================================
