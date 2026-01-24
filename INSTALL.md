# 🚀 Hurtig Installation

## Database Setup

```sql
-- 1. Opret schema
CREATE SCHEMA IF NOT EXISTS potentialeberegner;

-- 2. Kør hovedscripts i rækkefølge
\i potentialeberegner_v2.sql
\i bygning_views.sql
\i kombo_sensorer.sql

-- 3. Importer dine BBR-data
INSERT INTO potentialeberegner.bbr_potentiale (...)
SELECT ... FROM din_bbr_tabel WHERE ...;

-- 4. Beregn potentialer
SELECT potentialeberegner.update_all_potentialer();
```

## Streamlit Dashboard

```bash
cd streamlit_app

# Installer dependencies
pip install -r requirements.txt

# Konfigurer database
mkdir -p .streamlit
cp secrets.toml.template .streamlit/secrets.toml
# Rediger .streamlit/secrets.toml med dine credentials

# Start app
streamlit run app.py
```

## Verificer installation

```sql
-- Tjek antal enheder
SELECT COUNT(*) FROM potentialeberegner.bbr_potentiale;

-- Tjek samlet statistik
SELECT * FROM potentialeberegner.v_bygning_statistik;

-- Tjek kombos
SELECT * FROM potentialeberegner.v_kombo_oversigt;

-- Test kombo-beregning
SELECT potentialeberegner.get_kombo_alternativer(
    (SELECT bygning FROM potentialeberegner.bbr_potentiale LIMIT 1)
);
```
