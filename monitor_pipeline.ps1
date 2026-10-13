# Smart Supermarket B2G Platform - Pipeline Monitoring Script
# Monitor all microservices logs in real-time

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('all', 'backend', 'forecasting', 'mpc', 'derms', 'compliance', 'kafka')]
    [string]$Service = 'all'
)

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Smart Supermarket B2G Platform - Pipeline Monitor" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

if ($Service -eq 'all') {
    Write-Host "`nMonitoring ALL services (press Ctrl+C to stop)..." -ForegroundColor Yellow
    Write-Host "Color coding:" -ForegroundColor White
    Write-Host "  🔵 Backend    | 🟢 Forecasting | 🟡 MPC" -ForegroundColor White
    Write-Host "  🟠 DERMS      | 🟣 Compliance  | ⚫ Kafka" -ForegroundColor White
    Write-Host ""
    
    docker compose logs -f --tail=50 backend forecasting mpc derms compliance kafka
} else {
    Write-Host "`nMonitoring $Service service (press Ctrl+C to stop)..." -ForegroundColor Yellow
    docker compose logs -f --tail=100 $Service
}
