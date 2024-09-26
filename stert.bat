@echo off

set venv_path=venv

if not exist "%venv_path%" (
    echo Creating virtual environment...
    python -m venv "%venv_path%"
)

call "%venv_path%\Scripts\activate"

echo Virtual environment activated.

echo Installing dependencies...
pip install -r requirements.txt

echo Running the application...
python main.py

pause
