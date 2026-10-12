#!/usr/bin/env pwsh
# rebuild-docker.ps1
# Automated Docker rebuild and verification script for B2G Smart Supermarket

$ErrorActionPreference = "Continue"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "B2G Smart Supermarket - Docker Rebuild" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Step 1: Stop existing containers
Write-Host "[1/6] Stopping existing containers..." -ForegroundColor Yellow
docker compose down
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Containers stopped successfully`n" -ForegroundColor Green
} else {
    Write-Host "⚠ Warning: Container stop failed (may not exist)`n" -ForegroundColor Yellow
}

# Step 2: Rebuild images with no cache
Write-Host "[2/6] Rebuilding Docker images (this may take 2-3 minutes)..." -ForegroundColor Yellow
docker compose build --no-cache
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Images rebuilt successfully`n" -ForegroundColor Green
} else {
    Write-Host "✗ Error: Image rebuild failed`n" -ForegroundColor Red
    exit 1
}

# Step 3: Start services
Write-Host "[3/6] Starting Docker stack..." -ForegroundColor Yellow
Start-Job -ScriptBlock { docker compose up } | Out-Null
Write-Host "✓ Services starting in background`n" -ForegroundColor Green

# Step 4: Wait for services to become healthy
Write-Host "[4/6] Waiting for services to become healthy (60-90 seconds)..." -ForegroundColor Yellow
$maxWait = 90
$waited = 0
$allHealthy = $false

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 5
    $waited += 5
    
    $status = docker compose ps --format json | ConvertFrom-Json
    $healthyCount = 0
    $totalCount = 0
    
    foreach ($service in $status) {
        $totalCount++
        if ($service.Health -eq "healthy") {
            $healthyCount++
        }
    }
    
    Write-Host "  Progress: $healthyCount/$totalCount services healthy (${waited}s elapsed)" -ForegroundColor Gray
    
    if ($healthyCount -eq $totalCount -and $totalCount -gt 0) {
        $allHealthy = $true
        break
    }
}

if ($allHealthy) {
    Write-Host "✓ All services healthy`n" -ForegroundColor Green
} else {
    Write-Host "⚠ Warning: Not all services healthy after ${maxWait}s`n" -ForegroundColor Yellow
}

# Step 5: Verify API health
Write-Host "[5/6] Verifying API endpoints..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 10
    if ($healthResponse.status -eq "healthy") {
        Write-Host "✓ API health check passed" -ForegroundColor Green
        Write-Host "  - TimescaleDB: $($healthResponse.timescaledb)" -ForegroundColor Gray
        Write-Host "  - Redis: $($healthResponse.redis)`n" -ForegroundColor Gray
    } else {
        Write-Host "⚠ API health check returned unexpected status`n" -ForegroundColor Yellow
    }
} catch {
    Write-Host "✗ API health check failed: $_`n" -ForegroundColor Red
}

# Step 6: Display service status
Write-Host "[6/6] Final service status:" -ForegroundColor Yellow
docker compose ps
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Rebuild Complete" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Test WebSocket: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  2. Run tests: python -m pytest tests/ -v" -ForegroundColor White
Write-Host "  3. Start dashboard: cd dashboard && npm run dev`n" -ForegroundColor White

Write-Host "Logs:" -ForegroundColor Yellow
Write-Host "  View all logs: docker compose logs" -ForegroundColor White
Write-Host "  View backend logs: docker compose logs backend -f" -ForegroundColor White
Write-Host "  Stop services: docker compose down`n" -ForegroundColor White
