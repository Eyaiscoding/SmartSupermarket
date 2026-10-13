# Guide de Test End-to-End - Plateforme Smart Supermarket B2G

## Vue d'ensemble

Ce guide explique comment tester la plateforme B2G complète après achèvement des Phases 1-5 et 7 (Phase 6 Observability omise). Il détaille chaque étape du pipeline événementiel et montre comment vérifier que tout fonctionne correctement.

---

## 🏗️ Architecture Testée

```
MQTT Edge Sensors
       ↓
telemetry.raw (Kafka)
       ↓
Forecasting Service (AI/ML)
       ↓
forecasting.predictions (Kafka)
       ↓
MPC Service (Optimisation CVXPY)
       ↓
mpc.decisions (Kafka)
       ↓
DERMS Service (Dispatch équipements)
       ↓
derms.dispatch (Kafka)
       ↓
Compliance Service (Règles R1-R6)
       ↓
compliance.reports (Kafka) → TimescaleDB
```

---

## 📋 Pré-requis

1. **Docker Desktop** démarré et fonctionnel
2. **PowerShell** ou terminal avec accès Docker
3. **Ports disponibles**: 8000 (API), 9092-9093 (Kafka), 1883 (MQTT), 5432 (TimescaleDB), 6379 (Redis), 2181 (Zookeeper)

---

## 🚀 Étape 1: Démarrage de la Plateforme

```powershell
cd "c:\Users\user\Desktop\Digital\Smart building\SmartSupermarket"

# Démarrer tous les services
docker compose up -d

# Vérifier que tous les services sont démarrés (attendre 1-2 minutes)
docker compose ps
```

**Résultat attendu:**
```
NAME              STATUS
b2g-backend       Up (healthy)
b2g-forecasting   Up
b2g-mpc           Up
b2g-derms         Up
b2g-compliance    Up
b2g-kafka         Up (healthy)
b2g-zookeeper     Up (healthy)
b2g-timescaledb   Up (healthy)
b2g-redis         Up (healthy)
b2g-mosquitto     Up (healthy)
```

**Si un service est en erreur:**
```powershell
# Voir les logs du service problématique
docker compose logs [nom_service] --tail 50

# Exemples:
docker compose logs forecasting --tail 50
docker compose logs mpc --tail 50
```

---

## 🧪 Étape 2: Vérification de l'Infrastructure Kafka

### 2.1 Vérifier que les topics Kafka existent

```powershell
docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --list
```

**Résultat attendu:**
```
telemetry.raw
forecasting.predictions
mpc.decisions
derms.dispatch
compliance.reports
```

### 2.2 Vérifier les consumer groups

```powershell
docker exec b2g-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --list
```

**Résultat attendu:**
```
forecasting-service
mpc-service
derms-service
compliance-service-dispatch
compliance-service-telemetry
```

---

## 📡 Étape 3: Test du Pipeline Complet

### 3.1 Envoyer un événement de test

Créer un fichier `test_telemetry.json`:
```json
{"timestamp": "2026-10-13T15:00:00Z", "building_id": "supermarket_001", "energy_consumption_kw": 185.0, "pv_generation_kw": 65.0, "battery_soc_percent": 58.0, "grid_price_eur_per_kwh": 0.38, "outdoor_temp_c": 26.0, "indoor_temp_c": 23.0, "hvac_power_kw": 42.0, "lighting_power_kw": 28.0, "refrigeration_power_kw": 75.0, "checkout_power_kw": 20.0}
```

Envoyer au topic `telemetry.raw`:
```powershell
Get-Content test_telemetry.json | docker exec -i b2g-kafka kafka-console-producer --bootstrap-server localhost:9092 --topic telemetry.raw
```

### 3.2 Suivre l'événement à travers le pipeline

Ouvrir **4 terminaux PowerShell** séparés et exécuter:

**Terminal 1 - Forecasting Service:**
```powershell
docker compose logs forecasting -f
```

**Terminal 2 - MPC Service:**
```powershell
docker compose logs mpc -f
```

**Terminal 3 - DERMS Service:**
```powershell
docker compose logs derms -f
```

**Terminal 4 - Compliance Service:**
```powershell
docker compose logs compliance -f
```

**Que voir dans les logs:**

**Forecasting (Terminal 1):**
```
INFO - Processing telemetry event for 2026-10-13T15:00:00Z
INFO - Forecasting complete: consumption=187.2 kW, pv=63.5 kW
INFO - Published to forecasting.predictions
```

**MPC (Terminal 2):**
```
INFO - Processing forecasting predictions for 2026-10-13T15:00:00Z
INFO - MPC optimization complete: battery=-8.5 kW, hvac_shed=5.0 kW
INFO - Published to mpc.decisions
```

**DERMS (Terminal 3):**
```
INFO - Processing MPC decision for 2026-10-13T15:00:00Z
INFO - DERMS dispatch: 3 commands, battery=-8.5 kW, grid=95.0 kW
INFO - Published to derms.dispatch
```

**Compliance (Terminal 4):**
```
INFO - Checking compliance for 2026-10-13T15:00:00Z
INFO - Compliance check: GREEN, tier_1_protected=true
INFO - Published to compliance.reports
```

