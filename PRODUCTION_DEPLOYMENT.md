# Guide de Déploiement Production - Smart Supermarket B2G

## 📋 Vue d'ensemble

Ce guide couvre le déploiement production de la plateforme B2G avec ses 5 microservices, infrastructure Kafka, et bases de données.

---

## ✅ Checklist Pré-déploiement

### Infrastructure

- [ ] **Serveur(s)** avec Docker et Docker Compose installés
- [ ] **CPU**: Minimum 4 cores (recommandé 8+ cores pour production)
- [ ] **RAM**: Minimum 8 GB (recommandé 16+ GB pour production)
- [ ] **Stockage**: Minimum 50 GB SSD (recommandé 200+ GB pour données historiques)
- [ ] **Réseau**: Ports disponibles (8000, 9092-9093, 1883, 5432, 6379, 2181)
- [ ] **Accès root/sudo** pour gestion Docker

### Configuration

- [ ] Fichier `.env` créé depuis `.env.example`
- [ ] Mots de passe changés (TimescaleDB, Redis si activé)
- [ ] `ENVIRONMENT=production` défini
- [ ] `DEBUG=false` défini
- [ ] Logs configurés en format JSON (`LOG_FORMAT=json`)
- [ ] CORS origins configurés pour domaines production

### Sécurité

- [ ] Firewall configuré (autoriser uniquement ports nécessaires)
- [ ] SSL/TLS certificats obtenus (recommandé pour API externe)
- [ ] Secrets management configuré (ne pas hardcoder passwords)
- [ ] Backups automatiques configurés (TimescaleDB)
- [ ] Monitoring configuré (logs, métriques)

---

## 🚀 Procédure de Déploiement

### Étape 1: Préparation du Serveur

```bash
# Se connecter au serveur
ssh user@production-server

# Créer répertoire de déploiement
mkdir -p /opt/smart-supermarket-b2g
cd /opt/smart-supermarket-b2g

# Cloner le repository
git clone https://github.com/Eyaiscoding/SmartSupermarket.git .

# Créer fichier .env depuis template
cp .env.example .env
nano .env  # Éditer avec valeurs production
```

### Étape 2: Configuration Production

Éditer `.env` et définir:

```bash
# Environnement
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
LOG_FORMAT=json

# Sécurité
TIMESCALE_PASSWORD=<mot_de_passe_fort>
REDIS_PASSWORD=<mot_de_passe_redis>

# Performance
API_WORKERS=8
MPC_HORIZON_HOURS=48

# Kafka retention (plus long en production)
KAFKA_RETENTION_MS_TELEMETRY=2592000000  # 30 jours
KAFKA_RETENTION_MS_COMPLIANCE=63072000000  # 2 ans
```

### Étape 3: Build des Images Docker

```bash
# Build toutes les images
docker compose build --no-cache

# Vérifier les images créées
docker images | grep smartsupermarket
```

**Images attendues:**
- `smartsupermarket-backend`
- `smartsupermarket-forecasting`
- `smartsupermarket-mpc`
- `smartsupermarket-derms`
- `smartsupermarket-compliance`

### Étape 4: Initialisation Infrastructure

```bash
# Démarrer infrastructure d'abord (bases de données, Kafka)
docker compose up -d zookeeper kafka timescaledb redis mosquitto

# Attendre que tout soit healthy (2-3 minutes)
docker compose ps

# Vérifier health checks
docker compose ps | grep healthy
```

### Étape 5: Création des Topics Kafka

```bash
# Créer topics avec rétention production
docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --create \
  --topic telemetry.raw --partitions 4 --replication-factor 1 \
  --config retention.ms=2592000000

docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --create \
  --topic forecasting.predictions --partitions 2 --replication-factor 1 \
  --config retention.ms=86400000

docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --create \
  --topic mpc.decisions --partitions 1 --replication-factor 1 \
  --config retention.ms=2592000000

docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --create \
  --topic derms.dispatch --partitions 2 --replication-factor 1 \
  --config retention.ms=2592000000

docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --create \
  --topic compliance.reports --partitions 1 --replication-factor 1 \
  --config retention.ms=63072000000

# Vérifier
docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 --list
```

