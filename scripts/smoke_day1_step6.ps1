param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

Write-Host "[1/4] Checking health endpoint..."
try {
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"
} catch {
    Fail "Health check failed for $BaseUrl/health. Ensure backend is running. Details: $($_.Exception.Message)"
}

if ($health.status -ne "ok") {
    Fail "Unexpected health response. Expected status=ok, got: $($health | ConvertTo-Json -Compress)"
}

$adminUsername = $env:ADMIN_USERNAME
$adminPassword = $env:ADMIN_PASSWORD
if ([string]::IsNullOrWhiteSpace($adminUsername)) { $adminUsername = "admin" }
if ([string]::IsNullOrWhiteSpace($adminPassword)) { $adminPassword = "admin123" }

Write-Host "[2/4] Login with admin credentials..."
$loginBody = @{
    username = $adminUsername
    password = $adminPassword
} | ConvertTo-Json

try {
    $loginResponse = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/login" -ContentType "application/json" -Body $loginBody
} catch {
    Fail "Login request failed. Check ADMIN_USERNAME/ADMIN_PASSWORD and backend logs. Details: $($_.Exception.Message)"
}

if ([string]::IsNullOrWhiteSpace($loginResponse.access_token)) {
    Fail "Login response does not contain access_token. Response: $($loginResponse | ConvertTo-Json -Compress)"
}

if ($loginResponse.token_type -ne "bearer") {
    Fail "Unexpected token_type. Expected bearer, got: $($loginResponse.token_type)"
}

$token = $loginResponse.access_token

Write-Host "[3/4] Verify unauthorized access without token..."
$unauthStatus = $null
try {
    Invoke-WebRequest -Method Get -Uri "$BaseUrl/api/cars" -UseBasicParsing | Out-Null
    Fail "Expected HTTP 401 for /api/cars without token, but request succeeded."
} catch {
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $unauthStatus = [int]$_.Exception.Response.StatusCode
    }
}

if ($unauthStatus -ne 401) {
    Fail "Expected HTTP 401 for /api/cars without token, got: $unauthStatus"
}

Write-Host "[4/4] Fetch cars with JWT token..."
$authHeaders = @{ Authorization = "Bearer $token" }
try {
    $carsResponse = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/cars" -Headers $authHeaders
} catch {
    Fail "Authorized /api/cars request failed. Details: $($_.Exception.Message)"
}

if (-not ($carsResponse -is [System.Array])) {
    Fail "Expected /api/cars response to be an array. Got: $($carsResponse | ConvertTo-Json -Compress)"
}

if ($carsResponse.Count -lt 1) {
    Fail "Expected non-empty cars list (seeded data), but got empty array."
}

$requiredKeys = @("brand", "model", "year", "price", "color", "link")
$firstCar = $carsResponse[0]
foreach ($key in $requiredKeys) {
    if ($null -eq $firstCar.$key) {
        Fail "First car does not contain required field: $key"
    }
}

Write-Host "Smoke test passed: login and JWT-protected /api/cars work as expected."
exit 0
