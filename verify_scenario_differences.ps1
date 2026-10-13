# Script pour vérifier que les scénarios produisent des données différentes

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Vérification des Différences Entre Scénarios" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

Write-Host "`n🔄 Lancement des scénarios (cela prend ~10 minutes)..." -ForegroundColor Yellow

# Run normal scenario
Write-Host "`n1️⃣  Scénario NORMAL..." -ForegroundColor White
$null = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scenario" -Method POST -Body (@{scenario="none"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing
Start-Sleep -Seconds 2

# Run price spike scenario  
Write-Host "2️⃣  Scénario PRICE SPIKE..." -ForegroundColor White
$null = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/scenario" -Method POST -Body (@{scenario="price_spike"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing
Start-Sleep -Seconds 2

# Query specific dates where scenarios differ
Write-Host "`n📊 Récupération des données pour comparaison..." -ForegroundColor Yellow

# Normal data for day with price spikes (every evening 18:00-21:00)
$normalDay = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/history?start=2025-06-15+00:00:00&end=2025-06-15+23:59:59&scenario=normal" -UseBasicParsing

# Price spike data for same day
$spikeDay = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/history?start=2025-06-15+00:00:00&end=2025-06-15+23:59:59&scenario=price_spike" -UseBasicParsing

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  COMPARAISON: 15 Juin 2025, 18:00-21:00 (Heures de Pointe)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# Find evening timesteps (18:00-21:00)
$normalEvening = $normalDay | Where-Object { $_.timestamp -match "T(18|19|20):" } | Select-Object -First 5
$spikeEvening = $spikeDay | Where-Object { $_.timestamp -match "T(18|19|20):" } | Select-Object -First 5

if ($normalEvening -and $spikeEvening) {
    Write-Host "`n📈 SCÉNARIO NORMAL (Prix bas):" -ForegroundColor Green
    $normalEvening | ForEach-Object {
        Write-Host "  $($_.timestamp) | Grid: $($_.grid_power) kW | Battery: $($_.battery_soc)% | Actions: $($_.active_actions -join ', ')" -ForegroundColor White
    }
    
    Write-Host "`n💰 SCÉNARIO PRICE SPIKE (Prix x8):" -ForegroundColor Yellow
    $spikeEvening | ForEach-Object {
        Write-Host "  $($_.timestamp) | Grid: $($_.grid_power) kW | Battery: $($_.battery_soc)% | Actions: $($_.active_actions -join ', ')" -ForegroundColor White
    }
    
    Write-Host "`n✅ DIFFÉRENCES ATTENDUES:" -ForegroundColor Cyan
    Write-Host "  - Price Spike: Grid Power devrait être INFÉRIEUR (on évite le réseau)" -ForegroundColor White
    Write-Host "  - Price Spike: Battery SoC devrait DESCENDRE (décharge pour éviter achat)" -ForegroundColor White
    Write-Host "  - Price Spike: Actions devrait inclure 'peak_shaving' ou 'hvac_soft_shed'" -ForegroundColor White
} else {
    Write-Host "❌ Aucune donnée trouvée pour cette période" -ForegroundColor Red
    Write-Host "   Vérifiez que les scénarios sont terminés et que TimescaleDB contient les données" -ForegroundColor Yellow
}

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  POUR VISUALISER DANS LE DASHBOARD:" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "1. Ouvrir: http://localhost:5173/" -ForegroundColor White
Write-Host "2. Mode: Historique" -ForegroundColor White
Write-Host "3. Dates: Du 2025-06-15 au 2025-06-15" -ForegroundColor White
Write-Host "4. Observer le graphique 'Prix de l'électricité' et 'Flux énergétiques'" -ForegroundColor White
Write-Host "5. Zoomer sur 18:00-21:00 pour voir la différence" -ForegroundColor White

Write-Host "`n✅ Script terminé!" -ForegroundColor Green
