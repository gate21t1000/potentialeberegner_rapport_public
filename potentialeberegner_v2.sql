-- ============================================================================
-- POTENTIALEBEREGNER v2 - PostgreSQL/PostGIS Database Setup
-- ============================================================================
-- Formål: Identificere use cases, beregne investeringsbehov (antal sensorer
--         og prisspænd) for BBR-enheder baseret på anvendelseskoder og
--         antal faciliteter (toiletter, badeværelser, køkkener).
-- ============================================================================
-- ÆNDRINGER FRA v1:
-- - Fokus skiftet fra besparingspotentiale til investeringsbehov
-- - Sensorpriser med spænd (min/max)
-- - Sensorer multipliceres med antal faciliteter
-- - Filtrering på specifikke anvendelsestyper
-- ============================================================================

-- Aktivér PostGIS hvis ikke allerede aktiveret
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================================
-- DEL 0: OPRYDNING - Fjern gamle objekter
-- ============================================================================

-- Drop views først (afhænger af tabeller)
DROP VIEW IF EXISTS v_potentiale_per_anvendelse CASCADE;
DROP VIEW IF EXISTS v_sensor_anvendelse CASCADE;
DROP VIEW IF EXISTS v_use_case_popularitet CASCADE;
DROP VIEW IF EXISTS v_potentiale_per_kommune CASCADE;

-- Drop funktioner
DROP FUNCTION IF EXISTS get_use_cases_for_anvendelse(TEXT) CASCADE;
DROP FUNCTION IF EXISTS get_sensors_for_use_cases(INTEGER[]) CASCADE;
DROP FUNCTION IF EXISTS update_enhed_potentiale(INTEGER) CASCADE;
DROP FUNCTION IF EXISTS update_all_potentialer() CASCADE;
DROP FUNCTION IF EXISTS get_lat_lng(GEOMETRY) CASCADE;

-- Drop tabeller (i korrekt rækkefølge pga. foreign keys)
DROP TABLE IF EXISTS anvendelse_use_case_mapping CASCADE;
DROP TABLE IF EXISTS use_case_sensor_mapping CASCADE;
DROP TABLE IF EXISTS bbr_potentiale CASCADE;
DROP TABLE IF EXISTS use_cases CASCADE;
DROP TABLE IF EXISTS iot_sensor_types CASCADE;


-- ============================================================================
-- DEL 1: STØTTETABELLER
-- ============================================================================

