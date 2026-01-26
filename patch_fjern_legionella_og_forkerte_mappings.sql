-- ============================================================================
-- PATCH: Fjern Legionella use case og forkerte sensor-mappings
-- ============================================================================
-- Baggrund:
--   - Legionella-overvågning er ikke relevant for alle bygningstyper
--   - CO2-ventilation skal KUN have CO2-måler, ikke Temperatur/Luftfugtighed
-- ============================================================================

SET search_path TO potentialeberegner, public;

-- -----------------------------------------------------------------------------
-- 1. FJERN FORKERTE SENSOR-MAPPINGS FOR CO2-VENTILATION
-- -----------------------------------------------------------------------------
-- Use case 2 = "Behovsstyret ventilation via CO2-måling"
-- Skal KUN have CO2-måler (id 33), ikke Temperatur (10) eller Luftfugtighed (22)

DELETE FROM use_case_sensor_mapping 
WHERE use_case_id = 2 
  AND sensor_type_id IN (10, 22);  -- Temperaturføler og Luftfugtighedssensor

SELECT 'Fjernede forkerte mappings for CO2-ventilation:' AS status;
SELECT uc.use_case_navn, ist.sensor_type, ucsm.er_primaer
FROM use_case_sensor_mapping ucsm
JOIN use_cases uc ON uc.id = ucsm.use_case_id
JOIN iot_sensor_types ist ON ist.id = ucsm.sensor_type_id
WHERE ucsm.use_case_id = 2;

-- -----------------------------------------------------------------------------
-- 2. SLET LEGIONELLA USE CASE
-- -----------------------------------------------------------------------------
-- Use case: "Legionella-overvågning via temperaturlogger"

-- Først: Fjern fra anvendelse_use_case_mapping
DELETE FROM anvendelse_use_case_mapping 
WHERE use_case_id = (
    SELECT id FROM use_cases 
    WHERE use_case_navn = 'Legionella-overvågning via temperaturlogger'
);

-- Derefter: Fjern fra use_case_sensor_mapping
DELETE FROM use_case_sensor_mapping 
WHERE use_case_id = (
    SELECT id FROM use_cases 
    WHERE use_case_navn = 'Legionella-overvågning via temperaturlogger'
);

-- Til sidst: Slet selve use casen
DELETE FROM use_cases 
WHERE use_case_navn = 'Legionella-overvågning via temperaturlogger';

SELECT 'Slettede Legionella use case' AS status;

-- -----------------------------------------------------------------------------
-- 3. GENBEREGN ALLE POTENTIALER
-- -----------------------------------------------------------------------------
SELECT 'Genberegner alle potentialer...' AS status;
SELECT update_all_potentialer();

-- -----------------------------------------------------------------------------
-- 4. VERIFICER ÆNDRINGER
-- -----------------------------------------------------------------------------
SELECT 'Verificering af CO2-ventilation mappings:' AS status;
SELECT uc.use_case_navn, ist.sensor_type, ucsm.er_primaer
FROM use_case_sensor_mapping ucsm
JOIN use_cases uc ON uc.id = ucsm.use_case_id
JOIN iot_sensor_types ist ON ist.id = ucsm.sensor_type_id
WHERE uc.use_case_navn LIKE '%CO2%'
ORDER BY uc.use_case_navn, ist.sensor_type;

SELECT 'Færdig!' AS status;
