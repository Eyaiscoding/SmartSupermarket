# Smart Supermarket B2G Platform

Plateforme de gestion énergétique Building-to-Grid (B2G) pour un supermarché intelligent connecté à un microgrid et macrogrid. Le système gère intelligemment la consommation d'énergie, la production solaire PV, le stockage par batteries, et les échanges peer-to-peer (P2P) -- tout en garantissant une couverture électrique fiable et en respectant les hiérarchies de priorité des charges critiques.

**Architecture:** Microservices événementiels avec Apache Kafka, permettant un scaling indépendant, un déploiement autonome et des choix technologiques flexibles pour chaque service.

---

## 🚀 Démarrage Rapide

```bash
# Démarrer l'ensemble des 9 services
docker compose up --build

# Vérifier l'état des services
docker compose ps

# API disponible : http://localhost:8000/docs
```

**Services actifs:**
- ✅ Backend API (FastAPI)
- ✅ Forecasting Service (AI/ML)
- ✅ MPC Service (Optimisation)
- ✅ DERMS Service (Dispatch équipements)
- ✅ Compliance Service (Règles réglementaires)
- ✅ Apache Kafka + Zookeeper
- ✅ TimescaleDB, Redis, Mosquitto

---

## 📊 Architecture

### Vue d'ensemble des microservices

```
Edge Sensors → MQTT → telemetry.raw (Kafka)
                           ↓
                    Forecasting Service (AI/ML)
                           ↓
                  forecasting.predictions (Kafka)
                           ↓
                      MPC Service (Optimisation CVXPY)
                           ↓
                    mpc.decisions (Kafka)
                           ↓
                     DERMS Service (Dispatch)
                           ↓
                   derms.dispatch (Kafka)
                           ↓
                  Compliance Service (Règles R1-R6)
                           ↓
                compliance.reports (Kafka) → TimescaleDB
```

**Bénéfices clés:**
- ✅ Scaling indépendant par service
- ✅ Isolation des pannes
- ✅ Développement parallèle par équipes
- ✅ Replay & recovery via Kafka topics
- ✅ Rétrocompatible avec l'API v2 monolithique

---

## 🏗️ Services

| Service | Rôle | Technologies |
|---------|------|-------------|
| **Backend API** | Gateway REST/WebSocket | FastAPI, Python 3.13 |
| **Forecasting** | Prédictions AI/ML, détection d'anomalies | scikit-learn, pandas |
| **MPC** | Optimisation Model Predictive Control | CVXPY, NumPy |
| **DERMS** | Dispatch équipements, traduction commandes | Python, contraintes physiques |
| **Compliance** | Application règles réglementaires (R1-R6) | Python, rule engine |
| **Kafka** | Event streaming backbone | Apache Kafka 7.6.0 |
| **TimescaleDB** | Base de données time-series | PostgreSQL 16 + Timescale |
| **Redis** | Cache basse latence | Redis 7 |
| **Mosquitto** | Ingestion télémétrie MQTT | Eclipse Mosquitto 2 |

---

## 📡 Kafka Topics

| Topic | Partitions | Rétention | Usage |
|-------|------------|-----------|-------|
| `telemetry.raw` | 4 | 7 jours | Données capteurs brutes depuis appareils edge |
| `forecasting.predictions` | 2 | 24 heures | Sorties forecasting AI/ML |
| `mpc.decisions` | 1 | 30 jours | Décisions d'optimisation MPC |
| `derms.dispatch` | 2 | 30 jours | Commandes dispatch équipements |
| `compliance.reports` | 1 | 1 an | Rapports conformité réglementaire |

---

## 🔗 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | Health check infrastructure |
| GET | `/api/v1/latest` | État pipeline le plus récent (Redis/TimescaleDB) |
| GET | `/api/v1/history?start=...&end=...` | Historique par plage temporelle |
| POST | `/api/v1/scenario` | Déclenchement scénario (body: `{"scenario": "none"}`) |
| WS | `/ws/stream` | WebSocket : flux temps-réel des sorties pipeline |

---

## 📁 Dataset

- **Fichier:** `data/dataset.csv`
- **Type:** Données synthétiques générées pour simulation
- **Résolution:** Intervalles de 15 minutes
- **Période:** 1er juin - 30 septembre 2025 (4 mois)
- **Taille:** 11,712 lignes, 30 colonnes (~2 MB)

---

## 🧪 Tests

```bash
# Tests unitaires et d'intégration
python -m pytest tests/ -v

# Tests spécifiques P2P
python -m pytest tests/test_p2p.py -q

# Lint
ruff check .
```

---

## 📦 Tech Stack

- **Core:** Python 3.13, Apache Kafka 7.6.0, Docker Compose
- **Backend:** FastAPI, Pydantic, uvicorn
- **ML/AI:** scikit-learn, pandas, NumPy
- **Optimisation:** CVXPY
- **Messaging:** kafka-python, paho-mqtt
- **Persistence:** TimescaleDB (PostgreSQL 16), Redis 7
- **CI/CD:** GitHub Actions, pytest, ruff

---

## 📖 Documentation Complémentaire

- **`ARCHITECTURE_TECHNIQUE.md`** : Description détaillée de l'architecture, technologies et fonctionnement
- **`GUIDE_PRESENTATION.md`** : Guide de présentation pour expliquer l'interface utilisateur et les scénarios