---

## 🔍 Étape 4: Vérification des Topics Kafka

### 4.1 Lire le dernier message de chaque topic

**Topic: telemetry.raw**
```powershell
docker exec b2g-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic telemetry.raw --from-beginning --max-messages 1
```

**Topic: forecasting.predictions**
```powershell
docker exec b2g-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic forecasting.predictions --from-beginning --max-messages 1
```

**Topic: mpc.decisions**
```powershell
docker exec b2g-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic mpc.decisions --from-beginning --max-messages 1
```

**Topic: derms.dispatch**
```powershell
docker exec b2g-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic derms.dispatch --from-beginning --max-messages 1
```

**Topic: compliance.reports**
```powershell
docker exec b2g-kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic compliance.reports --from-beginning --max-messages 1
```

**Chaque commande doit afficher un message JSON correspondant à l'événement envoyé.**

---

## 🗄️ Étape 5: Vérification de la Persistance TimescaleDB

### 5.1 Connexion à TimescaleDB

```powershell
docker exec -it b2g-timescaledb psql -U b2g -d b2g
```

### 5.2 Vérifier les tables

```sql
\dt
```

**Résultat attendu:**
```
         List of relations
 Schema |       Name        | Type  | Owner 
--------+-------------------+-------+-------
 public | pipeline_outputs  | table | b2g
```

### 5.3 Compter les enregistrements

```sql
SELECT COUNT(*) FROM pipeline_outputs;
```

### 5.4 Voir les derniers enregistrements

```sql
SELECT timestamp, coverage_ratio, coverage_status, tier_1_protected, battery_soc
FROM pipeline_outputs
ORDER BY timestamp DESC
LIMIT 5;
```

### 5.5 Quitter psql

```sql
\q
```

---

## 🔴 Étape 6: Vérification de Redis (Cache)

### 6.1 Connexion à Redis

```powershell
docker exec -it b2g-redis redis-cli
```

### 6.2 Lire la clé latest

```
GET latest:supermarket_001
```

**Résultat attendu:** JSON du dernier état du pipeline

### 6.3 Quitter Redis

```
EXIT
```

---

## 🌐 Étape 7: Test de l'API Backend

### 7.1 Health Check

```powershell
curl http://localhost:8000/health
```

**Résultat attendu:**
```json
{
  "status": "healthy",
  "kafka": "connected",
  "timescaledb": "connected",
  "redis": "connected"
}
```

### 7.2 Obtenir l'état le plus récent

```powershell
curl http://localhost:8000/api/v1/latest
```

**Résultat attendu:** JSON avec l'état actuel du pipeline

### 7.3 Obtenir l'historique

```powershell
curl "http://localhost:8000/api/v1/history?start=2026-10-13T14:00:00Z&end=2026-10-13T16:00:00Z"
```

**Résultat attendu:** Array JSON avec historique de la période spécifiée

### 7.4 Ouvrir la documentation API interactive

Ouvrir dans le navigateur: `http://localhost:8000/docs`

---

## 🧪 Étape 8: Tests de Scénarios Spécifiques

### 8.1 Scénario Price Spike (Pic Tarifaire)

Envoyer un événement avec prix grid élevé:
```json
{"timestamp": "2026-10-13T18:00:00Z", "building_id": "supermarket_001", "energy_consumption_kw": 190.0, "pv_generation_kw": 20.0, "battery_soc_percent": 80.0, "grid_price_eur_per_kwh": 0.85, "outdoor_temp_c": 29.0, "indoor_temp_c": 24.5, "hvac_power_kw": 50.0, "lighting_power_kw": 30.0, "refrigeration_power_kw": 75.0, "checkout_power_kw": 20.0}
```

**Résultat attendu dans logs MPC:**
```
INFO - Peak shaving activated (grid_price=0.85 €/kWh)
INFO - Battery discharge: -30.0 kW
INFO - HVAC soft shed: 10.0 kW
```

### 8.2 Scénario Grid Outage (Panne Grid)

Envoyer un événement avec prix grid très élevé simulant indisponibilité:
```json
{"timestamp": "2026-10-13T19:00:00Z", "building_id": "supermarket_001", "energy_consumption_kw": 180.0, "pv_generation_kw": 50.0, "battery_soc_percent": 45.0, "grid_price_eur_per_kwh": 1.50, "outdoor_temp_c": 27.0, "indoor_temp_c": 25.0, "hvac_power_kw": 45.0, "lighting_power_kw": 28.0, "refrigeration_power_kw": 72.0, "checkout_power_kw": 18.0}
```

**Résultat attendu dans logs Compliance:**
```
INFO - Coverage ratio: 0.88 (AT_RISK)
INFO - Hard shedding activated
INFO - Tier 1 protected: true (Réfrigération maintenue)
```

### 8.3 Scénario Valley Filling (Heures Creuses)

