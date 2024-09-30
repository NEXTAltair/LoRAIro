@echo off
setlocal enabledelayedexpansion

REM エラーハンドリングを有効にする
set ERROR_FLAG=0

REM ドキュメントをビルド
echo Building documentation with Sphinx...
sphinx-build -b html docs\source docs\build
if %errorlevel% neq 0 (
    echo Sphinx build failed
    exit /b 1
)
echo Sphinx build succeeded.

REM 現在のブランチ名を保存
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD') do set current_branch=%%i
echo Current branch: %current_branch%

REM 一時ディレクトリの設定（docs\gh-pages-temp から gh-pages-temp に変更）
set temp_dir=gh-pages-temp

REM 一時ディレクトリが存在する場合は削除
if exist %temp_dir% (
    echo Removing existing temporary directory...
    rmdir /s /q %temp_dir%
)

REM リモートURLを取得
for /f "tokens=*" %%i in ('git config --get remote.origin.url') do set remote_url=%%i
echo Remote URL: %remote_url%

REM gh-pagesブランチを一時ディレクトリにクローン
echo Cloning gh-pages branch into %temp_dir%...
git clone -b gh-pages %remote_url% %temp_dir%
if %errorlevel% neq 0 (
    echo Failed to clone gh-pages branch
    exit /b 1
)
echo Clone succeeded.

REM 一時ディレクトリに移動
cd %temp_dir%

REM 既存のファイルを削除（.git ディレクトリを除く）
echo Removing existing files from gh-pages branch...
for /f "delims=" %%a in ('dir /a /b ^| findstr /v "^.git$"') do (
    rmdir /s /q "%%a" 2>nul || del /f /q "%%a"
)

REM 新しいビルド結果をコピー
echo Copying new build results...
xcopy /E /I /Y "..\docs\build\*" .
if %errorlevel% neq 0 (
    echo Failed to copy new build results
    exit /b 1
)
echo Copy succeeded.

REM 変更をコミットしてプッシュ
echo Committing and pushing changes...
git add -A
git commit -m "Update documentation"
git push origin gh-pages
if %errorlevel% neq 0 (
    echo Failed to push to gh-pages branch
    exit /b 1
)
echo Push succeeded.

REM 元のディレクトリに戻る
cd ..

REM 一時ディレクトリを削除
echo Removing temporary directory...
rmdir /s /q %temp_dir%

REM 元のブランチに戻る
echo Checking out original branch: %current_branch%...
git checkout %current_branch%
if %errorlevel% neq 0 (
    echo Failed to checkout original branch
    exit /b 1
)
echo Checked out to %current_branch%.

echo Documentation published to gh-pages branch successfully.
endlocal