### Étape 6: Initialisation TimescaleDB

```bash
# Connexion à la base
docker exec -it b2g-timescaledb psql -U b2g -d b2g

# Créer hypertable (si migration pas auto)
CREATE TABLE IF NOT EXISTS pipeline_outputs (
    timestamp TIMESTAMPTZ NOT NULL,
    building_id TEXT,
    coverage_ratio FLOAT,
    coverage_status TEXT,
    active_actions TEXT[],
    tier_1_protected BOOLEAN,
    battery_soc FLOAT,
    grid_power FLOAT,
    p2p_energy FLOAT,
    anomaly_flag BOOLEAN,
    anomaly_source TEXT
);

SELECT create_hypertable('pipeline_outputs', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_building_timestamp 
ON pipeline_outputs (building_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_coverage_status 
ON pipeline_outputs (coverage_status);

# Activer compression (après 7 jours)
ALTER TABLE pipeline_outputs SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'building_id'
);

SELECT add_compression_policy('pipeline_outputs', INTERVAL '7 days', if_not_exists => TRUE);

# Rétention 1 an (ajuster selon besoins)
SELECT add_retention_policy('pipeline_outputs', INTERVAL '1 year', if_not_exists => TRUE);

\q
```

### Étape 7: Démarrage des Microservices

```bash
# Démarrer backend API
docker compose up -d backend

# Attendre healthy
docker compose ps backend

# Démarrer microservices dans l'ordre
docker compose up -d forecasting
docker compose up -d mpc
docker compose up -d derms
docker compose up -d compliance

# Vérifier que tout est UP
docker compose ps
```

### Étape 8: Vérification Post-déploiement

```bash
# Health check API
curl http://localhost:8000/health

# Vérifier consumer groups Kafka
docker exec b2g-kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 --list

# Vérifier logs (pas d'erreurs)
docker compose logs --tail 50 forecasting
docker compose logs --tail 50 mpc
docker compose logs --tail 50 derms
docker compose logs --tail 50 compliance

# Envoyer événement de test
echo '{"timestamp": "2026-10-13T20:00:00Z", "building_id": "supermarket_001", "energy_consumption_kw": 180.0, "pv_generation_kw": 60.0, "battery_soc_percent": 55.0, "grid_price_eur_per_kwh": 0.28, "outdoor_temp_c": 22.0}' | \
  docker exec -i b2g-kafka kafka-console-producer \
  --bootstrap-server localhost:9092 --topic telemetry.raw

# Vérifier traitement dans compliance.reports (attendre 5 sec)
docker exec b2g-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic compliance.reports \
  --from-beginning --max-messages 1 --timeout-ms 10000
```

---

## 🔄 Procédure de Mise à Jour

### Rolling Update (Sans Downtime)

```bash
# 1. Pull dernière version
git pull origin main

# 2. Build nouvelle image (exemple: forecasting)
docker compose build forecasting

# 3. Recréer container (Docker Compose gère graceful shutdown)
docker compose up -d forecasting

# 4. Vérifier logs
docker compose logs forecasting --tail 50

# 5. Répéter pour autres services
docker compose build mpc && docker compose up -d mpc
docker compose build derms && docker compose up -d derms
docker compose build compliance && docker compose up -d compliance
docker compose build backend && docker compose up -d backend
```

### Full Stack Update (Avec Downtime Court)

```bash
# 1. Pull dernière version
git pull origin main

# 2. Arrêter tous les services
docker compose down

# 3. Build toutes les images
docker compose build --no-cache

# 4. Redémarrer
docker compose up -d

# 5. Vérifier
docker compose ps
docker compose logs --tail 100
```

---

## 📊 Monitoring et Logs

### Accès aux Logs

```bash
# Logs temps réel tous services
docker compose logs -f

# Logs service spécifique
docker compose logs -f forecasting

# Logs avec timestamps
docker compose logs -f --timestamps forecasting

# Dernières 100 lignes
docker compose logs --tail 100 mpc

# Logs depuis un timestamp
docker compose logs --since 2026-10-13T15:00:00Z compliance
```

### Logs Structurés (JSON)

