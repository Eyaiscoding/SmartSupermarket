# Guide de Présentation - Plateforme Smart Supermarket B2G

## 📋 Vue d'Ensemble

Ce guide explique comment présenter l'interface utilisateur et le fonctionnement de la plateforme Smart Supermarket B2G. Il détaille l'origine des chiffres, des graphiques et des métriques affichés, ainsi que le fonctionnement en coulisses lors de l'exécution des scénarios.

---

## 🎯 Objectif de la Plateforme

La plateforme B2G (Building-to-Grid) gère intelligemment l'énergie d'un supermarché connecté à un microgrid local et au réseau électrique principal (macrogrid). L'objectif est de :

1. **Garantir la fiabilité électrique** : Assurer l'alimentation continue des équipements critiques (réfrigération)
2. **Minimiser les coûts** : Réduire la facture énergétique via optimisation intelligente
3. **Exploiter la flexibilité** : Utiliser la batterie et moduler les charges (HVAC, éclairage, caisses)
4. **Respecter les contraintes** : Suivre les règles réglementaires et les limites de confort

---

## 🖥️ Structure de l'Interface Dashboard

### Vue Principale : État du Système en Temps Réel

Le dashboard affiche l'état actuel du système énergétique du supermarché. Voici d'où proviennent les informations :

#### 1. **Coverage Ratio (Ratio de Couverture)**
**Affiché :** Jauge circulaire ou barre de progression (0% - 100%)

**Calcul :**
```
Coverage Ratio = (Énergie Disponible) / (Consommation Totale) × 100%

Énergie Disponible = Production PV + Décharge Batterie + Import Grid + P2P
```

**Code source :** `src/compliance/checker.py` → fonction `calculate_coverage_ratio()`

**Interprétation :**
- 🟢 **NORMAL** (≥ 95%) : Couverture suffisante, système stable
- 🟡 **AT_RISK** (90-95%) : Situation tendue, délestage possible
- 🔴 **CRITICAL** (< 90%) : Risque de rupture électrique

**Exemple sur le dashboard :**
```
Coverage Ratio: 94.2%
Status: AT_RISK
```

---

#### 2. **État de Charge Batterie (SOC)**
**Affiché :** Jauge batterie avec pourcentage et indication visuelle

**Source données :** 
- Dataset : Colonne `battery_soc_percent` dans `data/dataset.csv`
- Mise à jour : Après chaque décision MPC (charge/décharge)

**Code source :** `src/mpc/coordinator.py` → calcul `SOC[t+1] = SOC[t] + (P_battery × Δt × η) / capacité_batterie`

**Contraintes affichées :**
- 🔴 Zone rouge : SOC < 15% (proche limite basse 10%)
- 🟢 Zone verte : SOC 20-80% (plage optimale)
- 🟡 Zone jaune : SOC > 85% (proche limite haute 95%)

**Exemple sur le dashboard :**
```
Battery SOC: 62.3%
Status: Optimal
Capacity: 100 kWh
Available Energy: 62.3 kWh
```

---

#### 3. **Graphique Bilan Énergétique**
**Affiché :** Graphique en barres empilées ou diagramme de flux Sankey

**Composantes :**
- 🔵 **Production PV** (colonne `pv_generation_kw`)
- 🟣 **Batterie** (colonne `battery_power_kw` — positif = charge, négatif = décharge)
- 🟢 **Grid** (colonne `grid_power_kw` — positif = import, négatif = export)
- 🟠 **P2P** (colonne `p2p_energy_kw` — échange avec voisins)
- 🔴 **Consommation** (colonne `energy_consumption_kw`)
- ⚡ **Délestage** (calculé par MPC — puissance réduite HVAC/éclairage/caisses)

**Équation affichée :**
```
Consommation = PV + Batterie + Grid + P2P - Délestage
```

**Code source :** `src/compliance/checker.py` → fonction `verify_energy_balance()` (Règle R6)

**Exemple sur le dashboard :**
```
Production PV:        60.0 kW ──┐
Batterie (décharge): -12.5 kW ──┤
Grid Import:          15.3 kW ──┼──→ Consommation: 180.0 kW
P2P Import:            5.0 kW ──┤
Délestage HVAC:       -8.0 kW ──┘
                     ─────────
Total:               180.0 kW = 180.0 kW ✓
```

