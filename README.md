# 🏢 IoT Potentialeberegner

Et værktøj til beregning af IoT-sensorinvesteringer baseret på danske BBR-data (Bygnings- og Boligregistret).

## 📋 Oversigt

Potentialeberegneren analyserer bygningsdata og identificerer relevante IoT use cases baseret på anvendelsestype og faciliteter. Systemet beregner antal sensorer og investeringsbehov.

**Hovedfunktioner:**
- Identificerer IoT use cases per bygningstype (33 forskellige use cases)
- Beregner sensorantal baseret på faciliteter (toiletter, badeværelser, køkkener, areal)
- Viser investeringsbehov med prisspænd (min/max)
- Sammenligner enkelt-sensorer med kombo-sensorer for besparelser
- Streamlit dashboard med interaktive visualiseringer

## 🗂️ Filstruktur

```
├── potentialeberegner_v2.sql      # Hovedscript - tabeller, funktioner, views
├── bygning_views.sql              # Views til bygningsniveau-aggregering
├── kombo_sensorer.sql             # Kombinations-sensorer med besparelsesberegning
├── grafana_queries_v2.sql         # Queries til Grafana dashboards
├── streamlit_app/
│   ├── app.py                     # Streamlit dashboard
│   ├── requirements.txt           # Python dependencies
│   └── secrets.toml.template      # Database credentials template
└── potentialeberegner_v2_dokumentation.txt  # Detaljeret dokumentation
```

## 🚀 Installation

### 1. Database setup

Kør SQL-scripts i denne rækkefølge:

```sql
-- 1. Hovedscript (tabeller, funktioner, basis-views)
\i potentialeberegner_v2.sql

-- 2. Bygnings-views
\i bygning_views.sql

-- 3. Kombo-sensorer (valgfrit, men anbefalet)
\i kombo_sensorer.sql
```

### 2. Importer BBR-data

```sql
INSERT INTO potentialeberegner.bbr_potentiale (...)
SELECT ...
FROM din_bbr_tabel
WHERE enh020_enhedens_anvendelse_txt IN (
    'Daginstitution', 'Grundskole', 'Universitet',
    'Enhed til kontor', 'Bibliotek', 'Svømmehal',
    -- ... se komplet liste i dokumentationen
);
```

### 3. Beregn potentialer

```sql
SELECT potentialeberegner.update_all_potentialer();
```

### 4. Streamlit dashboard

```bash
cd streamlit_app
pip install -r requirements.txt

# Opret secrets.toml fra template
cp secrets.toml.template .streamlit/secrets.toml
# Rediger secrets.toml med dine database credentials

streamlit run app.py
```

## 📊 Streamlit Dashboard

Dashboardet viser:

**Overblik (alle bygninger):**
- Samlet statistik (bygninger, enheder, sensorer, investering)
- Fordeling per anvendelsestype og kommune
- Interaktivt kort med bygningsmarkører
- Top 20 bygninger med størst investeringspotentiale

**Detaljevisning (enkelt bygning):**
- Bygningsoversigt med adresse, anvendelse, faciliteter
- Sensoroversigt med cirkeldiagram og use case-kobling
- Kombo-alternativer med besparelsesberegning
- Use case breakdown matrix

## 💡 Kombo-sensorer

Mange IoT-sensorer kombinerer flere funktioner i én enhed. Systemet beregner besparelser ved at bruge kombos i stedet for separate sensorer.

**Eksempel:**

| Sensor | Pris per stk |
|--------|-------------|
| Temperaturføler | 400 kr |
| Luftfugtighed | 500 kr |
| CO2-måler | 800 kr |
| **Sum (separate)** | **1.700 kr** |
| **Kombo-pris** | **1.200 kr** |
| **Besparelse** | **500 kr** |

**Inkluderede kombos:**

| Kombo | Pris |
|-------|------|
| Temperatur + Luftfugtighed | 400-500 kr |
| Temperatur + PIR | 400-500 kr |
| Temperatur + Luftfugtighed + CO2 | 1.100-1.200 kr |
| Temperatur + Luftfugtighed + CO2 + PIR | 1.200-1.300 kr |
| Temperatur + Luftfugtighed + Støjsensor | 1.200-1.300 kr |

## 🔧 Administration

### Deaktiver sensortype

```sql
-- Deaktiver
UPDATE potentialeberegner.iot_sensor_types 
SET aktiv = FALSE WHERE sensor_type = 'Vindmåler';

-- Genberegn
SELECT potentialeberegner.update_all_potentialer();
```

### Opdater sensorpriser

```sql
UPDATE potentialeberegner.iot_sensor_types 
SET pris_min_kr = 400, pris_max_kr = 900
WHERE sensor_type = 'CO2-måler';

SELECT potentialeberegner.update_all_potentialer();
```

### Tilføj ny kombo

```sql
-- Opret kombo
INSERT INTO potentialeberegner.iot_sensor_kombos (kombo_navn, pris_min_kr, pris_max_kr) 
VALUES ('Temperatur + Lux', 450, 550);

-- Tilføj komponenter
INSERT INTO potentialeberegner.kombo_komponenter (kombo_id, sensor_type_id) VALUES
((SELECT id FROM potentialeberegner.iot_sensor_kombos WHERE kombo_navn = 'Temperatur + Lux'), 10),
((SELECT id FROM potentialeberegner.iot_sensor_kombos WHERE kombo_navn = 'Temperatur + Lux'), 35);
```

## 📈 Grafana Integration

Se `grafana_queries_v2.sql` for komplette queries tilpasset Grafana 8.5.2:

- Geomap med bygninger (latitude/longitude)
- Statistik-panels
- Dropdown-variabler (kommune, anvendelse)

## 📐 Datamodel

### Hovedtabeller

| Tabel | Beskrivelse |
|-------|-------------|
| `bbr_potentiale` | BBR-data med beregnede use cases og sensorer |
| `use_cases` | 33 IoT use cases |
| `iot_sensor_types` | 36 sensortyper med priser |
| `use_case_sensor_mapping` | Relation: use case → sensorer |
| `anvendelse_use_case_mapping` | Relation: anvendelse → use cases |
| `iot_sensor_kombos` | Kombinations-sensorer |
| `kombo_komponenter` | Kombo-komponenter |

### Multiplikator-logik

Sensorantal beregnes ud fra `multiplikator_kilde`:

| Kilde | Beskrivelse |
|-------|-------------|
| `enhed` | 1 sensor per enhed |
| `toilet` | 1 sensor per toilet |
| `badevaerelser` | 1 sensor per badeværelse |
| `koekken` | 1 sensor per køkken |
| `areal_per_100m2` | 1 sensor per 100 m² |

## 📄 JSONB-struktur

### `use_cases` kolonne
```json
[
  {
    "id": 2,
    "navn": "Behovsstyret ventilation via CO2-måling",
    "kategori": "ventilation",
    "relevans": 9
  }
]
```

### `iot_sensorer` kolonne
```json
[
  {
    "id": 33,
    "type": "CO2-måler",
    "antal": 3,
    "pris_min": 350,
    "pris_max": 800,
    "pris_total_min": 1050,
    "pris_total_max": 2400,
    "for_use_cases": [2, 25]
  }
]
```

## 📝 Licens

MIT License

## 🤝 Bidrag

Pull requests er velkomne. For større ændringer, åbn venligst et issue først.