-- -----------------------------------------------------------------------------
-- 1.1 IoT Sensor Types støttetabel (NY STRUKTUR med prisspænd)
-- -----------------------------------------------------------------------------
CREATE TABLE iot_sensor_types (
    id SERIAL PRIMARY KEY,
    sensor_type TEXT NOT NULL UNIQUE,
    beskrivelse TEXT,
    pris_min_kr NUMERIC(10,2) DEFAULT 0,  -- Nedre prisspænd
    pris_max_kr NUMERIC(10,2) DEFAULT 0,  -- Øvre prisspænd
    aktiv BOOLEAN DEFAULT TRUE,           -- Kan deaktiveres uden at slette
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indsæt sensortyper med placeholder-priser
INSERT INTO iot_sensor_types (id, sensor_type, pris_min_kr, pris_max_kr) VALUES
(1, 'VOC-sensor', 400, 800),
(2, 'Vindmåler', 500, 1200),
(3, 'Vibrationssensor', 300, 700),
(4, 'Vandstandsmåler', 400, 900),
(5, 'Vandflowmåler', 500, 1200),
(6, 'Vandalsensor', 200, 500),
(7, 'Tryksensor', 350, 800),
(8, 'Tilt-sensor', 200, 450),
(9, 'Tilstedeværelsessensor', 300, 700),
(10, 'Temperaturføler', 150, 400),
(11, 'Støjsensor', 400, 900),
(12, 'Spændingsmåler', 300, 700),
(13, 'Skraldespands-niveausensor', 250, 600),
(14, 'Røgalarm', 200, 500),
(15, 'Regnmåler', 350, 800),
(16, 'Radon-måler', 800, 1500),
(17, 'pH-sensor', 500, 1100),
(18, 'Parkeringssensor', 300, 700),
(19, 'Oliestandsmåler', 400, 900),
(20, 'Lækagesensor', 200, 500),
(21, 'Lysstyrkemåler', 250, 550),
(22, 'Luftfugtighedssensor', 200, 500),
(23, 'Ledningsevnemåler', 450, 950),
(24, 'Jordtemperatursensor', 300, 700),
(25, 'Jordfugtighedssensor', 350, 750),
(26, 'Iltindholdsmåler', 600, 1200),
(27, 'Gyroskop', 250, 600),
(28, 'GPS-tracker/Vægtføler', 400, 900),
(29, 'Gasmåler', 500, 1100),
(30, 'Fjernvarmemåler', 600, 1400),
(31, 'Energimåler', 400, 1000),
(32, 'Dørkontakt', 100, 300),
(33, 'CO2-måler', 350, 800),
(34, 'Bevægelsessensor', 150, 400),
(35, 'Barometrisk', 300, 700),
(36, 'Accelerationssensor', 250, 600);

-- Reset sequence
SELECT setval('iot_sensor_types_id_seq', 36);


-- -----------------------------------------------------------------------------
-- 1.2 Use Cases støttetabel (UDEN besparelseskolonner)
-- -----------------------------------------------------------------------------
CREATE TABLE use_cases (
    id SERIAL PRIMARY KEY,
    use_case_navn TEXT NOT NULL,
    beskrivelse TEXT,
    link TEXT,
    link2 TEXT,
    kategori TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indsæt use cases fra CSV (uden besparelseskolonner)
INSERT INTO use_cases (id, use_case_navn, beskrivelse, link, link2, kategori) VALUES
(1, 'Tælling af brugere i mødelokaler (Space management)', NULL, 'https://iotwiki.dk/t/t%C3%A6ller?sort=title', NULL, 'space_management'),
(2, 'Behovsstyret ventilation via CO2-måling', NULL, 'https://iotwiki.dk/t/co2?sort=title', NULL, 'ventilation'),
(3, 'Natsænkning af varme baseret på brugsmønstre', NULL, 'https://iotwiki.dk/t/varme?sort=title', NULL, 'varme'),
(4, 'Vejrkompensering af varmestyring', NULL, 'https://iotwiki.dk/t/varme?sort=title', NULL, 'varme'),
(5, 'Lækageovervågning af brugsvand', NULL, 'https://iotwiki.dk/t/l%C3%A6kage?sort=title', NULL, 'vand'),
(6, 'Detektering af løbende toiletter', NULL, NULL, NULL, 'vand'),
(7, 'Automatisk lysstyring via bevægelsessensorer', NULL, 'https://iotwiki.dk/t/lys?sort=title', NULL, 'el'),
(8, 'Dagslysregulering af belysning', NULL, 'https://iotwiki.dk/t/lys?sort=title', NULL, 'el'),
(9, 'Zoneopdelt varmestyring i kontorlandskaber', NULL, 'https://iotwiki.dk/t/varme?sort=title', 'https://iotwiki.dk/t/temperatur', 'varme'),
(10, 'Overvågning af standbystrøm på teknisk udstyr', NULL, 'https://iotwiki.dk/t/elektricitet?sort=title', NULL, 'el'),
(11, 'Optimering af serverrumsafkøling', NULL, NULL, NULL, 'køling'),
(12, 'Forebyggende vedligehold af HVAC-anlæg', NULL, NULL, NULL, 'ventilation'),
(13, 'Identifikation af defekte kontraventiler i varmesystemer', NULL, 'https://iotwiki.dk/t/varme?sort=title', NULL, 'varme'),
(14, 'Måling af varmetab gennem åbne døre/vinduer', NULL, 'https://iotwiki.dk/t/varme?sort=title', 'https://iotwiki.dk/t/temperatur', 'varme'),
(15, 'Optimering af kantinedrift via persontælling', NULL, 'https://iotwiki.dk/t/t%C3%A6ller?sort=title', NULL, 'space_management'),
(16, 'Effektivitetsmåling af varmepumper (COP-overvågning)', NULL, NULL, NULL, 'varme'),
(17, 'Efterspørgselsstyring (Peak shaving) af elforbrug', NULL, NULL, NULL, 'el'),
(18, 'Dynamisk rengøring baseret på faktiske lokalebesøg', NULL, 'https://iotwiki.dk/t/t%C3%A6ller?sort=title', NULL, 'space_management'),
(19, 'Optimering af skraldeafhentning via fyldningsgrad', NULL, NULL, NULL, 'affald'),
(20, 'Indregulering af varmeanlæg via returløbstemperatur', NULL, 'https://iotwiki.dk/t/fjernvarme?sort=title', NULL, 'varme'),
(21, 'Overvågning af isoleringsevne (U-værdi estimering)', NULL, NULL, NULL, 'varme'),
(22, 'Legionella-overvågning via temperaturlogger', NULL, 'https://iotwiki.dk/t/temperatur/egenkontrol?sort=title', NULL, 'vand'),
(23, 'Optimering af elevator-drift og standby-mode', NULL, NULL, NULL, 'el'),
(24, 'Solafskærmningsstyring for reduktion af kølebehov', NULL, NULL, NULL, 'køling'),
(25, 'Belægningsstyret ventilation i fællesområder', NULL, NULL, NULL, 'ventilation'),
(26, 'Energiregnskab per lejer/afdeling', NULL, 'https://iotwiki.dk/t/energioptimering?sort=title', NULL, 'el'),
(27, 'Automatiseret energirapportering til EU-overholdelse', NULL, NULL, NULL, 'el'),
(28, 'Detektering af unødigt energiforbrug uden for åbningstid', NULL, NULL, NULL, 'el'),
(29, 'Måling af fugt i konstruktioner for at undgå skader', NULL, 'https://iotwiki.dk/t/fugt?sort=title', NULL, 'bygning'),
(30, 'Automatisk egenkontrol, frysere og køleskabe', NULL, 'https://iotwiki.dk/t/egenkontrol?sort=title', NULL, 'køling'),
(31, 'Monitorering af vandforbrug', NULL, 'https://iotwiki.dk/t/vand?sort=title', NULL, 'vand'),
(32, 'Monitorering af solcelleproduktion', NULL, NULL, NULL, 'el'),
(33, 'Måling af aktivitet i mødelokaler (Space management)', NULL, 'https://iotwiki.dk/t/pir?sort=title', NULL, 'space_management');

-- Reset sequence
SELECT setval('use_cases_id_seq', 33);


-- -----------------------------------------------------------------------------
-- 1.3 Mapping: Use Case til IoT Sensorer (med multiplikator-kilde)
-- -----------------------------------------------------------------------------
CREATE TABLE use_case_sensor_mapping (
    id SERIAL PRIMARY KEY,
    use_case_id INTEGER REFERENCES use_cases(id) ON DELETE CASCADE,
    sensor_type_id INTEGER REFERENCES iot_sensor_types(id) ON DELETE CASCADE,
    er_primaer BOOLEAN DEFAULT FALSE,
    -- Multiplikator-kilde: hvad skal sensorantallet ganges med?
    -- 'enhed' = 1 per enhed (standard)
    -- 'toilet' = per antal toiletter
    -- 'badevaerelser' = per antal badeværelser
    -- 'koekken' = per antal køkkener
    -- 'areal_per_100m2' = per 100 m² areal
    multiplikator_kilde TEXT DEFAULT 'enhed' CHECK (multiplikator_kilde IN ('enhed', 'toilet', 'badevaerelser', 'koekken', 'areal_per_100m2')),
    UNIQUE(use_case_id, sensor_type_id)
);

-- Mapping af use cases til sensorer med multiplikator

-- Use case 1: Tælling af brugere i mødelokaler
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(1, 9, TRUE, 'enhed'),   -- Tilstedeværelsessensor
(1, 34, FALSE, 'enhed'); -- Bevægelsessensor

-- Use case 2: Behovsstyret ventilation via CO2-måling
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(2, 33, TRUE, 'areal_per_100m2'),  -- CO2-måler per 100m²
(2, 10, FALSE, 'enhed'),           -- Temperaturføler
(2, 22, FALSE, 'enhed');           -- Luftfugtighedssensor

-- Use case 3: Natsænkning af varme
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(3, 10, TRUE, 'enhed'),  -- Temperaturføler
(3, 34, FALSE, 'enhed'), -- Bevægelsessensor
(3, 9, FALSE, 'enhed');  -- Tilstedeværelsessensor

-- Use case 4: Vejrkompensering af varmestyring
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(4, 10, TRUE, 'enhed'),  -- Temperaturføler (udetemperatur)
(4, 2, FALSE, 'enhed'),  -- Vindmåler
(4, 35, FALSE, 'enhed'); -- Barometrisk

-- Use case 5: Lækageovervågning af brugsvand
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(5, 20, TRUE, 'enhed'),  -- Lækagesensor
(5, 5, FALSE, 'enhed');  -- Vandflowmåler

-- Use case 6: Detektering af løbende toiletter
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(6, 5, TRUE, 'toilet'),  -- Vandflowmåler per toilet
(6, 20, FALSE, 'toilet'); -- Lækagesensor per toilet

-- Use case 7: Automatisk lysstyring
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(7, 34, TRUE, 'areal_per_100m2'),  -- Bevægelsessensor per 100m²
(7, 21, FALSE, 'enhed');           -- Lysstyrkemåler

-- Use case 8: Dagslysregulering
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(8, 21, TRUE, 'enhed');  -- Lysstyrkemåler

-- Use case 9: Zoneopdelt varmestyring
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(9, 10, TRUE, 'areal_per_100m2'),  -- Temperaturføler per 100m²
(9, 9, FALSE, 'enhed'),            -- Tilstedeværelsessensor
(9, 34, FALSE, 'enhed');           -- Bevægelsessensor

-- Use case 10: Overvågning af standbystrøm
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(10, 31, TRUE, 'enhed'),  -- Energimåler
(10, 12, FALSE, 'enhed'); -- Spændingsmåler

-- Use case 11: Optimering af serverrumsafkøling
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(11, 10, TRUE, 'enhed'),  -- Temperaturføler
(11, 22, FALSE, 'enhed'), -- Luftfugtighedssensor
(11, 31, FALSE, 'enhed'); -- Energimåler

-- Use case 12: Forebyggende vedligehold af HVAC
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(12, 3, TRUE, 'enhed'),   -- Vibrationssensor
(12, 10, FALSE, 'enhed'), -- Temperaturføler
(12, 7, FALSE, 'enhed');  -- Tryksensor

-- Use case 13: Identifikation af defekte kontraventiler
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(13, 10, TRUE, 'enhed'),  -- Temperaturføler
(13, 30, FALSE, 'enhed'); -- Fjernvarmemåler

-- Use case 14: Måling af varmetab gennem åbne døre/vinduer
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(14, 32, TRUE, 'enhed'),  -- Dørkontakt
(14, 10, FALSE, 'enhed'); -- Temperaturføler

-- Use case 15: Optimering af kantinedrift
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(15, 9, TRUE, 'enhed'),   -- Tilstedeværelsessensor
(15, 34, FALSE, 'enhed'); -- Bevægelsessensor

-- Use case 16: Effektivitetsmåling af varmepumper
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(16, 31, TRUE, 'enhed'),  -- Energimåler
(16, 10, FALSE, 'enhed'), -- Temperaturføler
(16, 5, FALSE, 'enhed');  -- Vandflowmåler

-- Use case 17: Efterspørgselsstyring (Peak shaving)
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(17, 31, TRUE, 'enhed'),  -- Energimåler
(17, 12, FALSE, 'enhed'); -- Spændingsmåler

-- Use case 18: Dynamisk rengøring
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(18, 9, TRUE, 'areal_per_100m2'),  -- Tilstedeværelsessensor per 100m²
(18, 34, FALSE, 'enhed');          -- Bevægelsessensor

-- Use case 19: Optimering af skraldeafhentning
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(19, 13, TRUE, 'enhed'); -- Skraldespands-niveausensor

-- Use case 20: Indregulering af varmeanlæg
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(20, 30, TRUE, 'enhed'),  -- Fjernvarmemåler
(20, 10, FALSE, 'enhed'); -- Temperaturføler

-- Use case 21: Overvågning af isoleringsevne
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(21, 10, TRUE, 'enhed'),  -- Temperaturføler (inde/ude)
(21, 22, FALSE, 'enhed'); -- Luftfugtighedssensor

-- Use case 22: Legionella-overvågning
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(22, 10, TRUE, 'badevaerelser'); -- Temperaturføler per badeværelse

-- Use case 23: Optimering af elevator-drift
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(23, 31, TRUE, 'enhed'),  -- Energimåler
(23, 34, FALSE, 'enhed'); -- Bevægelsessensor

-- Use case 24: Solafskærmningsstyring
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(24, 21, TRUE, 'enhed'),  -- Lysstyrkemåler
(24, 10, FALSE, 'enhed'); -- Temperaturføler

-- Use case 25: Belægningsstyret ventilation
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(25, 33, TRUE, 'areal_per_100m2'),  -- CO2-måler per 100m²
(25, 9, FALSE, 'enhed'),            -- Tilstedeværelsessensor
(25, 34, FALSE, 'enhed');           -- Bevægelsessensor

-- Use case 26: Energiregnskab per lejer/afdeling
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(26, 31, TRUE, 'enhed'),  -- Energimåler
(26, 30, FALSE, 'enhed'), -- Fjernvarmemåler
(26, 5, FALSE, 'enhed');  -- Vandflowmåler

-- Use case 27: Automatiseret energirapportering
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(27, 31, TRUE, 'enhed'); -- Energimåler

-- Use case 28: Detektering af energiforbrug uden for åbningstid
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(28, 31, TRUE, 'enhed'),  -- Energimåler
(28, 34, FALSE, 'enhed'); -- Bevægelsessensor

-- Use case 29: Måling af fugt i konstruktioner
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(29, 22, TRUE, 'enhed'); -- Luftfugtighedssensor

-- Use case 30: Automatisk egenkontrol, frysere og køleskabe
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(30, 10, TRUE, 'koekken'); -- Temperaturføler per køkken

-- Use case 31: Monitorering af vandforbrug
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(31, 5, TRUE, 'enhed'); -- Vandflowmåler

-- Use case 32: Monitorering af solcelleproduktion
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(32, 31, TRUE, 'enhed'),  -- Energimåler
(32, 21, FALSE, 'enhed'); -- Lysstyrkemåler

-- Use case 33: Måling af aktivitet i mødelokaler
INSERT INTO use_case_sensor_mapping (use_case_id, sensor_type_id, er_primaer, multiplikator_kilde) VALUES
(33, 34, TRUE, 'enhed'),  -- Bevægelsessensor
(33, 9, FALSE, 'enhed');  -- Tilstedeværelsessensor


-- -----------------------------------------------------------------------------
-- 1.4 Mapping: Anvendelseskoder til Use Cases
-- UDVIDET mapping for at koble FLEST mulige use cases på hver anvendelse
-- -----------------------------------------------------------------------------
CREATE TABLE anvendelse_use_case_mapping (
    id SERIAL PRIMARY KEY,
    anvendelse_tekst TEXT NOT NULL,  -- Den fulde tekstbeskrivelse fra BBR
    use_case_id INTEGER REFERENCES use_cases(id) ON DELETE CASCADE,
    relevans_score INTEGER DEFAULT 5 CHECK (relevans_score BETWEEN 1 AND 10),
    UNIQUE(anvendelse_tekst, use_case_id)
);

-- ===========================================================================
-- ANVENDELSE: Daginstitution
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Daginstitution', 1, 8),   -- Tælling af brugere
('Daginstitution', 2, 9),   -- CO2-styret ventilation
('Daginstitution', 3, 8),   -- Natsænkning af varme
('Daginstitution', 4, 7),   -- Vejrkompensering
('Daginstitution', 5, 8),   -- Lækageovervågning
('Daginstitution', 6, 8),   -- Løbende toiletter
('Daginstitution', 7, 8),   -- Automatisk lysstyring
('Daginstitution', 8, 7),   -- Dagslysregulering
('Daginstitution', 12, 6),  -- HVAC vedligehold
('Daginstitution', 14, 7),  -- Varmetab døre/vinduer
('Daginstitution', 18, 7),  -- Dynamisk rengøring
('Daginstitution', 19, 6),  -- Skraldeafhentning
('Daginstitution', 20, 7),  -- Indregulering varmeanlæg
('Daginstitution', 22, 9),  -- Legionella-overvågning
('Daginstitution', 28, 8),  -- Energiforbrug uden for åbningstid
('Daginstitution', 29, 6),  -- Fugtmåling
('Daginstitution', 30, 9),  -- Egenkontrol køl/frys
('Daginstitution', 31, 7);  -- Vandforbrug

-- Også den udfasede version
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('(UDFASES) Daginstitution.', 1, 8),
('(UDFASES) Daginstitution.', 2, 9),
('(UDFASES) Daginstitution.', 3, 8),
('(UDFASES) Daginstitution.', 4, 7),
('(UDFASES) Daginstitution.', 5, 8),
('(UDFASES) Daginstitution.', 6, 8),
('(UDFASES) Daginstitution.', 7, 8),
('(UDFASES) Daginstitution.', 8, 7),
('(UDFASES) Daginstitution.', 12, 6),
('(UDFASES) Daginstitution.', 14, 7),
('(UDFASES) Daginstitution.', 18, 7),
('(UDFASES) Daginstitution.', 19, 6),
('(UDFASES) Daginstitution.', 20, 7),
('(UDFASES) Daginstitution.', 22, 9),
('(UDFASES) Daginstitution.', 28, 8),
('(UDFASES) Daginstitution.', 29, 6),
('(UDFASES) Daginstitution.', 30, 9),
('(UDFASES) Daginstitution.', 31, 7);

-- ===========================================================================
-- ANVENDELSE: Grundskole
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Grundskole', 1, 9),   -- Tælling af brugere
('Grundskole', 2, 10),  -- CO2-styret ventilation
('Grundskole', 3, 8),   -- Natsænkning
('Grundskole', 4, 7),   -- Vejrkompensering
('Grundskole', 5, 7),   -- Lækageovervågning
('Grundskole', 6, 8),   -- Løbende toiletter
('Grundskole', 7, 9),   -- Automatisk lysstyring
('Grundskole', 8, 8),   -- Dagslysregulering
('Grundskole', 12, 7),  -- HVAC vedligehold
('Grundskole', 14, 7),  -- Varmetab døre/vinduer
('Grundskole', 15, 7),  -- Kantinedrift
('Grundskole', 18, 8),  -- Dynamisk rengøring
('Grundskole', 19, 6),  -- Skraldeafhentning
('Grundskole', 20, 7),  -- Indregulering varmeanlæg
('Grundskole', 22, 8),  -- Legionella-overvågning
('Grundskole', 25, 8),  -- Belægningsstyret ventilation
('Grundskole', 28, 9),  -- Energiforbrug uden for åbningstid
('Grundskole', 29, 6),  -- Fugtmåling
('Grundskole', 30, 8),  -- Egenkontrol køl/frys
('Grundskole', 31, 7),  -- Vandforbrug
('Grundskole', 33, 8);  -- Aktivitet i lokaler

-- ===========================================================================
-- ANVENDELSE: Universitet
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Universitet', 1, 9),   -- Tælling af brugere
('Universitet', 2, 10),  -- CO2-styret ventilation
('Universitet', 3, 8),   -- Natsænkning
('Universitet', 4, 7),   -- Vejrkompensering
('Universitet', 5, 7),   -- Lækageovervågning
('Universitet', 6, 7),   -- Løbende toiletter
('Universitet', 7, 9),   -- Automatisk lysstyring
('Universitet', 8, 8),   -- Dagslysregulering
('Universitet', 9, 8),   -- Zoneopdelt varmestyring
('Universitet', 10, 7),  -- Standbystrøm
('Universitet', 11, 8),  -- Serverrumsafkøling
('Universitet', 12, 8),  -- HVAC vedligehold
('Universitet', 14, 7),  -- Varmetab døre/vinduer
('Universitet', 15, 7),  -- Kantinedrift
('Universitet', 17, 7),  -- Peak shaving
('Universitet', 18, 8),  -- Dynamisk rengøring
('Universitet', 19, 6),  -- Skraldeafhentning
('Universitet', 20, 7),  -- Indregulering varmeanlæg
('Universitet', 22, 8),  -- Legionella-overvågning
('Universitet', 23, 6),  -- Elevator-drift
('Universitet', 24, 7),  -- Solafskærmning
('Universitet', 25, 9),  -- Belægningsstyret ventilation
('Universitet', 26, 8),  -- Energiregnskab
('Universitet', 27, 8),  -- Energirapportering
('Universitet', 28, 9),  -- Energiforbrug uden for åbningstid
('Universitet', 29, 7),  -- Fugtmåling
('Universitet', 30, 7),  -- Egenkontrol køl/frys
('Universitet', 31, 7),  -- Vandforbrug
('Universitet', 33, 9);  -- Aktivitet i mødelokaler

-- ===========================================================================
-- ANVENDELSE: Anden enhed til undervisning og forskning
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Anden enhed til undervisning og forskning', 1, 8),
('Anden enhed til undervisning og forskning', 2, 9),
('Anden enhed til undervisning og forskning', 3, 8),
('Anden enhed til undervisning og forskning', 5, 7),
('Anden enhed til undervisning og forskning', 6, 7),
('Anden enhed til undervisning og forskning', 7, 8),
('Anden enhed til undervisning og forskning', 8, 7),
('Anden enhed til undervisning og forskning', 12, 7),
('Anden enhed til undervisning og forskning', 18, 7),
('Anden enhed til undervisning og forskning', 22, 7),
('Anden enhed til undervisning og forskning', 25, 8),
('Anden enhed til undervisning og forskning', 28, 8),
('Anden enhed til undervisning og forskning', 30, 7),
('Anden enhed til undervisning og forskning', 33, 8);

-- ===========================================================================
-- ANVENDELSE: Enhed til kontor
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Enhed til kontor', 1, 10),  -- Tælling af brugere
('Enhed til kontor', 2, 9),   -- CO2-styret ventilation
('Enhed til kontor', 3, 8),   -- Natsænkning
('Enhed til kontor', 4, 7),   -- Vejrkompensering
('Enhed til kontor', 5, 7),   -- Lækageovervågning
('Enhed til kontor', 6, 7),   -- Løbende toiletter
('Enhed til kontor', 7, 9),   -- Automatisk lysstyring
('Enhed til kontor', 8, 8),   -- Dagslysregulering
('Enhed til kontor', 9, 9),   -- Zoneopdelt varmestyring
('Enhed til kontor', 10, 8),  -- Standbystrøm
('Enhed til kontor', 11, 7),  -- Serverrumsafkøling
('Enhed til kontor', 12, 7),  -- HVAC vedligehold
('Enhed til kontor', 14, 7),  -- Varmetab døre/vinduer
('Enhed til kontor', 15, 6),  -- Kantinedrift
('Enhed til kontor', 17, 8),  -- Peak shaving
('Enhed til kontor', 18, 8),  -- Dynamisk rengøring
('Enhed til kontor', 19, 6),  -- Skraldeafhentning
('Enhed til kontor', 20, 7),  -- Indregulering varmeanlæg
('Enhed til kontor', 22, 7),  -- Legionella-overvågning
('Enhed til kontor', 23, 6),  -- Elevator-drift
('Enhed til kontor', 24, 8),  -- Solafskærmning
('Enhed til kontor', 25, 8),  -- Belægningsstyret ventilation
('Enhed til kontor', 26, 9),  -- Energiregnskab
('Enhed til kontor', 27, 7),  -- Energirapportering
('Enhed til kontor', 28, 9),  -- Energiforbrug uden for åbningstid
('Enhed til kontor', 29, 6),  -- Fugtmåling
('Enhed til kontor', 30, 6),  -- Egenkontrol køl/frys
('Enhed til kontor', 31, 7),  -- Vandforbrug
('Enhed til kontor', 33, 10); -- Aktivitet i mødelokaler

-- ===========================================================================
-- ANVENDELSE: (UDFASES) Offentlig administration.
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('(UDFASES) Offentlig administration.', 1, 9),
('(UDFASES) Offentlig administration.', 2, 9),
('(UDFASES) Offentlig administration.', 3, 8),
('(UDFASES) Offentlig administration.', 5, 7),
('(UDFASES) Offentlig administration.', 6, 7),
('(UDFASES) Offentlig administration.', 7, 9),
('(UDFASES) Offentlig administration.', 8, 8),
('(UDFASES) Offentlig administration.', 9, 8),
('(UDFASES) Offentlig administration.', 10, 7),
('(UDFASES) Offentlig administration.', 17, 7),
('(UDFASES) Offentlig administration.', 18, 8),
('(UDFASES) Offentlig administration.', 22, 7),
('(UDFASES) Offentlig administration.', 25, 8),
('(UDFASES) Offentlig administration.', 26, 8),
('(UDFASES) Offentlig administration.', 27, 8),
('(UDFASES) Offentlig administration.', 28, 9),
('(UDFASES) Offentlig administration.', 33, 9);

-- ===========================================================================
-- ANVENDELSE: Bibliotek
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Bibliotek', 1, 8),
('Bibliotek', 2, 9),
('Bibliotek', 3, 8),
('Bibliotek', 5, 6),
('Bibliotek', 7, 9),
('Bibliotek', 8, 8),
('Bibliotek', 12, 7),
('Bibliotek', 14, 7),
('Bibliotek', 18, 8),
('Bibliotek', 22, 7),
('Bibliotek', 24, 7),
('Bibliotek', 25, 8),
('Bibliotek', 28, 9),
('Bibliotek', 29, 7),
('Bibliotek', 33, 8);

-- ===========================================================================
-- ANVENDELSE: Forsamlingshus
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Forsamlingshus', 1, 8),
('Forsamlingshus', 2, 9),
('Forsamlingshus', 3, 9),
('Forsamlingshus', 5, 7),
('Forsamlingshus', 6, 7),
('Forsamlingshus', 7, 8),
('Forsamlingshus', 8, 7),
('Forsamlingshus', 14, 7),
('Forsamlingshus', 15, 7),
('Forsamlingshus', 18, 7),
('Forsamlingshus', 22, 8),
('Forsamlingshus', 25, 8),
('Forsamlingshus', 28, 9),
('Forsamlingshus', 30, 8),
('Forsamlingshus', 31, 7);

-- ===========================================================================
-- ANVENDELSE: Anden enhed til kulturelle formål
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Anden enhed til kulturelle formål', 1, 7),
('Anden enhed til kulturelle formål', 2, 8),
('Anden enhed til kulturelle formål', 3, 8),
('Anden enhed til kulturelle formål', 5, 6),
('Anden enhed til kulturelle formål', 7, 8),
('Anden enhed til kulturelle formål', 8, 7),
('Anden enhed til kulturelle formål', 14, 6),
('Anden enhed til kulturelle formål', 18, 7),
('Anden enhed til kulturelle formål', 22, 7),
('Anden enhed til kulturelle formål', 25, 7),
('Anden enhed til kulturelle formål', 28, 8),
('Anden enhed til kulturelle formål', 29, 6);

-- ===========================================================================
-- ANVENDELSE: Sundhedscenter, lægehus, fødeklinik mv.
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Sundhedscenter, lægehus, fødeklinik mv.', 1, 7),
('Sundhedscenter, lægehus, fødeklinik mv.', 2, 10),
('Sundhedscenter, lægehus, fødeklinik mv.', 3, 7),
('Sundhedscenter, lægehus, fødeklinik mv.', 5, 8),
('Sundhedscenter, lægehus, fødeklinik mv.', 6, 8),
('Sundhedscenter, lægehus, fødeklinik mv.', 7, 7),
('Sundhedscenter, lægehus, fødeklinik mv.', 12, 8),
('Sundhedscenter, lægehus, fødeklinik mv.', 18, 7),
('Sundhedscenter, lægehus, fødeklinik mv.', 22, 10),
('Sundhedscenter, lægehus, fødeklinik mv.', 28, 8),
('Sundhedscenter, lægehus, fødeklinik mv.', 29, 7),
('Sundhedscenter, lægehus, fødeklinik mv.', 30, 9),
('Sundhedscenter, lægehus, fødeklinik mv.', 31, 8);

-- ===========================================================================
-- ANVENDELSE: Klubhus i forbindelse med fritid- og idræt
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Klubhus i forbindelse med fritid- og idræt', 1, 7),
('Klubhus i forbindelse med fritid- og idræt', 2, 8),
('Klubhus i forbindelse med fritid- og idræt', 3, 8),
('Klubhus i forbindelse med fritid- og idræt', 5, 7),
('Klubhus i forbindelse med fritid- og idræt', 6, 7),
('Klubhus i forbindelse med fritid- og idræt', 7, 7),
('Klubhus i forbindelse med fritid- og idræt', 14, 6),
('Klubhus i forbindelse med fritid- og idræt', 18, 6),
('Klubhus i forbindelse med fritid- og idræt', 22, 8),
('Klubhus i forbindelse med fritid- og idræt', 28, 8),
('Klubhus i forbindelse med fritid- og idræt', 30, 7),
('Klubhus i forbindelse med fritid- og idræt', 31, 7);

-- ===========================================================================
-- ANVENDELSE: Svømmehal
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Svømmehal', 1, 7),
('Svømmehal', 2, 9),
('Svømmehal', 3, 7),
('Svømmehal', 5, 9),
('Svømmehal', 6, 8),
('Svømmehal', 7, 7),
('Svømmehal', 12, 9),
('Svømmehal', 17, 8),
('Svømmehal', 18, 7),
('Svømmehal', 22, 10),
('Svømmehal', 25, 8),
('Svømmehal', 28, 8),
('Svømmehal', 29, 8),
('Svømmehal', 31, 9);

-- ===========================================================================
-- ANVENDELSE: Idrætshal
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Idrætshal', 1, 8),
('Idrætshal', 2, 9),
('Idrætshal', 3, 8),
('Idrætshal', 5, 7),
('Idrætshal', 6, 7),
('Idrætshal', 7, 9),
('Idrætshal', 8, 8),
('Idrætshal', 12, 7),
('Idrætshal', 14, 7),
('Idrætshal', 18, 7),
('Idrætshal', 22, 8),
('Idrætshal', 25, 9),
('Idrætshal', 28, 9),
('Idrætshal', 30, 6),
('Idrætshal', 31, 7);

-- ===========================================================================
-- ANVENDELSE: Anden enhed til idrætsformål
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Anden enhed til idrætsformål', 1, 7),
('Anden enhed til idrætsformål', 2, 8),
('Anden enhed til idrætsformål', 3, 7),
('Anden enhed til idrætsformål', 5, 7),
('Anden enhed til idrætsformål', 6, 7),
('Anden enhed til idrætsformål', 7, 8),
('Anden enhed til idrætsformål', 18, 6),
('Anden enhed til idrætsformål', 22, 8),
('Anden enhed til idrætsformål', 28, 8),
('Anden enhed til idrætsformål', 31, 7);

-- ===========================================================================
-- ANVENDELSE: Feriecenter, center til campingplads mv.
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Feriecenter, center til campingplads mv.', 1, 6),
('Feriecenter, center til campingplads mv.', 2, 7),
('Feriecenter, center til campingplads mv.', 3, 7),
('Feriecenter, center til campingplads mv.', 5, 8),
('Feriecenter, center til campingplads mv.', 6, 8),
('Feriecenter, center til campingplads mv.', 7, 7),
('Feriecenter, center til campingplads mv.', 18, 6),
('Feriecenter, center til campingplads mv.', 22, 9),
('Feriecenter, center til campingplads mv.', 28, 7),
('Feriecenter, center til campingplads mv.', 30, 8),
('Feriecenter, center til campingplads mv.', 31, 8);

-- ===========================================================================
-- ANVENDELSE: Bolig i etageejendom, flerfamiliehus eller to-familiehus
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 3, 7),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 4, 7),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 5, 8),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 6, 8),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 13, 7),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 20, 8),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 21, 6),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 22, 7),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 26, 8),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 29, 6),
('Bolig i etageejendom, flerfamiliehus eller to-familiehus', 31, 7);

