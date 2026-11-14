# Run this script by dot-sourcing it in the same PowerShell that starts the server.
$env:RECRUITER_DEMO = '1'
# For an external AI provider, use a new database and set RECRUITER_DEMO to 0.
# $env:RECRUITER_DB = 'data/live.sqlite3'
# $env:RECRUITER_AI_URL = 'https://provider.example/v1/chat/completions'
# $env:RECRUITER_AI_MODEL = 'model-id'
# $env:RECRUITER_AI_TIMEOUT = '60'
# Inject RECRUITER_ADMIN_PASSWORD and RECRUITER_AI_KEY in the server environment.
