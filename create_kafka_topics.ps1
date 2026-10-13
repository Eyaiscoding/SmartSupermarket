# Create all Kafka topics for the Smart Supermarket B2G platform

Write-Host "Creating Kafka topics..." -ForegroundColor Cyan

# Topic 1: Forecasting predictions
Write-Host "`n[1/5] Creating forecasting.predictions topic (2 partitions)..."
docker exec smartsupermarket-kafka-1 kafka-topics.sh --create --topic forecasting.predictions --partitions 2 --replication-factor 1 --if-not-exists --bootstrap-server localhost:9092

# Topic 2: Telemetry raw data
Write-Host "`n[2/5] Creating telemetry.raw topic (4 partitions)..."
docker exec smartsupermarket-kafka-1 kafka-topics.sh --create --topic telemetry.raw --partitions 4 --replication-factor 1 --if-not-exists --bootstrap-server localhost:9092

# Topic 3: MPC decisions
Write-Host "`n[3/5] Creating mpc.decisions topic (1 partition)..."
docker exec smartsupermarket-kafka-1 kafka-topics.sh --create --topic mpc.decisions --partitions 1 --replication-factor 1 --if-not-exists --bootstrap-server localhost:9092

# Topic 4: DERMS dispatch commands
Write-Host "`n[4/5] Creating derms.dispatch topic (2 partitions)..."
docker exec smartsupermarket-kafka-1 kafka-topics.sh --create --topic derms.dispatch --partitions 2 --replication-factor 1 --if-not-exists --bootstrap-server localhost:9092

# Topic 5: Compliance reports
Write-Host "`n[5/5] Creating compliance.reports topic (1 partition)..."
docker exec smartsupermarket-kafka-1 kafka-topics.sh --create --topic compliance.reports --partitions 1 --replication-factor 1 --if-not-exists --bootstrap-server localhost:9092

# List all topics to verify
Write-Host "`n`nVerifying created topics:" -ForegroundColor Green
docker exec smartsupermarket-kafka-1 kafka-topics.sh --list --bootstrap-server localhost:9092

Write-Host "`n✅ Kafka topics created successfully!" -ForegroundColor Green