-- ===========================================================================
-- ANVENDELSE: Bolig i døgninstitution
-- ===========================================================================
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Bolig i døgninstitution', 2, 8),
('Bolig i døgninstitution', 3, 7),
('Bolig i døgninstitution', 5, 8),
('Bolig i døgninstitution', 6, 8),
('Bolig i døgninstitution', 7, 7),
('Bolig i døgninstitution', 18, 7),
('Bolig i døgninstitution', 22, 10),
('Bolig i døgninstitution', 28, 7),
('Bolig i døgninstitution', 30, 8),
('Bolig i døgninstitution', 31, 8);

-- ===========================================================================
-- ANVENDELSE: Facilitet-baserede (toilet, badeværelse, køkken)
-- Disse anvendelser repræsenterer faciliteter snarere end bygningstyper
-- ===========================================================================

-- Badeværelse i enheden
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Badeværelse i enheden', 5, 9),
('Badeværelse i enheden', 22, 10);

-- Adgang til badeværelse
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Adgang til badeværelse', 5, 8),
('Adgang til badeværelse', 22, 9);

-- Vandskyllende toilet i enheden
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Vandskyllende toilet i enheden', 5, 8),
('Vandskyllende toilet i enheden', 6, 10),
('Vandskyllende toilet i enheden', 31, 7);

