$env:DEBUG = "True"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$proxyVars = @(
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy"
)

foreach ($name in $proxyVars) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
