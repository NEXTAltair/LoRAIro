# PySide6 総合ガイド - ウィンドウ表示とトラブルシューティング

## PySide6 基本情報

### 概要
- **PySide6**: Qt 6 フレームワークの公式Python バインディング
- **バージョン**: 6.9.1 (最新安定版)
- **目的**: クロスプラットフォームGUIアプリケーション開発
- **ライセンス**: LGPL/Commercial

### 主要モジュール
- `PySide6.QtWidgets`: GUI ウィジェット (QApplication, QMainWindow, QWidget等)
- `PySide6.QtCore`: コア機能 (QTimer, Signal, Slot等)
- `PySide6.QtGui`: グラフィックス関連 (QFont, QIcon, QPixmap等)

## 標準的なアプリケーション起動パターン

### 基本パターン
```python
import sys
from PySide6.QtWidgets import QApplication, QMainWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # UI設定

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()  # 重要: 明示的にshow()を呼ぶ
    sys.exit(app.exec())  # イベントループ開始
```

### 推奨される完全パターン
```python
import sys
import os
import platform
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtCore import Qt

def setup_qt_environment():
    """Qt環境設定"""
    # プラットフォーム別設定
    if platform.system() == "Linux":
        # WSL/コンテナ環境対応
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
    elif platform.system() == "Windows":
        os.environ["QT_QPA_PLATFORM"] = "windows"

def setup_fonts(app):
    """フォント設定"""
    families = QFontDatabase.families()
    preferred_fonts = ["Arial", "Helvetica", "Segoe UI", "DejaVu Sans"]
    
    for font_name in preferred_fonts:
        if font_name in families:
            font = QFont(font_name, 10)
            app.setFont(font)
            break

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Application")
        self.resize(800, 600)

if __name__ == "__main__":
    # Qt環境設定
    setup_qt_environment()
    
    # QApplication作成
    app = QApplication(sys.argv)
    app.setApplicationName("TestApp")
    
    # フォント設定
    setup_fonts(app)
    
    # メインウィンドウ作成・表示
    window = MainWindow()
    window.show()
    
    # デバッグ情報
    print(f"Window visible: {window.isVisible()}")
    print(f"Window size: {window.size()}")
    print(f"Platform: {platform.system()}")
    print(f"QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'Not set')}")
    
    # イベントループ開始
    sys.exit(app.exec())
```

## ウィンドウ表示の問題と解決策

### 1. ウィンドウが表示されない問題

#### 主な原因
1. **show()メソッドの呼び忘れ**: 最も一般的な原因
2. **QApplication.exec()の呼び忘れ**: イベントループが開始されない
3. **環境変数の問題**: DISPLAY未設定、QT_QPA_PLATFORM不適切
4. **早期終了**: windowオブジェクトのスコープ問題

#### 解決手順
```python
# 1. 基本チェック
window = MainWindow()
window.show()  # 必須
print(f"Visible: {window.isVisible()}")  # デバッグ出力

# 2. 強制表示
window.show()
window.raise_()           # 前面に表示
window.activateWindow()   # アクティブ化
app.processEvents()       # イベント処理強制実行

# 3. 環境チェック
print(f"DISPLAY: {os.environ.get('DISPLAY', 'Not set')}")
print(f"QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'Not set')}")
```

### 2. プラットフォーム固有の問題

#### Linux/WSL環境
```python
# X11転送が必要または offscreen モード
if platform.system() == "Linux":
    if not os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        print("Using offscreen mode")
```

#### Windows環境
```python
if platform.system() == "Windows":
    os.environ["QT_QPA_PLATFORM"] = "windows"
    # フォントディレクトリ設定
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
```

### 3. デバッグ手法

#### 詳細診断機能
```python
def diagnose_qt_environment():
    """Qt環境の詳細診断"""
    print("=== Qt Environment Diagnosis ===")
    print(f"Platform: {platform.system()}")
    print(f"QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'Not set')}")
    print(f"DISPLAY: {os.environ.get('DISPLAY', 'Not set')}")
    print(f"Available platforms: {QApplication.platformName()}")
    
    # フォント情報
    families = QFontDatabase.families()
    print(f"Available fonts: {len(families)}")
    print(f"Sample fonts: {families[:5]}")

# 使用方法
if __name__ == "__main__":
    app = QApplication(sys.argv)
    diagnose_qt_environment()  # 診断実行
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

## QMainWindow vs QWidget

### QMainWindow の特徴
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # メニューバー、ツールバー、ステータスバー自動提供
        # setCentralWidget() でメインコンテンツ設定
        
        # 基本設定
        self.setWindowTitle("Application Title")
        self.resize(800, 600)
        
        # 中央ウィジェット設定
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
```

