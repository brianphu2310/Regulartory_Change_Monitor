# Full monitoring run from your own computer (covers the agencies that refuse cloud runners).
# Needs Docker Desktop. Run from the repo folder:   powershell -ExecutionPolicy Bypass -File .\run_local.ps1
docker build -t reg-monitor .
New-Item -ItemType Directory -Force -Path data\live, reports | Out-Null
docker run --rm -v "${PWD}\data:/app/data" -v "${PWD}\reports:/app/reports" reg-monitor
Write-Host "Done. Review reports\latest.md, then commit data/live and reports to publish the run."
