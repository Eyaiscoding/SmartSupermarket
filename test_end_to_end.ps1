# Smart Supermarket B2G Platform - End-to-End Testing Script
# This script demonstrates the complete event-driven pipeline

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Smart Supermarket B2G Platform - End-to-End Testing" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# Step 1: Check all services are running
Write-Host "`n[Step 1/10] Checking all services status..." -ForegroundColor Yellow
docker compose ps

# Step 2: Verify Kafka topics exist
Write-Host "`n[Step 2/10] Verifying Kafka topics..." -ForegroundColor Yellow
docker exec smartsupermarket-kafka-1 kafka-topics.sh --list --bootstrap-server localhost:9092

# Step 3: Check service health endpoints
Write-Host "`n[Step 3/10] Checking service health endpoints..." -ForegroundColor Yellow
Write-Host "  - Backend API: " -NoNewline
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
    Write-Host "✅ $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed" -ForegroundColor Red
}

Write-Host "  - Forecasting Service: " -NoNewline
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -UseBasicParsing
    Write-Host "✅ $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed" -ForegroundColor Red
}

Write-Host "  - MPC Service: " -NoNewline
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8002/health" -UseBasicParsing
    Write-Host "✅ $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed" -ForegroundColor Red
}

Write-Host "  - DERMS Service: " -NoNewline
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8003/health" -UseBasicParsing
    Write-Host "✅ $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed" -ForegroundColor Red
}

Write-Host "  - Compliance Service: " -NoNewline
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8004/health" -UseBasicParsing
    Write-Host "✅ $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed" -ForegroundColor Red
}

# Step 4: Send test telemetry event
Write-Host "`n[Step 4/10] Publishing test telemetry event to Kafka..." -ForegroundColor Yellow
$testPayload = @'
{"ts": "2024-01-15T10:00:00Z", "T_ext": 5.2, "I_global": 450, "load_kw": 125.5, "pv_kw": 48.3, "batt_soc": 65.0, "batt_kw": -5.0, "price_eur_kwh": 0.15, "grid_kw": 82.2}
'@

docker exec smartsupermarket-kafka-1 kafka-console-producer.sh --topic telemetry.raw --bootstrap-server localhost:9092 --property "parse.key=false" <<< $testPayload
Write-Host "✅ Test event published" -ForegroundColor Green

# Step 5: Monitor pipeline flow
Write-Host "`n[Step 5/10] Monitoring event flow through pipeline (10 seconds)..." -ForegroundColor Yellow
Write-Host "  Watching: telemetry.raw → forecasting.predictions → mpc.decisions → derms.dispatch → compliance.reports"
Start-Sleep -Seconds 10

# Step 6: Check forecasting.predictions topic
Write-Host "`n[Step 6/10] Checking forecasting.predictions topic..." -ForegroundColor Yellow
docker exec smartsupermarket-kafka-1 kafka-console-consumer.sh --topic forecasting.predictions --from-beginning --max-messages 1 --timeout-ms 5000 --bootstrap-server localhost:9092

# Step 7: Check mpc.decisions topic
Write-Host "`n[Step 7/10] Checking mpc.decisions topic..." -ForegroundColor Yellow
docker exec smartsupermarket-kafka-1 kafka-console-consumer.sh --topic mpc.decisions --from-beginning --max-messages 1 --timeout-ms 5000 --bootstrap-server localhost:9092

# Step 8: Check derms.dispatch topic
Write-Host "`n[Step 8/10] Checking derms.dispatch topic..." -ForegroundColor Yellow
docker exec smartsupermarket-kafka-1 kafka-console-consumer.sh --topic derms.dispatch --from-beginning --max-messages 1 --timeout-ms 5000 --bootstrap-server localhost:9092

# Step 9: Check compliance.reports topic
Write-Host "`n[Step 9/10] Checking compliance.reports topic..." -ForegroundColor Yellow
docker exec smartsupermarket-kafka-1 kafka-console-consumer.sh --topic compliance.reports --from-beginning --max-messages 1 --timeout-ms 5000 --bootstrap-server localhost:9092

# Step 10: Query API for results
Write-Host "`n[Step 10/10] Querying API for latest results..." -ForegroundColor Yellow
try {
    $latest = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/latest" -UseBasicParsing
    Write-Host "✅ Latest data retrieved:" -ForegroundColor Green
    $latest | ConvertTo-Json -Depth 3
} catch {
    Write-Host "❌ Failed to retrieve latest data" -ForegroundColor Red
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  End-to-End Test Complete!" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. Check service logs: docker compose logs -f [service-name]"
Write-Host "  2. View TimescaleDB data: docker exec -it smartsupermarket-timescaledb-1 psql -U postgres -d smartsupermarket"
Write-Host "  3. Check Redis cache: docker exec -it smartsupermarket-redis-1 redis-cli"
Write-Host "  4. Run scenario tests: python scenario_runner.py --scenario price_spike"
Write-Host "  5. Access API docs: http://localhost:8000/docs"
