@echo off
setlocal enabledelayedexpansion

REM Set PYTHONPATH
set "PYTHONPATH=%~dp0src;%~dp0src\module\genai-tag-db-tools;%PYTHONPATH%"
set venv_path=venv

REM Check if Git is installed
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Git is not installed or not in the PATH. Please install Git and try again.
    echo Gitがインストールされていないか、PATHに設定されていません。Gitをインストールして再試行してください。
    pause
    exit /b 1
)

REM Clone the genai-tag-db-tools repository if it doesn't exist
set "submodule_path=src\module\genai-tag-db-tools"
if not exist "%submodule_path%\.git" (
    echo Cloning genai-tag-db-tools repository...
    echo genai-tag-db-toolsリポジトリをクローンしています...
    git clone https://github.com/NEXTAltair/genai-tag-db-tools.git "%submodule_path%"
    if !errorlevel! neq 0 (
        echo Failed to clone genai-tag-db-tools repository. Please check your network connection and try again.
        echo genai-tag-db-toolsリポジトリのクローンに失敗しました。ネットワーク接続を確認して再試行してください。
        pause
        exit /b 1
    )
)

REM Check if Python is installed
REM Pythonがインストールされているか確認します
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in the PATH. Please install Python and try again.
    echo Pythonがインストールされていないか、PATHに設定されていません。Pythonをインストールして再試行してください。
    pause
    exit /b 1
)

REM Rename processing.template.toml to processing.toml if it doesn't exist
REM processing.tomlが存在しない場合、processing.template.tomlをリネームします
if not exist "processing.toml" (
    if exist "processing.template.toml" (
        echo Renaming processing.template.toml to processing.toml...
        echo processing.template.tomlをprocessing.tomlにリネームしています...
        ren "processing.template.toml" "processing.toml"
    ) else (
        echo Warning: processing.template.toml not found. Please ensure you have the correct configuration file.
        echo 警告: processing.template.tomlが見つかりません。正しい設定ファイルがあることを確認してください。
    )
) else (
    echo processing.toml already exists. Using existing file.
    echo processing.tomlは既に存在します。既存のファイルを使用します。
)

REM Create virtual environment if it doesn't exist
REM 仮想環境が存在しない場合、作成します
if not exist "%venv_path%" (
    echo Creating virtual environment...
    echo 仮想環境を作成しています...
    python -m venv "%venv_path%"
    if !errorlevel! neq 0 (
        echo Failed to create virtual environment. Please check your Python installation.
        echo 仮想環境の作成に失敗しました。Pythonのインストールを確認してください。
        pause
        exit /b 1
    )
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

REM Install or upgrade dependencies
REM 依存関係をインストールまたはアップグレードします
echo Updating pip...
echo pipをアップデートしています...
python -m pip install --upgrade pip
echo Installing/upgrading dependencies...
echo 依存関係をインストール/アップグレードしています...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies. Please check your internet connection and try again.
    echo 依存関係のインストールに失敗しました。インターネット接続を確認して再試行してください。
    pause
    exit /b 1
)

REM Initialize and update submodules
REM サブモジュールの初期化と更新
echo Initializing and updating submodules...
echo サブモジュールを初期化・更新しています...
git submodule update --init --recursive
if %errorlevel% neq 0 (
    echo Failed to initialize and update submodules. Please check your git installation and network connection.
    echo サブモジュールの初期化・更新に失敗しました。Gitのインストールとネットワーク接続を確認してください。
    pause
    exit /b 1
)

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