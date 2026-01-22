# Potentialeberegner - IoT Investeringsrapport

Streamlit webapp til visualisering af BBR-data og IoT investeringspotentiale.

## 🚀 Deployment til Streamlit Cloud

### 1. Opret GitHub Repository

```bash
# Initialiser git repo
git init
git add .
git commit -m "Initial commit"

# Opret repo på GitHub og push
git remote add origin https://github.com/DIT-BRUGERNAVN/potentialeberegner.git
git branch -M main
git push -u origin main
```

### 2. Deploy på Streamlit Cloud

1. Gå til [share.streamlit.io](https://share.streamlit.io)
2. Log ind med GitHub
3. Klik "New app"
4. Vælg dit repository og `app.py`
5. Klik "Deploy"

### 3. Tilføj Database Secrets

1. Gå til din app på Streamlit Cloud
2. Klik "Settings" (⚙️) → "Secrets"
3. Indsæt følgende (med dine rigtige credentials):

```toml
[database]
host = "din-database-host.example.com"
port = 5432
database = "din_database"
user = "din_bruger"
password = "din_adgangskode"

schema = "potentialeberegner"
```

4. Klik "Save"
5. App'en genstarter automatisk

## 💻 Lokal Udvikling

### Installation

```bash
# Opret virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# eller: venv\Scripts\activate  # Windows

# Installer dependencies
pip install -r requirements.txt
```

### Konfigurer Secrets

```bash
# Opret secrets mappe
mkdir -p .streamlit

# Kopier template
cp secrets.toml.template .streamlit/secrets.toml

# Rediger med dine credentials
nano .streamlit/secrets.toml
```

### Kør App

```bash
streamlit run app.py
```

App'en åbner på http://localhost:8501

## 📁 Filstruktur

```
streamlit_app/
├── app.py                    # Hovedapplikation
├── requirements.txt          # Python dependencies
├── secrets.toml.template     # Template til credentials
├── .gitignore               # Git ignore (inkl. secrets)
└── README.md                # Denne fil
```

## 🔒 Sikkerhed

- **secrets.toml** må ALDRIG committes til git
- Credentials gemmes krypteret i Streamlit Cloud
- Database skal tillade forbindelser fra Streamlit Cloud's IP-ranges

## 🎨 Features

- **Filterbar**: Filtrer på kommune, adresse eller bygning ID
- **Sektionsvalg**: Vælg hvilke sektioner der vises
- **Interaktivt kort**: Leaflet kort med farver efter anvendelse
- **Grafer**: Plotly grafer med investering, sensorer, use cases
- **Responsivt**: Tilpasser sig skærmstørrelse

## 📊 Database Krav

App'en forventer følgende views/tabeller i schema `potentialeberegner`:

- `bbr_potentiale` - Hovedtabel med BBR-data
- `v_bygning_geomap` - View med aggregeret bygningsdata og geometri

Se `potentialeberegner_v2.sql` for komplet database setup.