---

#### 4. **Actions Actives (Active Actions)**
**Affiché :** Liste de tags/badges colorés

**Source :** Décisions MPC analysées par le Compliance Service

**Actions possibles :**
- 🔵 **Peak Shaving** : Réduction de la puissance de pointe importée depuis le grid
  - Déclenché quand prix grid > seuil (ex: 0.35 €/kWh)
  - Batterie se décharge pour éviter import coûteux
  
- 🟢 **Valley Filling** : Remplissage de la batterie pendant heures creuses
  - Déclenché quand prix grid < seuil (ex: 0.15 €/kWh)
  - Batterie se charge pour profiter tarifs bas

- 🟡 **Soft Shedding** : Délestage léger (HVAC, éclairage)
  - Réduction setpoint température HVAC de +2°C
  - Dimming éclairage à 80%
  - Pas d'impact perceptible sur confort

- 🔴 **Hard Shedding** : Délestage critique (caisses)
  - Arrêt gracieux caisses non utilisées
  - Uniquement si coverage_ratio < 90%

**Code source :** `src/api/output.py` → fonction `determine_active_actions()`

**Exemple sur le dashboard :**
```
Actions Actives:
 ✓ Peak Shaving
 ✓ HVAC Soft Shed (-8.0 kW)
```

---

#### 5. **Répartition de la Consommation**
**Affiché :** Camembert (Pie Chart) ou barres horizontales

**Catégories (colonnes dataset) :**
- 🔴 **Réfrigération** (Tier 1) : `refrigeration_power_kw` — ~40% consommation (jamais délestée)
- 🔵 **HVAC** (Tier 2) : `hvac_power_kw` — ~25% consommation (délestage prioritaire)
- 🟢 **Éclairage** (Tier 3) : `lighting_power_kw` — ~15% consommation (dimming possible)
- 🟡 **Caisses** (Tier 4) : `checkout_power_kw` — ~10% consommation (arrêt gracieux)
- ⚪ **Autres** : Bureaux, serveurs, etc. — ~10% consommation

**Code source :** Dataset colonnes directes, agrégées par `src/api/output.py`

**Exemple sur le dashboard :**
```
Répartition Consommation (180.0 kW total):
 Réfrigération:  72.0 kW (40%) [TIER 1 - PROTÉGÉ]
 HVAC:          37.0 kW (21%) [Réduit de 8.0 kW]
 Éclairage:     27.0 kW (15%)
 Caisses:       18.0 kW (10%)
 Autres:        26.0 kW (14%)
```

---

#### 6. **Alertes et Anomalies**
**Affiché :** Bannière rouge en haut du dashboard ou panneau latéral

**Détection :** Forecasting Service → Isolation Forest (algorithme ML)

**Source données :** Colonne `anomaly_flag` et `anomaly_source` dans les sorties

**Types d'anomalies détectées :**
1. **Capteur PV corrompu** : Production PV négative ou > capacité installée
2. **Température anormale** : Saut brutal > 5°C en 15 minutes
3. **Consommation aberrante** : Écart > 50% vs prédiction ML
4. **SOC batterie incohérent** : SOC augmente alors que batterie décharge

**Code source :** `src/forecasting/anomaly.py` → classe `IsolationForestDetector`

**Exemple sur le dashboard :**
```
⚠️ ANOMALIE DÉTECTÉE
Source: pv_generation_kw
Valeur mesurée: -5.2 kW (attendu: +60 kW)
Action recommandée: Vérifier capteur PV ou onduleur
```

---

#### 7. **Températures et Confort Thermique**
**Affiché :** Thermomètres visuels avec zones de confort

**Source données :**
- Température extérieure : `outdoor_temp_c`
- Température intérieure : `indoor_temp_c`
- Setpoint HVAC : `hvac_setpoint_c` (valeur cible)

**Zones de confort (Règle R4) :**
- 🔴 **Trop froid** : < 18°C (violation R4)
- 🟡 **Limite basse** : 18-20°C (alerte)
- 🟢 **Confort optimal** : 20-24°C
- 🟡 **Limite haute** : 24-26°C (alerte)
- 🔴 **Trop chaud** : > 26°C (violation R4)

**Code source :** `src/compliance/checker.py` → fonction `check_comfort_bounds()` (Règle R4)

