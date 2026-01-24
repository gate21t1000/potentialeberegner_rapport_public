-- ============================================================================
-- POTENTIALEBEREGNER v2 - BYGNINGS-VIEWS
-- ============================================================================
-- Tilføj disse views til din database efter kørsel af potentialeberegner_v2.sql
-- ============================================================================


-- -----------------------------------------------------------------------------
-- VIEW: Samlet statistik på bygningsniveau
-- -----------------------------------------------------------------------------
-- Viser aggregerede tal per unik bygning
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_investering_per_bygning CASCADE;

CREATE OR REPLACE VIEW v_investering_per_bygning AS
SELECT 
    bygning AS bygning_id,
    COUNT(*) AS antal_enheder,
    SUM(enh026_enhedenssamledeareal) AS samlet_areal_m2,
    STRING_AGG(DISTINCT enh020_enhedens_anvendelse_txt, ', ') AS anvendelsestyper,
    MAX(kommunekode) AS kommunekode,
    MAX(adressebetegnelse) AS adresse,
    SUM(antal_toiletter) AS total_toiletter,
    SUM(antal_badevaerelser) AS total_badevaerelser,
    SUM(antal_koekken) AS total_koekken,
    SUM(antal_use_cases) AS total_use_cases,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS investering_min_kr,
    SUM(samlet_investering_max_kr) AS investering_max_kr,
    -- Beregn gennemsnit per enhed i bygningen
    ROUND(AVG(total_antal_sensorer), 1) AS gns_sensorer_per_enhed,
    ROUND(AVG(samlet_investering_max_kr), 0) AS gns_investering_per_enhed,
    -- Investeringsniveau til farvekodning
    CASE 
        WHEN SUM(samlet_investering_max_kr) >= 100000 THEN 'Meget høj (100.000+ kr)'
        WHEN SUM(samlet_investering_max_kr) >= 50000 THEN 'Høj (50.000-100.000 kr)'
        WHEN SUM(samlet_investering_max_kr) >= 20000 THEN 'Medium (20.000-50.000 kr)'
        WHEN SUM(samlet_investering_max_kr) > 0 THEN 'Lav (< 20.000 kr)'
        ELSE 'Ingen'
    END AS investerings_niveau
FROM bbr_potentiale
WHERE bygning IS NOT NULL
GROUP BY bygning
ORDER BY investering_max_kr DESC;


-- -----------------------------------------------------------------------------
-- VIEW: Bygningsoversigt med geometri (til Grafana Geomap)
-- -----------------------------------------------------------------------------
-- Tager én repræsentativ geometri per bygning (første enhed)
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_bygning_geomap CASCADE;

CREATE OR REPLACE VIEW v_bygning_geomap AS
WITH bygning_stats AS (
    SELECT 
        bygning AS bygning_id,
        COUNT(*) AS antal_enheder,
        SUM(enh026_enhedenssamledeareal) AS samlet_areal_m2,
        STRING_AGG(DISTINCT enh020_enhedens_anvendelse_txt, ', ') AS anvendelsestyper,
        MAX(kommunekode) AS kommunekode,
        MAX(adressebetegnelse) AS adresse,
        SUM(antal_toiletter) AS total_toiletter,
        SUM(antal_badevaerelser) AS total_badevaerelser,
        SUM(antal_koekken) AS total_koekken,
        SUM(total_antal_sensorer) AS total_sensorer,
        SUM(samlet_investering_min_kr) AS investering_min_kr,
        SUM(samlet_investering_max_kr) AS investering_max_kr
    FROM bbr_potentiale
    WHERE bygning IS NOT NULL
    GROUP BY bygning
),
bygning_geom AS (
    SELECT DISTINCT ON (bygning)
        bygning,
        the_geom
    FROM bbr_potentiale
    WHERE bygning IS NOT NULL
      AND the_geom IS NOT NULL
    ORDER BY bygning, id
)
SELECT 
    bs.bygning_id,
    bs.antal_enheder,
    bs.samlet_areal_m2,
    bs.anvendelsestyper,
    bs.kommunekode,
    bs.adresse,
    bs.total_toiletter,
    bs.total_badevaerelser,
    bs.total_koekken,
    bs.total_sensorer,
    bs.investering_min_kr,
    bs.investering_max_kr,
    -- Investeringsniveau til farvekodning
    CASE 
        WHEN bs.investering_max_kr >= 100000 THEN 'Meget høj (100.000+ kr)'
        WHEN bs.investering_max_kr >= 50000 THEN 'Høj (50.000-100.000 kr)'
        WHEN bs.investering_max_kr >= 20000 THEN 'Medium (20.000-50.000 kr)'
        WHEN bs.investering_max_kr > 0 THEN 'Lav (< 20.000 kr)'
        ELSE 'Ingen'
    END AS investerings_niveau,
    -- Geometri (original EPSG:25832)
    bg.the_geom,
    -- Koordinater til Grafana Geomap (WGS84)
    ST_Y(ST_Transform(ST_Centroid(bg.the_geom), 4326)) AS latitude,
    ST_X(ST_Transform(ST_Centroid(bg.the_geom), 4326)) AS longitude
