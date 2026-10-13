# Script pour tester l'impact des scénarios et afficher les différences

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Test Impact des Scénarios" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

Write-Host "`n📊 Test 1: Scénario NORMAL" -ForegroundColor Yellow
$normal = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scenario" -Method POST -Body (@{scenario="none"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing

Write-Host "`n💰 Test 2: Scénario PIC DE PRIX" -ForegroundColor Yellow
$priceSpike = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scenario" -Method POST -Body (@{scenario="price_spike"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing

Write-Host "`n⚡ Test 3: Scénario COUPURE RÉSEAU" -ForegroundColor Yellow
$gridOutage = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scenario" -Method POST -Body (@{scenario="forced_grid_outage"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing

Write-Host "`n🔧 Test 4: Scénario CAPTEUR DÉFAILLANT" -ForegroundColor Yellow
$sensorCorruption = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scenario" -Method POST -Body (@{scenario="sensor_corruption"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing

Write-Host "`n`n==================================================================" -ForegroundColor Cyan
Write-Host "  COMPARAISON DES RÉSULTATS" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

$comparison = @(
    [PSCustomObject]@{
        Scénario = "Normal"
        'Tier 1 Breaches' = $normal.tier_1_breaches
        'Peak Shave Count' = $normal.peak_shave_count
        'Hard Shed Count' = $normal.hard_shed_count
        'Coverage Min' = $normal.coverage_ratio_min
        'Coverage Mean' = $normal.coverage_ratio_mean
        'Anomaly Count' = $normal.anomaly_count
    },
    [PSCustomObject]@{
        Scénario = "Price Spike"
        'Tier 1 Breaches' = $priceSpike.tier_1_breaches
        'Peak Shave Count' = $priceSpike.peak_shave_count
        'Hard Shed Count' = $priceSpike.hard_shed_count
        'Coverage Min' = $priceSpike.coverage_ratio_min
        'Coverage Mean' = $priceSpike.coverage_ratio_mean
        'Anomaly Count' = $priceSpike.anomaly_count
    },
    [PSCustomObject]@{
        Scénario = "Grid Outage"
        'Tier 1 Breaches' = $gridOutage.tier_1_breaches
        'Peak Shave Count' = $gridOutage.peak_shave_count
        'Hard Shed Count' = $gridOutage.hard_shed_count
        'Coverage Min' = $gridOutage.coverage_ratio_min
        'Coverage Mean' = $gridOutage.coverage_ratio_mean
        'Anomaly Count' = $gridOutage.anomaly_count
    },
    [PSCustomObject]@{
        Scénario = "Sensor Corruption"
        'Tier 1 Breaches' = $sensorCorruption.tier_1_breaches
        'Peak Shave Count' = $sensorCorruption.peak_shave_count
        'Hard Shed Count' = $sensorCorruption.hard_shed_count
        'Coverage Min' = $sensorCorruption.coverage_ratio_min
        'Coverage Mean' = $sensorCorruption.coverage_ratio_mean
        'Anomaly Count' = $sensorCorruption.anomaly_count
    }
)

$comparison | Format-Table -AutoSize

Write-Host "`n📍 POINTS D'IMPACT SPÉCIFIQUES:" -ForegroundColor Green
Write-Host "  - Price Spike: Timesteps 500-507 (8 points = 2h)" -ForegroundColor White
Write-Host "  - Grid Outage: Timesteps 200-215 (16 points = 4h)" -ForegroundColor White  
Write-Host "  - Sensor Corruption: Timesteps 1000-1003 (4 points = 1h)" -ForegroundColor White

Write-Host "`n💡 POUR VOIR L'IMPACT VISUEL:" -ForegroundColor Yellow
Write-Host "  1. Ouvrir dashboard: http://localhost:5173/" -ForegroundColor White
Write-Host "  2. Mode 'Historique'" -ForegroundColor White
Write-Host "  3. Pour Price Spike: dates 2025-06-06 à 2025-06-06 (timestep 500 ≈ jour 6)" -ForegroundColor White
Write-Host "  4. Pour Grid Outage: dates 2025-06-03 à 2025-06-03 (timestep 200 ≈ jour 3)" -ForegroundColor White
Write-Host "  5. Zoomer sur les graphiques pour voir les pics" -ForegroundColor White

Write-Host "`n✅ Test terminé!" -ForegroundColor Green