Avec `LOG_FORMAT=json`, chaque log est un objet JSON:

```json
{
  "timestamp": "2026-10-13T20:15:42.123Z",
  "level": "INFO",
  "service": "forecasting",
  "correlation_id": "abc123",
  "message": "Processing telemetry event",
  "data": {
    "timestamp": "2026-10-13T20:15:00Z",
    "consumption_kw": 185.0
  }
}
```

Parser avec `jq`:
```bash
docker compose logs forecasting --tail 100 | jq -r 'select(.level == "ERROR")'
```

### Métriques Kafka

```bash
# Lag consumer groups (retard traitement)
docker exec b2g-kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --all-groups

# Nombre de messages par topic
docker exec b2g-kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic telemetry.raw --time -1
```

### Métriques TimescaleDB

```sql
-- Connexion
docker exec -it b2g-timescaledb psql -U b2g -d b2g

-- Taille base de données
SELECT pg_size_pretty(pg_database_size('b2g'));

-- Nombre d'enregistrements
SELECT COUNT(*) FROM pipeline_outputs;

-- Taille hypertable
SELECT hypertable_size('pipeline_outputs');

-- Stats compression
SELECT * FROM timescaledb_information.compression_settings 
WHERE hypertable_name = 'pipeline_outputs';

-- Taux compression
SELECT 
  pg_size_pretty(before_compression_total_bytes) AS "avant compression",
  pg_size_pretty(after_compression_total_bytes) AS "après compression",
  ROUND(100 * (1 - after_compression_total_bytes::numeric / 
         before_compression_total_bytes::numeric), 2) AS "taux %"
FROM timescaledb_information.compressed_chunk_stats;
```

---

## 🔥 Procédures d'Urgence

### Service Crashe en Boucle

```bash
# Voir logs erreur
docker compose logs [service] --tail 200

# Vérifier ressources système
docker stats

# Redémarrer avec rebuild
docker compose stop [service]
docker compose build [service]
docker compose up -d [service]

# Si problème persiste, rollback version précédente
git log --oneline -5
git checkout [commit_hash_stable]
docker compose build [service]
docker compose up -d [service]
```

### Kafka Consumer Lag Élevé

```bash
# Identifier le service lent
docker exec b2g-kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --all-groups

# Augmenter resources service lent (éditer docker-compose.yml)
services:
  forecasting:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G

# Redémarrer
docker compose up -d forecasting
```

### Base de Données Pleine

```bash
# Vérifier taille
docker exec -it b2g-timescaledb psql -U b2g -d b2g \
  -c "SELECT pg_size_pretty(pg_database_size('b2g'));"

# Nettoyer données anciennes (ajuster période)
docker exec -it b2g-timescaledb psql -U b2g -d b2g \
  -c "DELETE FROM pipeline_outputs WHERE timestamp < NOW() - INTERVAL '6 months';"

# Vacuum
docker exec -it b2g-timescaledb psql -U b2g -d b2g \
  -c "VACUUM FULL pipeline_outputs;"

# Ou réduire rétention policy
docker exec -it b2g-timescaledb psql -U b2g -d b2g \
  -c "SELECT alter_job((SELECT job_id FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'), schedule_interval => INTERVAL '1 day', config => jsonb_build_object('drop_after', INTERVAL '6 months'));"
```

### Kafka Disque Plein

```bash
# Vérifier taille topics
docker exec b2g-kafka kafka-log-dirs \
  --bootstrap-server localhost:9092 --describe

# Réduire rétention topic problématique
docker exec b2g-kafka kafka-configs \
  --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name telemetry.raw \
  --alter --add-config retention.ms=604800000  # 7 jours

# Forcer nettoyage
docker exec b2g-kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --alter --topic telemetry.raw \
  --config segment.ms=3600000  # 1 heure
```

---

## 💾 Backup et Restauration

### Backup TimescaleDB

```bash
# Backup complet
docker exec b2g-timescaledb pg_dump -U b2g -d b2g -F c \
  > backup_b2g_$(date +%Y%m%d_%H%M%S).dump

# Backup données uniquement (plus petit)
docker exec b2g-timescaledb pg_dump -U b2g -d b2g -F c \
  --data-only -t pipeline_outputs \
  > backup_data_$(date +%Y%m%d_%H%M%S).dump

# Backup automatique quotidien (cron)
0 2 * * * /opt/smart-supermarket-b2g/scripts/backup.sh
```