-- Vandskyllende toilet uden for enheden
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Vandskyllende toilet uden for enheden', 5, 8),
('Vandskyllende toilet uden for enheden', 6, 10),
('Vandskyllende toilet uden for enheden', 31, 7);

-- Eget køkken med afløb
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Eget køkken med afløb', 5, 7),
('Eget køkken med afløb', 30, 9),
('Eget køkken med afløb', 31, 7);

-- Adgang til fælles køkken
INSERT INTO anvendelse_use_case_mapping (anvendelse_tekst, use_case_id, relevans_score) VALUES
('Adgang til fælles køkken', 5, 7),
('Adgang til fælles køkken', 30, 9),
('Adgang til fælles køkken', 31, 7);


-- ============================================================================
-- DEL 2: HOVEDTABEL - BBR ENHEDER MED USE CASES OG SENSORER
-- ============================================================================

CREATE TABLE bbr_potentiale (
    -- Primær nøgle
    id SERIAL PRIMARY KEY,
    
    -- Geometri
    the_geom GEOMETRY(MultiPoint, 25832),
    
    -- Original BBR identifikation
    id_lokalid UUID,
    kommunekode VARCHAR(4),
    
    -- Registrering
    registrering_fra TIMESTAMPTZ,
    registreringsaktoer TEXT,
    registrering_til TIMESTAMPTZ,
    
    -- Relationer
    adresse_identificerer UUID,
    bygning UUID,
    enh008_uuid_til_moderlejlighed UUID,
    
    -- Anvendelse og boligtype
    enh020_enhedens_anvendelse VARCHAR(10),
    enh023_boligtype VARCHAR(10),
    
    -- Arealer
    enh026_enhedenssamledeareal INTEGER,
    enh027_ereal_til_beboelse INTEGER,
    enh028_ereal_til_erhverv INTEGER,
    enh030_kilde_til_enhedens_erealer VARCHAR(10),
    
    -- Værelser
    enh031_antal_vaerelser INTEGER,
    enh063_antal_vaerelser_til_erhverv INTEGER,
    
    -- Installationer
    enh051_varmeinstallation VARCHAR(10),
    enh052_opvarmningsmiddel VARCHAR(10),
    enh053_supplerende_varme VARCHAR(10),
    
    -- Faciliteter (fra BBR)
    enh065_antal_vandskyllede_toiletter INTEGER,
    enh066_antal_badevaerelser INTEGER,
    enh067_stoejisolering VARCHAR(10),
    
    -- Supplerende arealer og koder
    enh102_heraf_areal1 INTEGER,
    enh103_heraf_areal2 INTEGER,
    enh104_heraf_areal3 INTEGER,
    enh105_supplerende_anvendelseskode1 VARCHAR(10),
    enh106_supplerende_anvendelseskode2 VARCHAR(10),
    enh107_supplerende_anvendelseskode3 VARCHAR(10),
    
    -- Fysiske arealer
    enh127_fysisk_areal_til_beboelse INTEGER,
    enh128_fysisk_areal_til_erhverv INTEGER,
    
    -- Etage og opgang
    etage UUID,
    opgang UUID,
    
    -- Status og adresse
    status VARCHAR(10),
    adressebetegnelse TEXT,
    
    -- Tekstoversættelser
    enh020_enhedens_anvendelse_txt TEXT,
    enh023_boligtype_txt TEXT,
    enh032_toiletforhold_txt TEXT,
    enh033_badeforhold_txt TEXT,
    enh034_koekkenforhold_txt TEXT,
    enh035_energiforsyning_txt TEXT,
    enh045_udlejningsforhold_txt TEXT,
    enh051_varmeinstallation_txt TEXT,
    enh052_opvarmningsmiddel_txt TEXT,
    
    -- =========================================================================
    -- BEREGNEDE FACILITET-TÆLLINGER
    -- =========================================================================
    
    -- Antal relevante toiletter (kun vandskyllende i/udenfor enhed)
    antal_toiletter INTEGER DEFAULT 0,
    
    -- Antal badeværelser
    antal_badevaerelser INTEGER DEFAULT 0,
    
    -- Antal køkkener (kun eget køkken/fælles køkken)
    antal_koekken INTEGER DEFAULT 0,
    
    -- =========================================================================
    -- USE CASES OG IOT SENSORER (JSONB)
    -- =========================================================================
    
    -- JSONB kolonne med identificerede use cases
    use_cases JSONB DEFAULT '[]'::JSONB,
    
    -- JSONB kolonne med kompatible IoT sensorer inkl. antal
    -- Format: [{"id": 1, "type": "...", "antal": 5, "pris_min": 500, "pris_max": 700}, ...]
    iot_sensorer JSONB DEFAULT '[]'::JSONB,
    
    -- =========================================================================
    -- BEREGNEDE INVESTERINGSFELTER
    -- =========================================================================
    
    antal_use_cases INTEGER DEFAULT 0,
    antal_sensor_typer INTEGER DEFAULT 0,
    total_antal_sensorer INTEGER DEFAULT 0,
    
    -- Investering (prisspænd)
    samlet_investering_min_kr NUMERIC(12,2) DEFAULT 0,
    samlet_investering_max_kr NUMERIC(12,2) DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Opret indeks for bedre performance
CREATE INDEX idx_bbr_potentiale_geom ON bbr_potentiale USING GIST (the_geom);
CREATE INDEX idx_bbr_potentiale_anvendelse ON bbr_potentiale (enh020_enhedens_anvendelse);
CREATE INDEX idx_bbr_potentiale_anvendelse_txt ON bbr_potentiale (enh020_enhedens_anvendelse_txt);
CREATE INDEX idx_bbr_potentiale_kommunekode ON bbr_potentiale (kommunekode);
CREATE INDEX idx_bbr_potentiale_use_cases ON bbr_potentiale USING GIN (use_cases);
CREATE INDEX idx_bbr_potentiale_iot_sensorer ON bbr_potentiale USING GIN (iot_sensorer);


-- ============================================================================
-- DEL 3: FUNKTIONER TIL BEREGNING
-- ============================================================================

-- -----------------------------------------------------------------------------
-- 3.1 Funktion til at finde use cases for en anvendelsestekst
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_use_cases_for_anvendelse(p_anvendelse_txt TEXT)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'id', uc.id,
                'navn', uc.use_case_navn,
                'kategori', uc.kategori,
                'relevans', aucm.relevans_score,
                'link', uc.link
            ) ORDER BY aucm.relevans_score DESC
        ),
        '[]'::JSONB
    ) INTO result
    FROM anvendelse_use_case_mapping aucm
    JOIN use_cases uc ON uc.id = aucm.use_case_id
    WHERE aucm.anvendelse_tekst = p_anvendelse_txt;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;


