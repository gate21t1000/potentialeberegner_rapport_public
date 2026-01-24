-- ============================================================================
-- KOMBO-SENSORER - Database udvidelse (v4 - RETTET BEREGNING)
-- ============================================================================
-- RETTET: Bruger nu pris-per-stk fra iot_sensor_types, ikke total-pris fra bygning
-- ============================================================================

SET search_path TO potentialeberegner, public;

-- -----------------------------------------------------------------------------
-- 1. TABELLER
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS kombo_komponenter CASCADE;
DROP TABLE IF EXISTS iot_sensor_kombos CASCADE;

CREATE TABLE iot_sensor_kombos (
    id SERIAL PRIMARY KEY,
    kombo_navn TEXT NOT NULL UNIQUE,
    beskrivelse TEXT,
    pris_min_kr NUMERIC(10,2) DEFAULT 0,
    pris_max_kr NUMERIC(10,2) DEFAULT 0,
    aktiv BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE kombo_komponenter (
    id SERIAL PRIMARY KEY,
    kombo_id INTEGER REFERENCES iot_sensor_kombos(id) ON DELETE CASCADE,
    sensor_type_id INTEGER REFERENCES iot_sensor_types(id) ON DELETE CASCADE,
    UNIQUE(kombo_id, sensor_type_id)
);

-- -----------------------------------------------------------------------------
-- 2. INDSÆT KOMBOS
-- -----------------------------------------------------------------------------
INSERT INTO iot_sensor_kombos (id, kombo_navn, pris_min_kr, pris_max_kr) VALUES
(1, 'Temperatur + Luftfugtighed', 400, 500),
(2, 'Temperatur + PIR', 400, 500),
(3, 'Temperatur + Luftfugtighed + CO2', 1100, 1200),
(4, 'Temperatur + Luftfugtighed + CO2 + PIR', 1200, 1300),
(5, 'Temperatur + Luftfugtighed + Støjsensor', 1200, 1300);

SELECT setval('iot_sensor_kombos_id_seq', 5);

-- Kombo komponenter
INSERT INTO kombo_komponenter (kombo_id, sensor_type_id) VALUES
(1, 10), (1, 22),                          -- Temp + Fugt
(2, 10), (2, 9), (2, 34),                  -- Temp + PIR (begge varianter)
(3, 10), (3, 22), (3, 33),                 -- Temp + Fugt + CO2
(4, 10), (4, 22), (4, 33), (4, 9), (4, 34),-- Temp + Fugt + CO2 + PIR
(5, 10), (5, 22), (5, 11);                 -- Temp + Fugt + Støj

-- -----------------------------------------------------------------------------
-- 3. FUNKTION: Beregn kombo-alternativer (RETTET!)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION potentialeberegner.get_kombo_alternativer(p_bygning_id UUID)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    WITH bygning_sensorer AS (
        -- Kun hent ANTAL af hver sensortype i bygningen
        SELECT 
            sensor_elem->>'type' AS sensor_type,
            SUM((sensor_elem->>'antal')::INTEGER) AS antal
        FROM potentialeberegner.bbr_potentiale bp,
             jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
        WHERE bp.bygning = p_bygning_id
        GROUP BY sensor_elem->>'type'
    ),
    sensor_med_priser AS (
        -- Join med iot_sensor_types for at få PRIS PER STK
        SELECT 
            bs.sensor_type,
            bs.antal,
            ist.id AS sensor_type_id,
            ist.pris_min_kr AS pris_per_stk_min,
            ist.pris_max_kr AS pris_per_stk_max,
            CASE 
                WHEN ist.sensor_type IN ('Bevægelsessensor', 'Tilstedeværelsessensor') THEN 'PIR_GROUP'
                ELSE ist.sensor_type
            END AS sensor_group
        FROM bygning_sensorer bs
        JOIN potentialeberegner.iot_sensor_types ist ON ist.sensor_type = bs.sensor_type
    ),
    kombo_komponenter_norm AS (
        -- Normaliser kombo-komponenter (PIR aliasing)
        SELECT DISTINCT ON (kk.kombo_id, 
            CASE 
                WHEN ist.sensor_type IN ('Bevægelsessensor', 'Tilstedeværelsessensor') THEN 'PIR_GROUP'
                ELSE ist.sensor_type
            END)
            kk.kombo_id,
            CASE 
                WHEN ist.sensor_type IN ('Bevægelsessensor', 'Tilstedeværelsessensor') THEN 'PIR_GROUP'
                ELSE ist.sensor_type
            END AS sensor_group,
            ist.pris_min_kr,
            ist.pris_max_kr
        FROM potentialeberegner.kombo_komponenter kk
        JOIN potentialeberegner.iot_sensor_types ist ON ist.id = kk.sensor_type_id
    ),
    kombo_match AS (
        SELECT 
            k.id AS kombo_id,
            k.kombo_navn,
            k.pris_min_kr AS kombo_pris_per_stk_min,
            k.pris_max_kr AS kombo_pris_per_stk_max,
            COUNT(DISTINCT kkn.sensor_group) AS komponenter_krævet,
            COUNT(DISTINCT CASE WHEN smp.sensor_group IS NOT NULL THEN kkn.sensor_group END) AS komponenter_fundet,
            -- Antal kombos = minimum antal af alle komponenter i bygningen
            MIN(smp.antal) AS antal_kombos,
            -- Sum af PRIS PER STK for enkelt-sensorer (fra iot_sensor_types)
            SUM(DISTINCT kkn.pris_min_kr) AS enkelt_pris_per_stk_min,
            SUM(DISTINCT kkn.pris_max_kr) AS enkelt_pris_per_stk_max,
            -- Liste af sensortyper fra bygningen
            ARRAY_AGG(DISTINCT smp.sensor_type ORDER BY smp.sensor_type) AS erstatter_sensorer
        FROM potentialeberegner.iot_sensor_kombos k
        JOIN kombo_komponenter_norm kkn ON kkn.kombo_id = k.id
        LEFT JOIN sensor_med_priser smp ON smp.sensor_group = kkn.sensor_group
        WHERE k.aktiv = TRUE
        GROUP BY k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr
        -- Alle komponenter skal være til stede
        HAVING COUNT(DISTINCT kkn.sensor_group) = COUNT(DISTINCT CASE WHEN smp.sensor_group IS NOT NULL THEN kkn.sensor_group END)
    )
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'kombo_id', kombo_id,
                'kombo_navn', kombo_navn,
                'erstatter', erstatter_sensorer,
                'antal', antal_kombos,
                -- Alle priser ganges med antal_kombos
                'kombo_pris_min', kombo_pris_per_stk_min * antal_kombos,
                'kombo_pris_max', kombo_pris_per_stk_max * antal_kombos,
                'enkelt_pris_min', enkelt_pris_per_stk_min * antal_kombos,
                'enkelt_pris_max', enkelt_pris_per_stk_max * antal_kombos,
                'besparelse_min', (enkelt_pris_per_stk_min - kombo_pris_per_stk_max) * antal_kombos,
                'besparelse_max', (enkelt_pris_per_stk_max - kombo_pris_per_stk_min) * antal_kombos
            )
            ORDER BY ((enkelt_pris_per_stk_max - kombo_pris_per_stk_min) * antal_kombos) DESC
        ),
        '[]'::JSONB
    ) INTO result
    FROM kombo_match
    WHERE antal_kombos > 0
      -- Vis hvis der er POTENTIEL besparelse (enkelt_max > kombo_min)
      AND enkelt_pris_per_stk_max > kombo_pris_per_stk_min;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 4. VIEW: Oversigt med korrekte beregninger
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_kombo_oversigt;
CREATE VIEW v_kombo_oversigt AS
SELECT 
    k.id,
    k.kombo_navn,
    k.pris_min_kr || '-' || k.pris_max_kr || ' kr' AS kombo_pris,
    SUM(DISTINCT ist.pris_min_kr) || '-' || SUM(DISTINCT ist.pris_max_kr) || ' kr' AS enkelt_priser_sum,
    SUM(DISTINCT ist.pris_max_kr) - k.pris_min_kr AS besparelse_max_per_stk,
    STRING_AGG(DISTINCT ist.sensor_type, ' + ' ORDER BY ist.sensor_type) AS komponenter
FROM iot_sensor_kombos k
JOIN kombo_komponenter kk ON kk.kombo_id = k.id
JOIN iot_sensor_types ist ON ist.id = kk.sensor_type_id
WHERE ist.sensor_type NOT IN ('Bevægelsessensor')  -- Undgå dobbelt PIR i visning
GROUP BY k.id, k.kombo_navn, k.pris_min_kr, k.pris_max_kr
ORDER BY besparelse_max_per_stk DESC;

-- -----------------------------------------------------------------------------
-- 5. VERIFIKATION
-- -----------------------------------------------------------------------------
SELECT '=== Kombo oversigt ===' AS info;
SELECT * FROM v_kombo_oversigt;

SELECT '=== Forventet output for 1 kombo ===' AS info;
SELECT 
    kombo_navn,
    kombo_pris AS "Kombo-pris (1 stk)",
    enkelt_priser_sum AS "Separate sensorer (1 stk)",
    besparelse_max_per_stk || ' kr' AS "Besparelse (1 stk)"
FROM v_kombo_oversigt;
