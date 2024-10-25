@echo off
setlocal enabledelayedexpansion

set venv_path=venv

if not exist "%venv_path%" (
    echo Creating a new virtual environment...
    echo 新規に仮想環境を作成しています...
    call install.bat
)

REM Activate virtual environment
REM 仮想環境を有効化します
call "%venv_path%\Scripts\activate"
if %errorlevel% neq 0 (
    echo Failed to activate virtual environment. Please check your installation.
    echo 仮想環境の有効化に失敗しました。インストールを確認してください。
    pause
    exit /b 1
)

echo Virtual environment activated.
echo 仮想環境が有効化されました。

REM Run the application
REM アプリケーションを実行します
echo Running the application...
echo アプリケーションを実行しています...
python main.py
if %errorlevel% neq 0 (
    echo The application exited with an error. Please check the logs for more information.
    echo アプリケーションがエラーで終了しました。詳細はログを確認してください。
    pause
    exit /b 1
)

echo Application closed.
echo アプリケーションが終了しました。
pause