-- -----------------------------------------------------------------------------
-- 3.2 Funktion til at beregne sensorer med antal og priser
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_sensors_with_quantities(
    p_use_case_ids INTEGER[],
    p_antal_toiletter INTEGER,
    p_antal_badevaerelser INTEGER,
    p_antal_koekken INTEGER,
    p_areal_m2 INTEGER
)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    WITH sensor_calculations AS (
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
                ELSE 1
            END AS antal,
            ucsm.er_primaer,
            array_agg(DISTINCT ucsm.use_case_id) AS for_use_cases
        FROM use_case_sensor_mapping ucsm
        JOIN iot_sensor_types ist ON ist.id = ucsm.sensor_type_id
        WHERE ucsm.use_case_id = ANY(p_use_case_ids)
          AND ist.aktiv = TRUE  -- Kun aktive sensorer
        GROUP BY ist.id, ist.sensor_type, ist.pris_min_kr, ist.pris_max_kr, 
                 ucsm.multiplikator_kilde, ucsm.er_primaer
    ),
    -- Aggreger sensorer (samme sensortype kan forekomme med forskellige multiplikatorer)
    aggregated_sensors AS (
        SELECT 
            id,
            sensor_type,
            pris_min_kr,
            pris_max_kr,
            MAX(antal) AS antal,  -- Tag max antal hvis samme sensor bruges flere gange
            BOOL_OR(er_primaer) AS er_primaer,
            array_agg(DISTINCT unnest_val) AS for_use_cases
        FROM sensor_calculations,
             LATERAL unnest(for_use_cases) AS unnest_val
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
        ),
        '[]'::JSONB
    ) INTO result
    FROM aggregated_sensors;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;


