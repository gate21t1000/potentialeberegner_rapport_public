-- ============================================================================
-- PATCH: Ændre CO2-måler fra areal_per_100m2 til areal_per_500m2
-- ============================================================================

SET search_path TO potentialeberegner, public;

-- -----------------------------------------------------------------------------
-- 1. Tilføj ny multiplikator-type til constraint
-- -----------------------------------------------------------------------------
ALTER TABLE use_case_sensor_mapping 
DROP CONSTRAINT IF EXISTS use_case_sensor_mapping_multiplikator_kilde_check;

ALTER TABLE use_case_sensor_mapping 
ADD CONSTRAINT use_case_sensor_mapping_multiplikator_kilde_check 
CHECK (multiplikator_kilde IN (
    'enhed', 
    'toilet', 
    'badevaerelser', 
    'koekken', 
    'areal_per_100m2',
    'areal_per_500m2'
));

-- -----------------------------------------------------------------------------
-- 2. Opdater beregningsfunktionen til at håndtere areal_per_500m2
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_sensors_with_quantities(
    p_use_case_ids INTEGER[],
    p_antal_toiletter INTEGER DEFAULT 1,
    p_antal_badevaerelser INTEGER DEFAULT 1,
    p_antal_koekken INTEGER DEFAULT 1,
    p_areal_m2 NUMERIC DEFAULT NULL
)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    WITH sensor_data AS (
        SELECT 
            ist.id,
            ist.sensor_type,
            ist.pris_min_kr,
            ist.pris_max_kr,
            ucsm.multiplikator_kilde,
            -- Beregn antal baseret på multiplikator-kilde
            CASE ucsm.multiplikator_kilde
                WHEN 'enhed' THEN 1
                WHEN 'toilet' THEN GREATEST(COALESCE(p_antal_toiletter, 1), 1)
                WHEN 'badevaerelser' THEN GREATEST(COALESCE(p_antal_badevaerelser, 1), 1)
                WHEN 'koekken' THEN GREATEST(COALESCE(p_antal_koekken, 1), 1)
                WHEN 'areal_per_100m2' THEN GREATEST(CEIL(COALESCE(p_areal_m2, 100)::NUMERIC / 100), 1)
                WHEN 'areal_per_500m2' THEN GREATEST(CEIL(COALESCE(p_areal_m2, 500)::NUMERIC / 500), 1)
                ELSE 1
            END AS antal,
            ucsm.er_primaer,
            array_agg(DISTINCT ucsm.use_case_id) AS for_use_cases
        FROM use_case_sensor_mapping ucsm
        JOIN iot_sensor_types ist ON ist.id = ucsm.sensor_type_id
        WHERE ucsm.use_case_id = ANY(p_use_case_ids)
          AND ist.aktiv = TRUE
        GROUP BY ist.id, ist.sensor_type, ist.pris_min_kr, ist.pris_max_kr, 
                 ucsm.multiplikator_kilde, ucsm.er_primaer
    ),
    aggregated_sensors AS (
        SELECT 
            id,
            sensor_type,
            pris_min_kr,
            pris_max_kr,
            SUM(antal) AS antal,
            bool_or(er_primaer) AS er_primaer,
            array_agg(DISTINCT unnested_uc) AS for_use_cases
        FROM sensor_data,
             LATERAL unnest(for_use_cases) AS unnested_uc
        GROUP BY id, sensor_type, pris_min_kr, pris_max_kr
    )
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', id,
                'type', sensor_type,
                'antal', antal,
                'pris_min', pris_min_kr,
                'pris_max', pris_max_kr,
                'pris_total_min', antal * pris_min_kr,
                'pris_total_max', antal * pris_max_kr,
                'er_primaer', er_primaer,
                'for_use_cases', for_use_cases
            )
            ORDER BY antal DESC, sensor_type
        ),
        '[]'::JSONB
    ) INTO result
    FROM aggregated_sensors;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 3. Opdater CO2-måler mapping til areal_per_500m2
-- -----------------------------------------------------------------------------
UPDATE use_case_sensor_mapping 
SET multiplikator_kilde = 'areal_per_500m2'
WHERE sensor_type_id = (
    SELECT id FROM iot_sensor_types WHERE sensor_type = 'CO2-måler'
);

-- -----------------------------------------------------------------------------
-- 4. Verificer ændringen
-- -----------------------------------------------------------------------------
SELECT 'CO2-måler mapping opdateret:' AS info;

SELECT 
    uc.use_case_navn,
    ist.sensor_type,
    ucsm.multiplikator_kilde
FROM use_case_sensor_mapping ucsm
JOIN iot_sensor_types ist ON ist.id = ucsm.sensor_type_id
JOIN use_cases uc ON uc.id = ucsm.use_case_id
WHERE ist.sensor_type = 'CO2-måler'
ORDER BY uc.use_case_navn;

-- -----------------------------------------------------------------------------
-- 5. GENBEREGN ALLE POTENTIALER (vigtigt!)
-- -----------------------------------------------------------------------------
SELECT 'Genberegner alle potentialer...' AS info;
SELECT update_all_potentialer();
SELECT 'Færdig!' AS info;