Envoyer un événement avec prix grid bas:
```json
{"timestamp": "2026-10-13T03:00:00Z", "building_id": "supermarket_001", "energy_consumption_kw": 120.0, "pv_generation_kw": 0.0, "battery_soc_percent": 25.0, "grid_price_eur_per_kwh": 0.12, "outdoor_temp_c": 18.0, "indoor_temp_c": 21.0, "hvac_power_kw": 30.0, "lighting_power_kw": 15.0, "refrigeration_power_kw": 60.0, "checkout_power_kw": 5.0}
```

**Résultat attendu dans logs MPC:**
```
INFO - Valley filling activated (grid_price=0.12 €/kWh)
INFO - Battery charge: +40.0 kW
```

---

## 📊 Étape 9: Métriques et Performance

### 9.1 Vérifier le lag Kafka (retard consommation)

```powershell
docker exec b2g-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group forecasting-service
docker exec b2g-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group mpc-service
docker exec b2g-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group derms-service
docker exec b2g-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group compliance-service-dispatch
```

**Résultat attendu:** LAG = 0 (tous les messages traités)

### 9.2 Mesurer la latence end-to-end

1. Noter le timestamp de l'événement envoyé: `T_send`
2. Vérifier le timestamp du dernier rapport compliance: `T_compliance`
3. Latence = `T_compliance - T_send`

**Latence cible:** < 5 secondes

---

## 🚨 Étape 10: Tests de Résilience

### 10.1 Test de redémarrage d'un service

```powershell
# Arrêter MPC Service
docker compose stop mpc

# Envoyer un événement (devrait être bufferisé par Kafka)
Get-Content test_telemetry.json | docker exec -i b2g-kafka kafka-console-producer --bootstrap-server localhost:9092 --topic telemetry.raw

# Attendre 10 secondes

# Redémarrer MPC Service
docker compose start mpc

# Vérifier logs - l'événement devrait être traité
docker compose logs mpc --tail 20
```

### 10.2 Test de panne Kafka temporaire

```powershell
# Arrêter Kafka
docker compose stop kafka

# Les services doivent logger des erreurs de connexion mais ne pas crasher

# Attendre 10 secondes

# Redémarrer Kafka
docker compose start kafka

# Vérifier que tous les services se reconnectent automatiquement
docker compose logs forecasting --tail 10
docker compose logs mpc --tail 10
```

---

## 🛠️ Étape 11: Dépannage

### 11.1 Service ne démarre pas

```powershell
# Voir logs détaillés
docker compose logs [service_name] --tail 100

# Reconstruire l'image
docker compose build [service_name]

# Redémarrer
docker compose up -d [service_name]
```

### 11.2 Messages non traités (Kafka lag élevé)

```powershell
# Vérifier le lag
docker exec b2g-kafka kafka-consumer-groups --bootstrap-server localhost:9092 --describe --all-groups

# Redémarrer le service consommateur lent
docker compose restart [service_name]
```

### 11.3 Erreurs JSON parsing

Si les services loguent des erreurs `JSONDecodeError`:
- Vérifier le format du message dans le topic
- Nettoyer les topics et réessayer:

```powershell
# Arrêter tous les services
docker compose down

# Supprimer les volumes Kafka (ATTENTION: perte de données)
docker volume rm smartsupermarket_kafka_data

# Redémarrer
docker compose up -d
```

---

## 📈 Étape 12: Métriques Succès

**Pipeline fonctionnel si:**
- ✅ Tous les services `Up` et `healthy`
- ✅ Kafka lag = 0 pour tous les consumer groups
- ✅ Latence end-to-end < 5 secondes
- ✅ Messages présents dans les 5 topics Kafka
- ✅ Données persistées dans TimescaleDB
- ✅ Cache Redis à jour avec dernier état
- ✅ API Backend répond en < 100ms
- ✅ Compliance reports status = GREEN/YELLOW (pas RED)
- ✅ Tier 1 (Réfrigération) toujours protégé = `true`

---

## 🎯 Checklist de Test Final

- [ ] Infrastructure démarrée (10 containers)
- [ ] Topics Kafka créés (5 topics)
- [ ] Consumer groups actifs (5 groups)
- [ ] Événement test envoyé
- [ ] Logs des 4 services affichent traitement
- [ ] Messages dans tous les topics Kafka
- [ ] Données dans TimescaleDB
- [ ] Cache Redis à jour
- [ ] API `/health` retourne healthy
- [ ] API `/api/v1/latest` retourne données
- [ ] Latence < 5 secondes
- [ ] Kafka lag = 0
- [ ] Test price spike OK
- [ ] Test valley filling OK
- [ ] Test redémarrage service OK
- [ ] Compliance status GREEN
- [ ] Tier 1 protected = true

---

## 📚 Ressources

- **Logs en temps réel:** `docker compose logs -f [service]`
- **Status services:** `docker compose ps`
- **API Documentation:** http://localhost:8000/docs
- **Kafka Topics:** `/topic` dans chaque commande kafka-console-*
- **TimescaleDB:** `docker exec -it b2g-timescaledb psql -U b2g -d b2g`
- **Redis:** `docker exec -it b2g-redis redis-cli`

---

**Version:** 1.0  
**Dernière mise à jour:** Octobre 2026