**Exemple sur le dashboard :**
```
Température Intérieure: 22.5°C [CONFORT OPTIMAL]
Température Extérieure: 28.0°C
Setpoint HVAC: 22.0°C (+2°C offset dû soft shedding)
```

---

#### 8. **Historique Temporel (Graphique Time-Series)**
**Affiché :** Graphique linéaire multi-courbes sur 24h ou 7 jours

**Courbes affichées :**
- 📈 Consommation totale (kW)
- 📈 Production PV (kW)
- 📈 SOC batterie (%)
- 📈 Prix grid (€/kWh)
- 📈 Coverage ratio (%)

**Source données :** Base TimescaleDB via endpoint `/api/v1/history?start=...&end=...`

**Code source :** Backend API `src/api/fastapi_app.py` → endpoint `get_history()`

**Exemple sur le dashboard :**
```
Graphique 24h glissant:
- Pic consommation: 220 kW à 14h30 (chaleur maximale)
- Pic production PV: 80 kW à 13h00 (midi solaire)
- SOC batterie: Charge 10h-13h, décharge 16h-20h (peak shaving)
- Prix grid: Pic 0.45 €/kWh à 18h00 (heures de pointe)
```

---

## 🎬 Fonctionnement Lors de l'Exécution d'un Scénario

### Étapes du Pipeline (En Coulisses)

Lorsque l'utilisateur clique sur **"Exécuter Scénario"** dans l'interface, voici ce qui se passe :

#### **1️⃣ Chargement du Dataset**
**Fichier :** `data/dataset.csv` (11,712 lignes, 30 colonnes)

**Code :** `src/ingestion/loader.py` → fonction `load_dataset()`

**Actions :**
- Lecture CSV avec pandas
- Validation colonnes requises (30 colonnes obligatoires)
- Parsing timestamps (format ISO 8601)
- Vérification plage valeurs (ex: SOC entre 0-100%)

**Temps d'exécution :** ~200ms

---

#### **2️⃣ Publication MQTT (Simulation Edge)**
**Code :** `src/ingestion/mqtt_publisher.py` → classe `DatasetMQTTPublisher`

**Actions :**
- Connexion au broker Mosquitto (port 1883)
- Publication ligne par ligne vers topics MQTT :
  - `supermarket/telemetry/energy` → consommation, PV, grid
  - `supermarket/telemetry/battery` → SOC, puissance batterie
  - `supermarket/telemetry/environment` → températures

**Temps d'exécution :** ~1s par ligne (11,712 lignes = ~3 heures en temps réel, mais accéléré en mode simulation)

---

#### **3️⃣ Ingestion Kafka**
**Code :** `src/ingestion/mqtt_subscriber.py` → classe `KafkaForwarder`

**Actions :**
- Subscription aux topics MQTT
- Transformation messages MQTT → JSON structuré
- Publication vers topic Kafka `telemetry.raw` (4 partitions)

**Temps d'exécution :** <50ms par message

---

#### **4️⃣ Forecasting Service (AI/ML)**
**Code :** `services/forecasting/main.py` → classe `MessageProcessor`

**Actions :**
1. **Consommation topic Kafka** `telemetry.raw`
2. **Prédictions ML** (Gradient Boosting) :
   - Consommation future (prochaine heure)
   - Production PV future (prochaine heure)
3. **Détection anomalies** (Isolation Forest) :
   - Score d'anomalie pour chaque feature
   - Flag si score < -0.5 (outlier)
4. **Budgets de flexibilité** :
   - HVAC : Calcul capacité délestage selon écart température
   - Éclairage : 20% dimming possible (puissance × 0.20)
   - Caisses : Arrêt gracieux possible
5. **Publication Kafka** `forecasting.predictions`

**Temps d'exécution :** ~800ms

**Exemple message produit :**
```json
{
  "timestamp": "2025-06-01T00:15:00Z",
  "forecasted_consumption_kw": 185.4,
  "forecasted_pv_kw": 62.1,
  "anomaly_detected": false,
  "flexibility_budgets": {
    "hvac": {"shed_capacity_kw": 15.2, "duration_min": 45},
    "lighting": {"shed_capacity_kw": 8.0, "duration_min": 120},
    "checkout": {"shed_capacity_kw": 5.5, "duration_min": 30}
  }
}
```