### QWidget の場合
```python
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # より軽量、自由度高い
        self.setWindowTitle("Application Title")
        self.resize(800, 600)
```

## UI設計ファイル (.ui) の統合

### Qt Designer で作成した .ui ファイルの使用
```python
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.load_ui()
    
    def load_ui(self):
        """UIファイル読み込み"""
        loader = QUiLoader()
        ui_file = QFile("mainwindow.ui")
        ui_file.open(QFile.ReadOnly)
        self.ui = loader.load(ui_file)
        ui_file.close()
        
        # UIを中央ウィジェットとして設定
        self.setCentralWidget(self.ui)
```

### uic でコンバートされたPythonファイルの使用
```python
from ui_mainwindow import Ui_MainWindow  # Qt Designer -> Python変換

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)  # UI初期化
```

## 一般的なエラーと対処法

### 1. ImportError
```bash
# PySide6がインストールされていない
pip install PySide6

# または uvを使用している場合
uv add PySide6
```

### 2. セグメンテーション違反
```python
# QApplication インスタンスを先に作成
app = QApplication(sys.argv)
# その後でQt関連オブジェクトを作成
window = MainWindow()
```

### 3. ウィンドウが一瞬で消える
```python
# windowオブジェクトをローカル変数でなくグローバルに保持
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()  # グローバルスコープで保持
    window.show()
    sys.exit(app.exec())  # sys.exit()で確実に終了待機
```

## 最良実践とパフォーマンス

### 1. リソース管理
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
    
    def closeEvent(self, event):
        """アプリケーション終了時のクリーンアップ"""
        # リソースの解放
        event.accept()
```

### 2. シグナル・スロット接続
```python
# 手動接続
button.clicked.connect(self.on_button_clicked)

# Qt Designer自動接続 (on_<objectname>_<signal> パターン)
@Slot()
def on_pushButton_clicked(self):
    pass
```

### 3. 非同期処理
```python
from PySide6.QtCore import QThread, QObject, Signal

class Worker(QObject):
    finished = Signal()
    progress = Signal(int)
    
    def run(self):
        # 重い処理
        self.finished.emit()

# 使用方法
worker = Worker()
thread = QThread()
worker.moveToThread(thread)
thread.started.connect(worker.run)
thread.start()
```

## Context7によるPySide6実例分析

### 実際のアプリケーション起動パターン (Context7調査結果)

#### 標準的なmain.py実装
```python
# main.py (Application Entry Point)
import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("MyApp")
    app.setApplicationVersion("1.0.0")
    
    main_window = MainWindow()
    main_window.resize(800, 600)
    main_window.show()
    
    sys.exit(app.exec())
```

#### MainWindow実装パターン
```python
class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # UI設定（Qt Designerから生成されたUIを使用）
        self.setupUi(self)
        
        # カスタムウィジェット設定
        self.setup_custom_widgets()
        
        # シグナル・スロット接続
        self.setup_connections()
        
        # 初期状態設定
        self.initialize_state()
    
    def setup_custom_widgets(self):
        """カスタムウィジェットの設定"""
        # 中央ウィジェット設定例
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
    
    def setup_connections(self):
        """シグナル・スロット接続設定"""
        # Qt自動接続パターンまたは手動接続
        pass
    
    def initialize_state(self):
        """初期状態設定"""
        pass
```

### 環境固有の設定パターン

#### プラットフォーム判定とQt設定
```python
import platform
import os

def setup_qt_environment(config=None):
    """Qt環境の設定とプラットフォーム対応"""
    qt_config = config.get("qt", {}) if config else {}
    
    # プラットフォーム別設定
    system = platform.system()
    
    if system == "Windows":
        # Windows環境の設定
        os.environ["QT_QPA_PLATFORM"] = "windows"
        # フォントディレクトリ設定
        font_dirs = ["C:/Windows/Fonts"]
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                os.environ["QT_QPA_FONTDIR"] = font_dir
                break
    
    elif system == "Linux":
        # Linux環境の設定
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            # ヘッドレス環境
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        else:
            # GUI環境
            os.environ["QT_QPA_PLATFORM"] = "xcb"  # または "wayland"
    
    elif system == "Darwin":  # macOS
        # macOS環境の設定
        os.environ["QT_QPA_PLATFORM"] = "cocoa"