### Restauration TimescaleDB

```bash
# Restaurer backup complet
cat backup_b2g_20261013_020000.dump | \
  docker exec -i b2g-timescaledb pg_restore -U b2g -d b2g -c

# Restaurer données uniquement
cat backup_data_20261013_020000.dump | \
  docker exec -i b2g-timescaledb pg_restore -U b2g -d b2g --data-only
```

### Backup Configuration

```bash
# Sauvegarder .env et docker-compose.yml
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  .env docker-compose.yml

# Sauvegarder volumes Docker (Kafka data)
docker run --rm \
  -v smartsupermarket_kafka_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/kafka_data_$(date +%Y%m%d).tar.gz /data
```

---

## 📈 Scaling Stratégies

### Scaling Vertical (Augmenter Ressources)

Éditer `docker-compose.yml`:

```yaml
services:
  forecasting:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G
```

### Scaling Horizontal (Multiple Instances)

**Forecasting Service** (peut scaler facilement):
```bash
# Lancer 3 instances
docker compose up -d --scale forecasting=3

# Kafka distribue automatiquement les partitions
```

**MPC Service** (1 partition → 1 instance max recommandé)
```bash
# Augmenter partitions si besoin plus d'instances
docker exec b2g-kafka kafka-topics --bootstrap-server localhost:9092 \
  --alter --topic forecasting.predictions --partitions 4

# Puis scaler
docker compose up -d --scale mpc=4
```

---

## 🔐 Sécurité Production

### Checklist Sécurité

- [ ] **Firewall actif** (UFW, iptables)
- [ ] **Ports restreints** (uniquement API 8000 exposé publiquement)
- [ ] **SSL/TLS** sur API (reverse proxy Nginx/Traefik)
- [ ] **Secrets externalisés** (Docker secrets, Vault)
- [ ] **Kafka authentication** (SASL/SCRAM activé)
- [ ] **TimescaleDB SSL** connections
- [ ] **Redis password** activé
- [ ] **Logs sanitized** (pas de mots de passe)
- [ ] **Rate limiting** sur API
- [ ] **Fail2ban** installé
- [ ] **Backups chiffrés**
- [ ] **Monitoring sécurité** (tentatives accès)
- [ ] **Updates régulières** images Docker

### Exemple Firewall UFW

```bash
# Autoriser SSH
sudo ufw allow 22/tcp

# Autoriser API (via reverse proxy)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Bloquer accès direct bases de données
sudo ufw deny 5432/tcp
sudo ufw deny 6379/tcp
sudo ufw deny 9092/tcp

# Activer
sudo ufw enable
```

---

## 📞 Support et Troubleshooting

### Contacts

- **Équipe Développement:** dev-team@company.com
- **Équipe Ops:** ops-team@company.com
- **On-call:** +33-XX-XX-XX-XX-XX

### Ressources

- **Documentation API:** http://[server]:8000/docs
- **GitHub Repository:** https://github.com/Eyaiscoding/SmartSupermarket
- **Architecture Technique:** ARCHITECTURE_TECHNIQUE.md
- **Guide Tests:** END_TO_END_TESTING_GUIDE.md

### Logs Communs Erreurs

| Erreur | Cause | Solution |
|--------|-------|----------|
| `kafka.errors.NoBrokersAvailable` | Kafka pas démarré | `docker compose up -d kafka` |
| `JSONDecodeError` | Message malformé dans topic | Nettoyer topic ou corriger producteur |
| `psycopg2.OperationalError` | TimescaleDB inaccessible | Vérifier credentials `.env` |
| `redis.exceptions.ConnectionError` | Redis pas démarré | `docker compose up -d redis` |
| `kafka consumer lag > 1000` | Service trop lent | Scaler service ou augmenter resources |

---

**Version:** 1.0  
**Dernière révision:** Octobre 2026  
**Maintenu par:** Équipe Smart Supermarket B2G