---

#### **5️⃣ MPC Service (Optimisation)**
**Code :** `services/mpc/main.py` → classe `MessageProcessor`

**Actions :**
1. **Consommation topic Kafka** `forecasting.predictions`
2. **Formulation problème MPC** :
   - Horizon glissant : 4 timesteps (1 heure)
   - Variables : P_battery, P_shed[HVAC], P_shed[lighting], P_shed[checkout]
   - Fonction objectif : Minimiser (coût énergie + pénalité délestage + pénalité inconfort)
3. **Résolution CVXPY** :
   - Solveur ECOS (convexe)
   - Contraintes : SOC batterie, taux rampe, tiers priorités, confort
4. **Extraction solution** :
   - Commande batterie optimale (kW)
   - Décisions délestage par groupe (kW)
5. **Publication Kafka** `mpc.decisions`

**Temps d'exécution :** ~1.5s (optimisation CVXPY)

**Exemple message produit :**
```json
{
  "timestamp": "2025-06-01T00:15:00Z",
  "battery_command_kw": -12.5,
  "shedding_decisions": {
    "hvac": {"power_kw": 8.0, "action": "soft_shed"},
    "lighting": {"power_kw": 0.0, "action": "none"},
    "checkout": {"power_kw": 0.0, "action": "none"}
  },
  "peak_shaving_active": true
}
```

---

#### **6️⃣ DERMS Service (Dispatch Équipements)**
**Code :** `services/derms/main.py` → classe `MessageProcessor`

**Actions :**
1. **Consommation topic Kafka** `mpc.decisions`
2. **Traduction décisions → commandes physiques** :
   - Batterie : `discharge 12.5 kW pendant 900 sec`
   - HVAC : `setpoint +2°C, réduction puissance 8.0 kW`
   - Éclairage : `dimming à 80%`
   - Caisses : `graceful_shutdown séquence`
3. **Application contraintes physiques** :
   - Taux rampe batterie ≤ 10 kW/15min
   - Température HVAC 18-26°C
   - Dimming éclairage ≥ 50%
4. **Publication Kafka** `derms.dispatch`

**Temps d'exécution :** ~200ms

**Exemple message produit :**
```json
{
  "timestamp": "2025-06-01T00:15:00Z",
  "equipment_commands": [
    {
      "equipment_id": "battery_001",
      "action": "discharge",
      "parameters": {"power_kw": 12.5, "duration_sec": 900}
    },
    {
      "equipment_id": "hvac_main",
      "action": "setpoint_adjust",
      "parameters": {"temp_offset_c": 2.0, "power_reduction_kw": 8.0}
    }
  ]
}
```

---

#### **7️⃣ Compliance Service (Vérification Règles)**
**Code :** `services/compliance/main.py` → classe `MessageProcessor`

**Actions :**
1. **Consommation topics Kafka** `derms.dispatch` + `telemetry.raw`
2. **Vérification règles R1-R6** :
   - R1 : Tier 1 protégé ? (réfrigération jamais délestée)
   - R2 : SOC batterie 10-95% ? (limites respectées)
   - R3 : Taux rampe batterie ≤ 10 kW/15min ? (smooth operation)
   - R4 : Température 18-26°C ? (confort maintenu)
   - R5 : Durée délestage ≤ limites ? (HVAC 45min, éclairage 120min)
   - R6 : Bilan énergétique équilibré ? (identité vérifiée)
3. **Calcul valeur services ancillaires** :
   - Peak shaving : Économie sur demand charge (€)
   - Valley filling : Arbitrage tarifaire (€)
   - Demand response : Rémunération programmes DR (€)
4. **Génération rapport** :
   - Status : COMPLIANT / WARNING / VIOLATION
   - Liste violations éventuelles
   - Valeur économique créée (€)
5. **Publication Kafka** `compliance.reports`

**Temps d'exécution :** ~150ms

**Exemple message produit :**
```json
{
  "timestamp": "2025-06-01T00:15:00Z",
  "compliance_status": "COMPLIANT",
  "violations": [],
  "tier_1_protected": true,
  "ancillary_services_value_eur": {
    "peak_shaving": 2.45,
    "valley_filling": 1.20,
    "demand_response": 0.00
  }
}
```

