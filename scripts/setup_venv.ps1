# setup_venv.ps1
# Finds a Python 3.11 interpreter, creates .venv, upgrades pip and installs requirements

$candidates = @( @('py','-3.11'), @('python3.11'), @('python') )
$found = $null
foreach ($cmd in $candidates) {
    try {
        if ($cmd.Length -eq 2) {
            $out = & $cmd[0] $cmd[1] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        } else {
            $out = & $cmd[0] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        }
        if ($LASTEXITCODE -eq 0 -and $out -like '3.11*') {
            $found = $cmd
            break
        }
    } catch {}
}

if (-not $found) {
    Write-Error 'Python 3.11 not found. Install Python 3.11 or adjust the script.'
    exit 1
}

Write-Host "Using interpreter: $($found -join ' ')"
if ($found.Length -eq 2) {
    & $found[0] $found[1] -m venv .venv
} else {
    & $found[0] -m venv .venv
}

if ($LASTEXITCODE -ne 0) {
    Write-Error 'Failed to create venv'
    exit 1
}

.\.venv\Scripts\python -m pip install -U pip
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Failed to upgrade pip'
    exit 1
}

.\.venv\Scripts\python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Failed to install requirements'
    exit 1
}

.\.venv\Scripts\python -c "import vectorbt; print('vectorbt', vectorbt.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Error 'vectorbt import failed'
    exit 1
}

Write-Host 'Setup complete. Activate with: .\\.venv\\Scripts\\Activate.ps1'
