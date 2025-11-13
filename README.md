# backtest-vector-bt

This repository is a starting point for backtesting strategies using the

Setup (Windows, PowerShell)
---------------------------

Prerequisites:
- Python 3.11 (recommended)
- `winget` (optional, recommended for easy install)

1) Install Python 3.11 (one of the options):

	 - Using `winget` (per-user, no admin required):

		 ```powershell
		 winget install --id Python.Python.3.11 -e --source winget --scope user
		 ```

	 - Or download the installer from https://www.python.org/ and run it. Make
		 sure to check "Add Python 3.11 to PATH".

2) Create the virtual environment and install requirements (repo root):

	 ```powershell
	 # create venv with the py launcher
	 py -3.11 -m venv .venv

	 # upgrade pip and install packages
	 .\.venv\Scripts\python -m pip install -U pip
	 .\.venv\Scripts\python -m pip install -r requirements.txt
	 ```

	 Or run the included setup script which detects Python 3.11 and installs
	 dependencies:

	 ```powershell
	 powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_venv.ps1
	 ```

Notes
-----
- If PowerShell blocks script activation (`Activate.ps1`), you can still use
	the venv via the venv python executable (`.\.venv\Scripts\python`). To
	allow activation, run:

	```powershell
	Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
	```

- If `vectorbt` import fails with a Numba/llvmlite DLL error, install the
	Microsoft Visual C++ Redistributable for Visual Studio (x64) from
	https://learn.microsoft.com/en-US/cpp/windows/latest-supported-vc-redist and
	then reinstall `llvmlite`/`numba` in the venv:

	```powershell
	.\.venv\Scripts\python -m pip install --upgrade --force-reinstall llvmlite numba
	```

Verification
------------
After installing, verify imports:

```powershell
.\.venv\Scripts\python -c "import vectorbt; print('vectorbt', vectorbt.__version__)"
.\.venv\Scripts\python -c "import llvmlite, numba; print('llvmlite', llvmlite.__version__, 'numba', numba.__version__)"
```

Optional
--------
- Consider pinning working versions for reproducibility (e.g., add
	`llvmlite==0.45.1` and `numba==0.62.1` to `requirements.txt`).

If you want, I can add a tiny smoke test that runs a trivial `vectorbt`
example and demonstrates everything working.
# backtest-vector-bt