FROM bygning_stats bs
LEFT JOIN bygning_geom bg ON bs.bygning_id = bg.bygning;


-- -----------------------------------------------------------------------------
-- VIEW: Overordnet bygningsstatistik
-- -----------------------------------------------------------------------------
-- Én række med samlet statistik
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_bygning_statistik CASCADE;

CREATE OR REPLACE VIEW v_bygning_statistik AS
SELECT 
    COUNT(DISTINCT bygning) AS antal_bygninger,
    COUNT(*) AS antal_enheder,
    ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT bygning), 0), 1) AS gns_enheder_per_bygning,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS total_investering_min,
    SUM(samlet_investering_max_kr) AS total_investering_max,
    ROUND(SUM(samlet_investering_max_kr) / NULLIF(COUNT(DISTINCT bygning), 0), 0) AS gns_investering_per_bygning
FROM bbr_potentiale
WHERE bygning IS NOT NULL;


-- -----------------------------------------------------------------------------
-- VIEW: Bygninger per anvendelsestype
-- -----------------------------------------------------------------------------
-- Hvor mange bygninger har enheder af hver type?
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_bygninger_per_anvendelse CASCADE;

CREATE OR REPLACE VIEW v_bygninger_per_anvendelse AS
SELECT 
    enh020_enhedens_anvendelse_txt AS anvendelse,
    COUNT(DISTINCT bygning) AS antal_bygninger,
    COUNT(*) AS antal_enheder,
    ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT bygning), 0), 1) AS gns_enheder_per_bygning,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS investering_min_kr,
    SUM(samlet_investering_max_kr) AS investering_max_kr
FROM bbr_potentiale
WHERE bygning IS NOT NULL
  AND enh020_enhedens_anvendelse_txt IS NOT NULL
GROUP BY enh020_enhedens_anvendelse_txt
ORDER BY antal_bygninger DESC;


-- -----------------------------------------------------------------------------
-- VIEW: Bygninger per kommune
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_bygninger_per_kommune CASCADE;

CREATE OR REPLACE VIEW v_bygninger_per_kommune AS
SELECT 
    kommunekode,
    COUNT(DISTINCT bygning) AS antal_bygninger,
    COUNT(*) AS antal_enheder,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS investering_min_kr,
    SUM(samlet_investering_max_kr) AS investering_max_kr
FROM bbr_potentiale
WHERE bygning IS NOT NULL
  AND kommunekode IS NOT NULL
GROUP BY kommunekode
ORDER BY antal_bygninger DESC;


-- -----------------------------------------------------------------------------
-- VIEW: Top bygninger med flest enheder
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_bygninger_flest_enheder CASCADE;

CREATE OR REPLACE VIEW v_bygninger_flest_enheder AS
SELECT 
    bygning AS bygning_id,
    COUNT(*) AS antal_enheder,
    STRING_AGG(DISTINCT enh020_enhedens_anvendelse_txt, ', ') AS anvendelsestyper,
    MAX(adressebetegnelse) AS adresse,
    MAX(kommunekode) AS kommunekode,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS investering_min_kr,
    SUM(samlet_investering_max_kr) AS investering_max_kr
FROM bbr_potentiale
WHERE bygning IS NOT NULL
GROUP BY bygning
ORDER BY antal_enheder DESC
LIMIT 100;


-- ============================================================================
-- GRAFANA QUERIES FOR BYGNINGER
-- ============================================================================

-- Query: Bygninger med størst investeringsbehov (til Geomap)
/*
SELECT 
    bygning_id,
    antal_enheder,
    anvendelsestyper,
    adresse,
    total_sensorer,
    investering_min_kr,
    investering_max_kr,
    investerings_niveau,
    latitude,
    longitude
FROM v_bygning_geomap
WHERE latitude IS NOT NULL
ORDER BY investering_max_kr DESC
LIMIT 50;
*/

-- Query: Samlet statistik (til Stat panel)
/*
SELECT * FROM v_bygning_statistik;
*/

-- Query: Bygninger per anvendelse (til Bar chart)
/*
SELECT 
    anvendelse,
    antal_bygninger,
    antal_enheder,
    investering_max_kr
FROM v_bygninger_per_anvendelse
ORDER BY antal_bygninger DESC;
*/

-- Query: Bygninger per kommune (til Table eller Bar chart)
/*
SELECT * FROM v_bygninger_per_kommune;
*/