```

### ウィンドウ表示確実化のテクニック

#### 強制表示メソッド
```python
def ensure_window_visible(window, app):
    """ウィンドウ表示を確実に行う"""
    # 基本表示
    window.show()
    app.processEvents()
    
    # 表示確認と追加処理
    if not window.isVisible():
        window.showNormal()
        app.processEvents()
    
    # 前面表示
    window.raise_()
    window.activateWindow()
    
    return window.isVisible()
```

#### 診断とデバッグ機能
```python
def diagnose_qt_environment(app):
    """Qt環境の包括的診断"""
    print("=== Qt Environment Diagnosis ===")
    print(f"Platform: {platform.system()}")
    print(f"QT_QPA_PLATFORM: {os.environ.get('QT_QPA_PLATFORM', 'Not set')}")
    print(f"Available platforms: {app.platformName()}")
    
    # ディスプレイ環境
    if platform.system() == "Linux":
        print(f"DISPLAY: {os.environ.get('DISPLAY', 'Not set')}")
        print(f"WAYLAND_DISPLAY: {os.environ.get('WAYLAND_DISPLAY', 'Not set')}")
    
    # フォント情報
    from PySide6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    print(f"Available fonts: {len(families)}")
    if families:
        print(f"Sample fonts: {families[:5]}")
```

## トラブルシューティング チェックリスト

### アプリケーションが起動しない場合

1. **基本チェック**
   - [ ] `QApplication` インスタンス作成済み
   - [ ] `window.show()` 呼び出し済み
   - [ ] `app.exec()` でイベントループ開始済み

2. **環境チェック**
   - [ ] `DISPLAY` 環境変数設定 (Linux)
   - [ ] `QT_QPA_PLATFORM` 適切に設定
   - [ ] PySide6 正しくインストール済み

3. **デバッグ情報確認**
   - [ ] `window.isVisible()` 結果確認
   - [ ] コンソールエラーメッセージ確認
   - [ ] プラットフォーム情報確認

4. **コード構造**
   - [ ] クラス継承が正しい
   - [ ] `super().__init__()` 呼び出し済み
   - [ ] UI設定が完了してから `show()`

### パフォーマンス問題

1. **レンダリング問題**
   - [ ] 大量ウィジェットの場合は仮想化検討
   - [ ] 不要な再描画を避ける
   - [ ] 重い処理は別スレッドで実行

2. **メモリリーク**
   - [ ] 親子関係正しく設定
   - [ ] 明示的にオブジェクト削除
   - [ ] シグナル接続の適切な解除

## 高度なパターンとベストプラクティス

### サービス統合パターン
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # サービス初期化
        self.config_service = ConfigurationService()
        self.db_manager = DatabaseManager()
        self.worker_service = WorkerService()
        
        # UI設定
        self.setupUi(self)
        self.setup_services()
    
    def setup_services(self):
        """サービス統合設定"""
        # サービス間の連携設定
        pass
```

### 非同期ワーカーパターン
```python
from PySide6.QtCore import QObject, QThread, Signal, Slot

class DatabaseWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int)
    
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
    
    @Slot()
    def process(self):
        """データベース処理実行"""
        try:
            # 重い処理
            result = self.db_manager.process_data()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setup_workers()
    
    def setup_workers(self):
        """ワーカースレッド設定"""
        self.worker = DatabaseWorker(self.db_manager)
        self.worker_thread = QThread()
        
        self.worker.moveToThread(self.worker_thread)
        
        # シグナル接続
        self.worker.finished.connect(self.handle_result)
        self.worker.error.connect(self.handle_error)
        
        self.worker_thread.start()
    
    @Slot(object)  
    def handle_result(self, result):
        """処理結果ハンドリング"""
        pass
    
    @Slot(str)
    def handle_error(self, error_message):
        """エラーハンドリング"""
        pass
```

---

この包括的なガイドにより、PySide6を使用したGUIアプリケーション開発における多くの問題を解決し、実用的なアプリケーション開発が可能になります。Context7から取得した実世界での実装例も含めて、実践的な開発に活用できる内容となっています。