-- -----------------------------------------------------------------------------
-- 3.3 Hovedfunktion: Opdater use cases, sensorer og investering for en enhed
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_enhed_potentiale(p_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_anvendelse_txt TEXT;
    v_toiletforhold_txt TEXT;
    v_koekkenforhold_txt TEXT;
    v_use_cases JSONB;
    v_use_case_ids INTEGER[];
    v_sensorer JSONB;
    v_antal_use_cases INTEGER;
    v_antal_sensor_typer INTEGER;
    v_total_antal_sensorer INTEGER;
    v_investering_min NUMERIC;
    v_investering_max NUMERIC;
    v_antal_toiletter INTEGER;
    v_antal_badevaerelser INTEGER;
    v_antal_koekken INTEGER;
    v_areal_m2 INTEGER;
BEGIN
    -- Hent data fra enheden
    SELECT 
        enh020_enhedens_anvendelse_txt,
        enh032_toiletforhold_txt,
        enh034_koekkenforhold_txt,
        COALESCE(enh065_antal_vandskyllede_toiletter, 0),
        COALESCE(enh066_antal_badevaerelser, 0),
        COALESCE(enh026_enhedenssamledeareal, 100)
    INTO 
        v_anvendelse_txt,
        v_toiletforhold_txt,
        v_koekkenforhold_txt,
        v_antal_toiletter,
        v_antal_badevaerelser,
        v_areal_m2
    FROM bbr_potentiale WHERE id = p_id;
    
    -- Beregn antal køkkener baseret på køkkenforhold
    v_antal_koekken := CASE 
        WHEN v_koekkenforhold_txt IN ('Eget køkken med afløb', 'Adgang til fælles køkken') THEN 1 
        ELSE 0 
    END;
    
    -- Juster antal toiletter baseret på toiletforhold
    IF v_toiletforhold_txt NOT IN ('Vandskyllende toilet i enheden', 'Vandskyllende toilet uden for enheden') THEN
        v_antal_toiletter := 0;
    END IF;
    
    -- Hent use cases baseret på anvendelsestekst
    v_use_cases := get_use_cases_for_anvendelse(v_anvendelse_txt);
    
    -- Ekstraher use case IDs
    SELECT COALESCE(
        array_agg((elem->>'id')::INTEGER),
        ARRAY[]::INTEGER[]
    ) INTO v_use_case_ids
    FROM jsonb_array_elements(v_use_cases) elem;
    
    -- Hent sensorer med antal og priser
    v_sensorer := get_sensors_with_quantities(
        v_use_case_ids,
        v_antal_toiletter,
        v_antal_badevaerelser,
        v_antal_koekken,
        v_areal_m2
    );
    
    -- Beregn totaler
    v_antal_use_cases := jsonb_array_length(v_use_cases);
    v_antal_sensor_typer := jsonb_array_length(v_sensorer);
    
    -- Beregn total antal sensorer og investering
    SELECT 
        COALESCE(SUM((elem->>'antal')::INTEGER), 0),
        COALESCE(SUM((elem->>'pris_total_min')::NUMERIC), 0),
        COALESCE(SUM((elem->>'pris_total_max')::NUMERIC), 0)
    INTO v_total_antal_sensorer, v_investering_min, v_investering_max
    FROM jsonb_array_elements(v_sensorer) elem;
    
    -- Opdater enheden
    UPDATE bbr_potentiale SET
        antal_toiletter = v_antal_toiletter,
        antal_badevaerelser = v_antal_badevaerelser,
        antal_koekken = v_antal_koekken,
        use_cases = v_use_cases,
        iot_sensorer = v_sensorer,
        antal_use_cases = v_antal_use_cases,
        antal_sensor_typer = v_antal_sensor_typer,
        total_antal_sensorer = v_total_antal_sensorer,
        samlet_investering_min_kr = v_investering_min,
        samlet_investering_max_kr = v_investering_max,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_id;
END;
$$ LANGUAGE plpgsql;


-- -----------------------------------------------------------------------------
-- 3.4 Batch-funktion: Opdater alle enheder
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_all_potentialer()
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER := 0;
    rec RECORD;
BEGIN
    FOR rec IN SELECT id FROM bbr_potentiale LOOP
        PERFORM update_enhed_potentiale(rec.id);
        v_count := v_count + 1;
    END LOOP;
    
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- DEL 4: VIEWS TIL ANALYSE
-- ============================================================================

-- -----------------------------------------------------------------------------
-- 4.1 View: Oversigt over investering per anvendelsestype
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_investering_per_anvendelse AS
SELECT 
    enh020_enhedens_anvendelse_txt AS anvendelse,
    COUNT(*) AS antal_enheder,
    SUM(enh026_enhedenssamledeareal) AS samlet_areal_m2,
    SUM(antal_toiletter) AS total_toiletter,
    SUM(antal_badevaerelser) AS total_badevaerelser,
    SUM(antal_koekken) AS total_koekken,
    ROUND(AVG(antal_use_cases), 1) AS gns_use_cases,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS investering_min_kr,
    SUM(samlet_investering_max_kr) AS investering_max_kr
FROM bbr_potentiale
WHERE enh020_enhedens_anvendelse_txt IS NOT NULL
GROUP BY enh020_enhedens_anvendelse_txt
ORDER BY investering_max_kr DESC;


-- -----------------------------------------------------------------------------
-- 4.2 View: Sensor anvendelse med priser
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_sensor_anvendelse AS
SELECT 
    sensor_elem->>'type' AS sensor_type,
    COUNT(DISTINCT bp.id) AS antal_enheder,
    SUM((sensor_elem->>'antal')::INTEGER) AS total_antal_sensorer,
    SUM((sensor_elem->>'pris_total_min')::NUMERIC) AS total_pris_min,
    SUM((sensor_elem->>'pris_total_max')::NUMERIC) AS total_pris_max
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.iot_sensorer) AS sensor_elem
GROUP BY sensor_elem->>'type'
ORDER BY total_antal_sensorer DESC;