---

#### **8️⃣ Persistance et Cache**
**Code :** `src/persistence/timescale.py` + `src/persistence/redis_cache.py`

**Actions :**
1. **Backend API écoute** topic Kafka `compliance.reports`
2. **Écriture TimescaleDB** :
   - INSERT dans hypertable `pipeline_outputs`
   - Partitionnement automatique par timestamp
3. **Mise à jour cache Redis** :
   - Key `latest:supermarket_001` → JSON état le plus récent
   - TTL 1 heure
4. **Diffusion WebSocket** :
   - Broadcast événement vers clients connectés `/ws/stream`
   - Dashboard reçoit mise à jour temps-réel

**Temps d'exécution :** ~50ms (écriture DB + cache + WebSocket)

---

#### **9️⃣ Affichage Dashboard (Mise à Jour Interface)**
**Code :** Frontend JavaScript (dashboard séparé, consomme API Backend)

**Actions :**
1. **Réception message WebSocket** depuis `/ws/stream`
2. **Parsing JSON** et extraction métriques
3. **Mise à jour composants UI** :
   - Jauge Coverage Ratio → animation transition
   - Graphique SOC batterie → ajout nouveau point
   - Liste Actions Actives → ajout/retrait badges
   - Graphique Time-Series → ajout point courbes
4. **Déclenchement alertes visuelles** si anomalie ou violation

**Temps d'exécution :** ~100ms (rendering frontend)

---

### 📊 Temps Total Pipeline (End-to-End)

```
Ingestion MQTT → Kafka:           50ms
Forecasting (AI/ML):             800ms
MPC (Optimisation):            1,500ms
DERMS (Dispatch):                200ms
Compliance (Vérification):       150ms
Persistance (DB + Cache):         50ms
WebSocket → Dashboard:           100ms
─────────────────────────────────────
TOTAL:                        ~2.85s
```

**Latence perçue utilisateur :** ~3 secondes entre événement capteur et affichage dashboard

---

## 🎭 Scénarios de Démonstration

### Scénario 1 : Mode Normal (Fonctionnement Nominal)
**Fichier :** `data/dataset.csv` avec scénario `none`

**Caractéristiques :**
- Prix grid stable (~0.25 €/kWh)
- Production PV régulière (courbe solaire typique)
- Grid toujours disponible
- Pas d'anomalies capteurs

**Dashboard attendu :**
- Coverage Ratio : 98-100% (🟢 NORMAL)
- Actions Actives : Valley Filling (charge batterie heures creuses)
- SOC batterie : Cycle charge 10h-14h, décharge 17h-21h
- Pas d'alertes

---

### Scénario 2 : Price Spike (Pic Tarifaire)
**Fichier :** `data/dataset.csv` avec scénario `price_spike`

**Caractéristiques :**
- Prix grid monte à 0.80 €/kWh pendant 18h-20h (×3 tarif normal)
- Système doit minimiser import grid coûteux

**Dashboard attendu :**
- Coverage Ratio : 92-95% (🟡 AT_RISK)
- Actions Actives : 
  - ✓ Peak Shaving (batterie décharge à fond)
  - ✓ HVAC Soft Shed (-10 kW)
  - ✓ Lighting Dim (-5 kW)
- SOC batterie : Chute rapide 80% → 20%
- Graphique : Pic grid power réduit de 40% vs baseline

**Valeur créée :**
```
Économie peak shaving = (P_peak_baseline - P_peak_actual) × tarif_demand_charge
                      = (50 kW - 20 kW) × 15 €/kW/mois
                      = 450 €/mois économisés
```

---

### Scénario 3 : Sensor Corruption (Capteur Défaillant)
**Fichier :** `data/dataset.csv` avec scénario `sensor_corruption`

**Caractéristiques :**
- Capteur PV retourne valeurs négatives (ex: -50 kW au lieu de +60 kW)
- Forecasting Service détecte anomalie via Isolation Forest

**Dashboard attendu :**
- 🔴 **ALERTE ANOMALIE** :
  ```
  ⚠️ Anomalie détectée sur pv_generation_kw
  Valeur mesurée: -50.2 kW (physiquement impossible)
  Isolation Forest score: -0.87 (outlier)
  Action recommandée: Vérifier onduleur PV ou câblage
  ```
