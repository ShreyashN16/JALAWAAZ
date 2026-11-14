# Jal Awaaz on Windows PowerShell. Usage: .\run.ps1 [install|doctor|run|test|test-e2e|seed|unseed|smoke|warm|eval|bench|tunnel]
param([string]$cmd = "run")
Set-Location $PSScriptRoot
foreach ($v in @("..\.venv\Scripts\Activate.ps1", ".venv\Scripts\Activate.ps1")) { if (Test-Path $v) { . $v; break } }
switch ($cmd) {
  "install"  { python -m pip install -r requirements-dev.txt }
  "doctor"   { python -m scripts.doctor }
  "run"      { python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 }
  "test"     { python -m pytest -q --ignore=tests/e2e }
  "test-e2e" { python -m pytest -q tests/e2e }
  "seed"     { python -m scripts.seed_demo }
  "unseed"   { python -m scripts.seed_demo --clear }
  "smoke"    { python -m scripts.smoke }
  "warm"     { python -m scripts.warm_tts }
  "eval"     { python -m bench.text_eval }
  "bench"    { python -m bench.make_noisy; if ($?) { python -m bench.run_bench } }
  "tunnel"   { cloudflared tunnel --url http://localhost:8000 }
  default    { Write-Host "Unknown command '$cmd'. Use: install doctor run test test-e2e seed unseed smoke warm eval bench tunnel" }
}