-- -----------------------------------------------------------------------------
-- 4.3 View: Use case popularitet
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_use_case_popularitet AS
SELECT 
    uc_elem->>'navn' AS use_case_navn,
    uc_elem->>'kategori' AS kategori,
    COUNT(DISTINCT bp.id) AS antal_enheder
FROM bbr_potentiale bp,
     jsonb_array_elements(bp.use_cases) AS uc_elem
GROUP BY uc_elem->>'navn', uc_elem->>'kategori'
ORDER BY antal_enheder DESC;


-- -----------------------------------------------------------------------------
-- 4.4 View: Investering per kommune
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_investering_per_kommune AS
SELECT 
    kommunekode,
    COUNT(*) AS antal_enheder,
    SUM(total_antal_sensorer) AS total_sensorer,
    SUM(samlet_investering_min_kr) AS investering_min_kr,
    SUM(samlet_investering_max_kr) AS investering_max_kr
FROM bbr_potentiale
WHERE kommunekode IS NOT NULL
GROUP BY kommunekode
ORDER BY investering_max_kr DESC;


-- -----------------------------------------------------------------------------
-- 4.5 View: Facilitet oversigt
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_facilitet_oversigt AS
SELECT 
    enh020_enhedens_anvendelse_txt AS anvendelse,
    COUNT(*) AS antal_enheder,
    SUM(antal_toiletter) AS total_toiletter,
    SUM(antal_badevaerelser) AS total_badevaerelser,
    SUM(antal_koekken) AS total_koekken,
    SUM(antal_toiletter + antal_badevaerelser + antal_koekken) AS total_faciliteter