- Coverage Ratio : Chute temporaire car PV non comptabilisé
- Actions Actives : Hard Shedding si nécessaire (compensation perte PV)

**Code détection :**
```python
# src/forecasting/anomaly.py
if pv_generation_kw < 0:
    anomaly_flag = True
    anomaly_source = "pv_generation_kw"
    anomaly_score = isolation_forest.decision_function([features])
```

---

### Scénario 4 : Forced Grid Outage (Panne Grid)
**Fichier :** `data/dataset.csv` avec scénario `forced_grid_outage`

**Caractéristiques :**
- Grid indisponible pendant 2 heures (14h-16h)
- Système passe en mode autonome (PV + Batterie uniquement)

**Dashboard attendu :**
- Coverage Ratio : Chute à 85% (🔴 CRITICAL)
- Actions Actives :
  - ✓ Hard Shedding HVAC (-15 kW)
  - ✓ Lighting Dim 50% (-10 kW)
  - ✓ Checkout Shutdown (-8 kW)
- SOC batterie : Décharge maximale pour compenser
- ⚠️ **ALERTE CRITIQUE** :
  ```
  🔴 Grid Outage Détecté
  Mode autonome activé (PV + Batterie)
  Durée estimée autonomie: 47 minutes (SOC actuel 35%)
  Tier 1 (Réfrigération) maintenu : ✓
  ```

**Protection Tier 1 :**
```python
# src/compliance/checker.py (Règle R1)
if coverage_ratio < 0.90:
    # Prioriser réfrigération AVANT tout autre charge
    shed_checkout_first()
    if still_insufficient:
        shed_lighting()
    if still_insufficient:
        shed_hvac()
    # Réfrigération JAMAIS délestée, même coverage_ratio < 50%
```

---

## 📈 Métriques Économiques Affichées

### Coût Énergétique Total (Daily/Monthly)
**Calcul :**
```
Coût Total = Σ (P_grid[t] × prix_grid[t] × Δt) 
           + demand_charge × P_peak_mois
           - valeur_services_ancillaires
```

**Exemple dashboard :**
```
💰 Coût Énergétique Journalier:
   Import grid:           245.60 € (1,200 kWh × 0.20 €/kWh moyen)
   Demand charge:          75.00 € (50 kW peak × 1.50 €/kW/jour)
   Services ancillaires:  -12.50 € (peak shaving, valley filling)
   ─────────────────────────────────
   TOTAL:                 308.10 €
   
   vs Baseline (sans optimisation): 425.00 €
   💡 Économie: 116.90 € (27.5%)
```

---

### Autosuffisance Énergétique
**Calcul :**
```
Taux Autosuffisance = (PV + Batterie) / Consommation Totale × 100%
```

**Exemple dashboard :**
```
🌞 Autosuffisance: 68.4%
   Production PV:      450 kWh/jour
   Batterie fournie:   120 kWh/jour
   Consommation:       834 kWh/jour
   ─────────────────────────────────
   Import grid requis: 264 kWh/jour (31.6%)
```

---

### Émissions CO₂ Évitées
**Calcul :**
```
CO₂ évité = (P_grid_baseline - P_grid_actual) × intensité_CO2_grid
```

**Exemple dashboard :**
```
🌱 Impact Environnemental:
   Intensité CO₂ grid: 380 g/kWh
   Import évité: 150 kWh/jour (vs baseline)
   ─────────────────────────────────
   CO₂ évité: 57.0 kg/jour
   Équivalent: 285 km voiture thermique
```

---

## 🔍 Debugging et Diagnostic

### Mode Debug (Logs Détaillés)
Pour voir les calculs en détail lors d'une présentation :

**Activer logs Kafka :**
```bash
# Terminal 1 : Voir messages telemetry.raw
docker exec b2g-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic telemetry.raw --from-beginning

# Terminal 2 : Voir décisions MPC
docker exec b2g-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic mpc.decisions --from-beginning
```

**Activer logs services :**
```bash
docker compose logs forecasting -f  # Prédictions ML en temps réel
docker compose logs mpc -f          # Résolution optimisation
docker compose logs derms -f        # Commandes équipements
```

---

### Vérification Bilan Énergétique
Pour expliquer d'où viennent les chiffres :

