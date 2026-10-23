$ErrorActionPreference = 'Stop'
py -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Unable to create Python virtualenv' }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Unable to install dependencies' }
.\.venv\Scripts\python.exe -m team7_pipeline doctor
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed' }
