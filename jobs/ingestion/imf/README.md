# Source IMF DataMapper — Ingestion

Extraction des séries temporelles macro-économiques du **FMI (Fonds Monétaire International)**
via l'[API publique DataMapper v1](https://www.imf.org/external/datamapper/api/v1/).

---

## Vue d'ensemble

| Propriété | Valeur |
|---|---|
| **Source** | IMF DataMapper API v1 |
| **URL de base** | `https://www.imf.org/external/datamapper/api/v1` |
| **Authentification** | Aucune (API publique) |
| **Format** | JSON |
| **Couverture pays** | 241 pays / régions / groupes analytiques |
| **Indicateurs disponibles** | 133 (WEO, FPP, AFRREO, FM…) |
| **Fréquence de mise à jour** | Semi-annuelle (publications WEO : mai et novembre) |
| **Output Data Lake** | `data/datalake/raw/imf/indicators/{date}/data.json` |
| **Output métadonnées** | `data/datalake/raw/imf/meta/indicators.json` · `countries.json` |

---

## Endpoints disponibles

| Endpoint | Description | Nb. d'items |
|---|---|---|
| `/indicators` | Liste de tous les indicateurs disponibles | 133 |
| `/countries` | Liste des pays (codes ISO 3 lettres + libellés) | 241 |
| `/regions` | Régions géographiques définies | — |
| `/groups` | Groupes analytiques définis | — |

Chaque endpoint retourne un objet JSON dont les **clés sont les IDs** à utiliser pour récupérer les séries temporelles.

### Structure d'un indicateur (`/indicators`)

```json
{
  "indicators": {
    "NGDP_RPCH": {
      "label": "Real GDP growth",
      "description": "Gross domestic product is the most commonly used...",
      "source": "World Economic Outlook (October 2025)",
      "unit": "Annual percent change",
      "dataset": "WEO"
    }
  }
}
```

### Structure d'un pays (`/countries`)

```json
{
  "countries": {
    "FRA": { "label": "France" },
    "USA": { "label": "United States" },
    "CHN": { "label": "China, People's Republic of" }
  }
}
```

### Récupération d'une série temporelle

```
GET /NGDP_RPCH              → croissance PIB réel, tous les pays
GET /NGDP_RPCH/USA/CHN      → USA + Chine uniquement
GET /NGDP_RPCH?periods=2019,2020  → filtrée sur 2019-2020
```

---

## Indicateurs par défaut (6 indicateurs macro WEO)

Configurés dans `config.yaml` et la variable `IMF_INDICATORS`.

| Code | Libellé | Unité | Dataset |
|---|---|---|---|
| `NGDP_RPCH` | Real GDP growth | Annual percent change | WEO |
| `PCPIPCH` | Inflation rate, average consumer prices | Annual percent change | WEO |
| `LUR` | Unemployment rate | Percent | WEO |
| `BCA_NGDPD` | Current account balance, percent of GDP | Percent of GDP | WEO |
| `GGXCNL_NGDP` | General government net lending/borrowing | Percent of GDP | WEO |
| `GGXWDG_NGDP` | General government gross debt | Percent of GDP | WEO |

> La liste complète des 133 indicateurs est disponible dans
> `data/datalake/raw/imf/meta/indicators.json`.

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `IMF_BASE_URL` | `https://www.imf.org/external/datamapper/api/v1` | URL de base de l'API |
| `IMF_TIMEOUT` | `60` | Timeout HTTP en secondes |
| `IMF_INDICATORS` | *(6 indicateurs WEO)* | Codes séparés par virgule |
| `IMF_YEAR_FROM` | `2000` | Année de début incluse (filtre côté client) |
| `IMF_YEAR_TO` | *(année en cours)* | Année de fin incluse |
| `DATALAKE_PATH` | `./data/datalake` | Répertoire racine du Data Lake |

---

## Pipeline — `extract_imf.py`

```
fetch_metadata           (timeout 60 s)
    ↓  {indicators_meta, countries_meta}
fetch_raw_data           (retry ×3 · delay 10 s · timeout 600 s)
    ↓  {raw_data, indicators_fetched, record_count_raw}
validate_raw
    ↓  {status, empty_indicators}
normalize_records        (filtre années, labels, flatten ISO3/année)
    ↓  {records, record_count, null_value_count}
load_to_datalake         (partition par date)
```

### Format de sortie — record normalisé

```json
{
  "indicator":       "NGDP_RPCH",
  "indicator_label": "Real GDP growth",
  "country":         "FRA",
  "country_label":   "France",
  "year":            2024,
  "value":           1.1
}
```

**Chiffres typiques (run 2026-04-12, filtre 2000→2026) :**

| Indicateur | Pays couverts | Points de données |
|---|---|---|
| `NGDP_RPCH` | 229 | 10 714 |
| `PCPIPCH` | 228 | 10 616 |
| `LUR` | 122 | 5 048 |
| `BCA_NGDPD` | 228 | 10 356 |
| `GGXCNL_NGDP` | 229 | 8 650 |
| `GGXWDG_NGDP` | 227 | 7 925 |
| **Total** | — | **33 227** |

---

## Lancement

```bash
# Run standard (6 indicateurs, 2000 → aujourd'hui)
python -m jobs.ingestion.imf.extract_imf

# Restreindre à 2 indicateurs et une plage temporelle
IMF_INDICATORS=NGDP_RPCH,PCPIPCH IMF_YEAR_FROM=2010 IMF_YEAR_TO=2023 \
  python -m jobs.ingestion.imf.extract_imf

# Ajouter un indicateur hors liste par défaut
IMF_INDICATORS=NGDP_RPCH,PCPIPCH,LP \
  python -m jobs.ingestion.imf.extract_imf

# Data Lake alternatif
DATALAKE_PATH=/tmp/datalake python -m jobs.ingestion.imf.extract_imf

# Timeout réduit (test / CI)
IMF_TIMEOUT=30 python -m jobs.ingestion.imf.extract_imf
```

---

## Structure des fichiers

```
jobs/ingestion/imf/
├── __init__.py
├── README.md          ← ce fichier
├── client.py          ← IMFClient (urllib stdlib, zero dépendance)
├── config.yaml        ← indicateurs par défaut, env vars documentées
└── extract_imf.py     ← job @step/@job (5 steps)

data/datalake/raw/imf/
├── meta/
│   ├── indicators.json   ← 133 indicateurs (label, description, unit, dataset)
│   └── countries.json    ← 241 pays/régions (code ISO3 → label)
└── indicators/
    └── {YYYY-MM-DD}/
        └── data.json     ← records normalisés (array JSON)
```

---

## Notes techniques

- **Zéro dépendance externe** — `IMFClient` utilise uniquement `urllib` de la stdlib.
- **User-Agent** — ne pas envoyer de User-Agent personnalisé ; le WAF IMF accepte
  `Python-urllib/3.x` (valeur par défaut de `urllib`) mais peut bloquer les UA custom.
- **Valeurs nulles** — conservées dans le Data Lake (`"value": null`) pour traçabilité ;
  filtrées ou imputées en couche staging.
- **Agrégats régionaux** — l'API retourne aussi des codes non-ISO comme `WEOWORLD`,
  `G7`, `OEMDC` etc. ; conservés en raw, filtrables en staging via `len(iso3) == 3`.
- **Publications WEO** — les données sont mises à jour 2× par an (avril/octobre) ;
  une run semi-annuelle suffit. Les projections futures (années > en cours) sont
  incluses dans les réponses de l'API.