```bash
# Interroger TimescaleDB directement
docker exec -it b2g-timescaledb psql -U postgres -d b2g_db

# Requête SQL
SELECT timestamp, coverage_ratio, battery_soc, grid_power, active_actions
FROM pipeline_outputs
WHERE timestamp >= NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;
```

---

## 📚 Points Clés pour la Présentation

### Message Principal
> "La plateforme B2G optimise automatiquement l'énergie du supermarché en combinant intelligence artificielle, optimisation mathématique et architecture événementielle distribuée. Elle garantit la fiabilité électrique (Tier 1 jamais interrompu) tout en réduisant les coûts de 25-30% via peak shaving et exploitation de la flexibilité."

### Chiffres Clés à Retenir
- ⚡ **Latence pipeline** : ~3 secondes (MQTT → Dashboard)
- 💰 **Économie coûts** : 25-30% vs baseline sans optimisation
- 🔋 **Efficacité batterie** : 90% round-trip efficiency (charge/décharge)
- 🌞 **Autosuffisance** : 60-70% selon production PV
- 🏗️ **Architecture** : 9 services microservices, 5 topics Kafka
- 🚀 **Scalabilité** : 4x parallélisation possible (4 partitions `telemetry.raw`)

### Démo Recommandée (5 minutes)
1. **[0:00-1:00]** Montrer dashboard mode normal → tout est vert, système stable
2. **[1:00-2:00]** Déclencher scénario price_spike → montrer peak shaving en action
3. **[2:00-3:00]** Zoomer sur graphique bilan énergétique → expliquer équation
4. **[3:00-4:00]** Afficher logs Kafka en temps réel → montrer messages JSON
5. **[4:00-5:00]** Déclencher anomalie capteur → montrer détection Isolation Forest

---

## 🎓 Questions Fréquentes Présentation

**Q1 : D'où viennent les prédictions de consommation ?**
> R : Le Forecasting Service utilise un modèle Gradient Boosting entraîné sur 4 mois de données historiques (11,712 timesteps). Il prend en compte température extérieure, heure du jour, jour de semaine, saison. Précision : MAE ~5 kW (erreur moyenne 3% de la consommation totale).

**Q2 : Comment le système décide quoi délester en priorité ?**
> R : Le MPC Service suit une hiérarchie stricte (Tiers) :
> - Tier 1 (Réfrigération) : JAMAIS délestée (Règle R1)
> - Tier 2 (HVAC) : Délestage prioritaire (+2°C setpoint max)
> - Tier 3 (Éclairage) : Dimming jusqu'à 50%
> - Tier 4 (Caisses) : Arrêt gracieux en dernier recours

**Q3 : Que se passe-t-il si la batterie est vide ET le grid est en panne ?**
> R : Scénario worst-case, couverture électrique < 50%. Système active shedding maximal :
> 1. Arrêt HVAC complet (inertie thermique 1-2h)
> 2. Éclairage minimal (10% zones critiques)
> 3. Arrêt toutes caisses
> 4. **Réfrigération maintenue** (Tier 1 protégé) même si cela signifie SOC batterie → 0%
> 
> Durée autonomie réfrigération seule : ~2 heures avec SOC 50%

**Q4 : Les chiffres dashboard sont-ils simulés ou réels ?**
> R : **Simulés** pour cette démonstration. Le dataset `data/dataset.csv` contient des données synthétiques générées pour reproduire des comportements réalistes (courbe solaire, profils consommation, variabilité météo). En production, les mêmes algorithmes seraient connectés à de vrais capteurs MQTT/Modbus et produiraient des décisions réelles envoyées aux équipements physiques (batteries, HVAC, éclairage).

**Q5 : Quelle est la valeur économique créée par la plateforme ?**
> R : Sur 1 mois (été, avec PV optimal) :
> - **Économie import grid** : ~150 €/mois (réduction 20% consommation pointe)
> - **Économie demand charge** : ~450 €/mois (réduction peak 30 kW)
> - **Rémunération services ancillaires** : ~80 €/mois (demand response)
> - **ROI projet** : Économie totale ~680 €/mois → ROI batterie (50k€) en ~6 ans

---

**Document version :** 1.0  
**Dernière mise à jour :** Octobre 2026  
**Auteurs :** Équipe Smart Supermarket B2G