FROM bbr_potentiale
WHERE enh020_enhedens_anvendelse_txt IS NOT NULL
GROUP BY enh020_enhedens_anvendelse_txt
ORDER BY total_faciliteter DESC;


-- ============================================================================
-- DEL 5: HJÆLPEFUNKTION TIL GRAFANA
-- ============================================================================

CREATE OR REPLACE FUNCTION get_lat_lng(geom GEOMETRY)
RETURNS TABLE(latitude DOUBLE PRECISION, longitude DOUBLE PRECISION) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ST_Y(ST_Transform(ST_Centroid(geom), 4326)) AS latitude,
        ST_X(ST_Transform(ST_Centroid(geom), 4326)) AS longitude;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- ============================================================================
-- DEL 6: EKSEMPEL PÅ IMPORT MED FILTRERING
-- ============================================================================

-- Liste over gyldige anvendelsestekster
/*
INSERT INTO bbr_potentiale (
    the_geom, id_lokalid, kommunekode, registrering_fra, registreringsaktoer,
    registrering_til, adresse_identificerer, bygning, enh008_uuid_til_moderlejlighed,
    enh020_enhedens_anvendelse, enh023_boligtype, enh026_enhedenssamledeareal,
    enh027_ereal_til_beboelse, enh028_ereal_til_erhverv, enh030_kilde_til_enhedens_erealer,
    enh031_antal_vaerelser, enh051_varmeinstallation, enh052_opvarmningsmiddel,
    enh053_supplerende_varme, enh063_antal_vaerelser_til_erhverv,
    enh065_antal_vandskyllede_toiletter, enh066_antal_badevaerelser, enh067_stoejisolering,
    enh102_heraf_areal1, enh103_heraf_areal2, enh104_heraf_areal3,
    enh105_supplerende_anvendelseskode1, enh106_supplerende_anvendelseskode2,
    enh107_supplerende_anvendelseskode3, enh127_fysisk_areal_til_beboelse,
    enh128_fysisk_areal_til_erhverv, etage, opgang, status, adressebetegnelse,
    enh020_enhedens_anvendelse_txt, enh023_boligtype_txt, enh032_toiletforhold_txt,
    enh033_badeforhold_txt, enh034_koekkenforhold_txt, enh035_energiforsyning_txt,
    enh045_udlejningsforhold_txt, enh051_varmeinstallation_txt, enh052_opvarmningsmiddel_txt
)
SELECT 
    the_geom, id_lokalid::UUID, kommunekode, registrering_fra, registreringsaktoer,
    registrering_til, adresse_identificerer::UUID, bygning::UUID, 
    enh008_uuid_til_moderlejlighed::UUID,
    enh020_enhedens_anvendelse, enh023_boligtype, enh026_enhedenssamledeareal,
    enh027_ereal_til_beboelse, enh028_ereal_til_erhverv, enh030_kilde_til_enhedens_erealer,
    enh031_antal_vaerelser, enh051_varmeinstallation, enh052_opvarmningsmiddel,
    enh053_supplerende_varme, enh063_antal_vaerelser_til_erhverv,
    enh065_antal_vandskyllede_toiletter, enh066_antal_badevaerelser, enh067_stoejisolering,
    enh102_heraf_areal1, enh103_heraf_areal2, enh104_heraf_areal3,
    enh105_supplerende_anvendelseskode1, enh106_supplerende_anvendelseskode2,
    enh107_supplerende_anvendelseskode3, enh127_fysisk_areal_til_beboelse,
    enh128_fysisk_areal_til_erhverv, etage::UUID, opgang::UUID, status, adressebetegnelse,
    enh020_enhedens_anvendelse_txt, enh023_boligtype_txt, enh032_toiletforhold_txt,
    enh033_badeforhold_txt, enh034_koekkenforhold_txt, enh035_energiforsyning_txt,
    enh045_udlejningsforhold_txt, enh051_varmeinstallation_txt, enh052_opvarmningsmiddel_txt
FROM din_bbr_tabel
WHERE enh020_enhedens_anvendelse_txt IN (
    'Badeværelse i enheden',
    'Enhed til kontor',
    'Vandskyllende toilet i enheden',
    '(UDFASES) Offentlig administration.',
    'Bibliotek',
    'Forsamlingshus',
    'Anden enhed til kulturelle formål',
    'Grundskole',
    'Universitet',
    'Anden enhed til undervisning og forskning',
    'Sundhedscenter, lægehus, fødeklinik mv.',
    'Daginstitution',
    'Klubhus i forbindelse med fritid- og idræt',
    'Svømmehal',
    'Idrætshal',
    'Anden enhed til idrætsformål',
    'Eget køkken med afløb',
    'Adgang til fælles køkken',
    'Adgang til badeværelse',
    'Vandskyllende toilet uden for enheden',
    'Feriecenter, center til campingplads mv.',
    'Bolig i etageejendom, flerfamiliehus eller to-familiehus',
    'Bolig i døgninstitution',
    '(UDFASES) Daginstitution.'
);

-- Efter import: Beregn potentialer
SELECT update_all_potentialer();
*/


-- ============================================================================
-- SLUTNING
-- ============================================================================
-- For at køre dette script:
-- 1. Opret forbindelse til din PostGIS-database
-- 2. Kør hele scriptet (opretter tabeller, funktioner, views)
-- 3. Indsæt data fra din BBR-tabel med filtrering (tilpas DEL 6)
-- 4. Kør: SELECT update_all_potentialer();
-- 5. Brug views og Grafana queries til analyse
-- ============================================================================
