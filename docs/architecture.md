# LoRAIro Architecture Documentation

## System Overview

LoRAIro is an AI-powered image annotation and dataset management application built with a clean 3-layer architecture designed for machine learning dataset preparation. The system processes images through multiple AI providers and provides quality assessment tools for training data curation.

## Architectural Principles

### Clean Architecture
The application follows clean architecture principles with clear separation of concerns:

- **Presentation Layer**: PySide6-based GUI components
- **Application Layer**: Business logic services and use cases
- **Domain Layer**: Core business entities and rules
- **Infrastructure Layer**: Database, file system, and external APIs

### Dependency Injection
Services are injected into components to maintain loose coupling and enable testability.

### Configuration-Driven Development
All system behavior is configurable through TOML files, enabling easy customization without code changes.

### Event-Driven Architecture
Components communicate through Qt signals/slots for loose coupling and responsive UI.

## System Components

### Core Application Flow

```mermaid
graph TD
    A[main.py] --> B[MainWindow]
    B --> C[ImageProcessingService]
    B --> D[AnnotationService]
    B --> E[ConfigurationService]
    C --> F[FileSystemManager]
    D --> G[AI Providers]
    D --> H[DatabaseManager]
    E --> I[Config Files]
```

#### Entry Point
- **`src/lorairo/main.py`**: Application initialization
  - Sets up Qt application
  - Configures logging
  - Initializes service dependencies
  - Launches main window

#### Main Window Controller
- **`src/lorairo/gui/window/main_window.py`**: Primary GUI orchestrator
  - Coordinates between widgets
  - Manages application state
  - Handles user interactions
  - Displays notifications and progress

### Service Layer Architecture

The service layer encapsulates business logic and provides clean interfaces for the GUI layer.

```mermaid
graph LR
    A[GUI Components] --> B[Service Layer]
    B --> C[Repository Layer]
    B --> D[External APIs]
    C --> E[Database]
    D --> F[AI Providers]
```

#### Core Services

**ImageProcessingService**
- Image loading and validation
- Format conversion (JPEG, PNG, WebP)
- Resizing and quality optimization
- Batch processing coordination
- Metadata extraction

**AnnotationService**
- AI provider coordination
- Caption and tag generation
- Quality scoring integration
- Batch annotation processing
- Result aggregation and storage

**ConfigurationService**
- TOML configuration management
- Environment variable integration
- Runtime configuration updates
- Validation and defaults

### Data Layer Architecture

The data layer provides persistent storage and manages image metadata.

```mermaid
graph TD
    A[DatabaseManager] --> B[Repository Pattern]
    B --> C[SQLAlchemy ORM]
    C --> D[SQLite Database]
    E[Alembic] --> D
    F[Schema Models] --> C
```

#### Database Components

**DatabaseManager** (`src/lorairo/database/db_manager.py`)
- Connection management
- Transaction coordination
- Session lifecycle
- Migration management

**Repository Layer** (`src/lorairo/database/db_repository.py`)
- Data access abstraction
- Query optimization
- Business logic isolation
- Transaction boundaries

**Schema Models** (`src/lorairo/database/schema.py`)
- Entity definitions
- Relationship mapping
- Validation rules
- Database constraints

### GUI Architecture

The GUI follows the Model-View-Controller pattern with PySide6 components.

```mermaid
graph TD
    A[MainWindow] --> B[Widget Controllers]
    B --> C[Designer UI Files]
    B --> D[Custom Widgets]
    C --> E[Qt Layouts]
    D --> F[Business Logic]
    F --> G[Services]
```

#### GUI Components

**Designer Integration**
- **`src/lorairo/gui/designer/`**: Auto-generated UI classes
- **`.ui` files**: Qt Designer interface definitions
- **`*_ui.py` files**: Compiled Python UI classes

**Widget Controllers**
- **`src/lorairo/gui/widgets/`**: Custom widget implementations
- Business logic integration
- Signal/slot connections
- Data binding and validation

**Window Controllers**
- **`src/lorairo/gui/window/`**: Window-level orchestration
- Multi-widget coordination
- Application state management
- User workflow control

### AI Integration Architecture

The system supports multiple AI providers through a unified interface.

```mermaid
graph TD
    A[AnnotationService] --> B[Provider Factory]
    B --> C[OpenAI Provider]
    B --> D[Anthropic Provider]
    B --> E[Google Provider]
    F[Local Models] --> G[image-annotator-lib]
    A --> F
```

#### AI Provider Integration

**Multi-Provider Support**
- OpenAI GPT-4 Vision
- Anthropic Claude
- Google Gemini
- Local ML models via image-annotator-lib

**Provider Abstraction**
- Unified annotation interface
- Provider-specific configuration
- Error handling and retry logic
- Rate limiting and quota management

**Local Model Integration**
- CLIP-based aesthetic scoring
- DeepDanbooru tagging
- ONNX and TensorFlow models
- GPU acceleration support

### Storage Architecture

File system management handles image storage and organization.

```mermaid
graph TD
    A[FileSystemManager] --> B[Image Storage]
    A --> C[Metadata Files]
    A --> D[Cache Management]
    B --> E[Directory Organization]
    C --> F[.txt/.caption Files]
    D --> G[Temporary Files]
```

#### Storage Components

**FileSystemManager** (`src/lorairo/storage/file_system.py`)
- Directory management
- File organization patterns
- Metadata file coordination
- Cleanup and maintenance

**File Organization**
- Images with associated metadata files
- Directory-based categorization
- Atomic file operations
- Backup and recovery support

## Local Package Integration

### Submodule Architecture

The project leverages two local packages as Git submodules managed through uv:

```mermaid
graph TD
    A[LoRAIro Main] --> B[genai-tag-db-tools]
    A --> C[image-annotator-lib]
    B --> D[Tag Database Management]
    C --> E[AI Annotation Core]
    C --> F[Local ML Models]
```

#### genai-tag-db-tools
- **Purpose**: Tag database management utilities
- **Integration**: CLI tool (`tag-db` command)
- **Location**: `local_packages/genai-tag-db-tools/`
- **Features**: Tag taxonomy management, database operations

#### image-annotator-lib
- **Purpose**: Core image annotation functionality
- **Integration**: Python library import
- **Location**: `local_packages/image-annotator-lib/`
- **Features**: Multi-provider AI annotation, local model support

### Dependency Management

**uv Integration**
- Packages linked via `uv.sources` in `pyproject.toml`
- Editable installs for development
- Automatic dependency resolution
- Version pinning and updates

## Configuration Architecture

### Hierarchical Configuration

```mermaid
graph TD
    A[Configuration System] --> B[System Defaults]
    A --> C[User Configuration]
    A --> D[Environment Variables]
    B --> E[config/lorairo.toml]
    C --> F[User Overrides]
    D --> G[Runtime Settings]
```

#### Configuration Layers

**System Configuration** (`config/lorairo.toml`)
- Application defaults
- AI provider settings
- Database configuration
- Logging setup

**Environment Integration**
- API key management
- Development/production flags
- Debug configuration
- Path overrides

**Runtime Configuration**
- User preference persistence
- Session state management
- Dynamic setting updates
- Validation and defaults

## Security Architecture

### Data Protection

**API Key Management**
- Environment variable storage
- Secure configuration handling
- No credential logging
- Provider-specific security

**File System Security**
- Proper file permissions
- Temporary file cleanup
- Path validation
- Directory traversal prevention

### Error Handling

**Comprehensive Error Management**
- Structured error types
- User-friendly messages
- Detailed logging for debugging
- Graceful degradation strategies

## Performance Architecture

### Memory Management

**Image Processing Optimization**
- Lazy loading strategies
- Memory-efficient processing
- Garbage collection optimization
- Resource cleanup automation

**Database Performance**
- Connection pooling
- Query optimization
- Index management
- Batch operations

### Scalability Considerations

**Batch Processing**
- Parallel image processing
- Queue management
- Progress tracking
- Error recovery

**Resource Management**
- Memory usage monitoring
- CPU utilization optimization
- I/O operation efficiency
- Network request optimization

## Testing Architecture

### Test Strategy

```mermaid
graph TD
    A[Test Suite] --> B[Unit Tests]
    A --> C[Integration Tests]
    A --> D[GUI Tests]
    B --> E[Service Testing]
    B --> F[Repository Testing]
    C --> G[Database Integration]
    C --> H[AI Provider Integration]
    D --> I[Widget Testing]
    D --> J[Workflow Testing]
```

#### Test Categories

**Unit Tests** (`pytest -m unit`)
- Service layer testing
- Business logic validation
- Mock-based isolation
- Fast execution

**Integration Tests** (`pytest -m integration`)
- Database operations
- File system interactions
- Service coordination
- End-to-end workflows

**GUI Tests** (`pytest -m gui`)
- Widget functionality
- User interaction simulation
- Visual component testing
- Accessibility validation

## Deployment Architecture

### Development Environment

**Local Development**
- uv virtual environment
- Local SQLite database
- File-based configuration
- Debug logging enabled

### Package Management

**Dependencies**
- Core dependencies in `pyproject.toml`
- Development tools separation
- Local package integration
- Version pinning strategy

## Future Architecture Considerations

### Extensibility Points

**Plugin Architecture**
- AI provider plugins
- Processing pipeline extensions
- Custom widget plugins
- Export format plugins

**Microservice Potential**
- Annotation service separation
- API-based communication
- Horizontal scaling capability
- Cloud deployment options

### Technology Evolution

**Framework Updates**
- PySide6 version management
- Python version compatibility
- Dependency update strategy
- Migration planning

## Sequence Diagrams

The following sequence diagrams illustrate the detailed interactions between components during key application workflows.

### Application Startup Flow

```mermaid
sequenceDiagram
    participant User
    participant Main as main.py
    participant Config as ConfigurationService
    participant Log as Logger
    participant App as QApplication
    participant MW as MainWindow
    participant UI as Ui_MainWindow

    User->>+Main: アプリケーション起動
    Main->>+Config: get_config()
    Config-->>-Main: 設定情報
    Main->>+Log: initialize_logging(config)
    Log-->>-Main: ログ初期化完了
    Main->>+App: QApplication([])
    App-->>-Main: アプリインスタンス
    Main->>+MW: MainWindow()
    MW->>+UI: setupUi(self)
    UI-->>-MW: UI初期化完了
    MW-->>-Main: ウィンドウインスタンス
    Main->>MW: show()
    Main->>App: exec()
    App-->>-User: アプリケーション表示
```

### MainWindow Initialization Flow

```mermaid
sequenceDiagram
    participant MW as MainWindow
    participant CS as ConfigurationService
    participant IR as ImageRepository
    participant IDM as ImageDatabaseManager
    participant FSM as FileSystemManager
    participant ITR as ImageTextFileReader
    participant IPS as ImageProcessingService
    participant PW as ProgressWidget
    participant PC as ProgressController

    MW->>+CS: ConfigurationService()
    CS-->>-MW: 設定サービス
    MW->>MW: setupUi(self)

    Note over MW: init_managers()
    MW->>+IR: ImageRepository(DefaultSessionLocal)
    IR-->>-MW: リポジトリインスタンス
    MW->>+IDM: ImageDatabaseManager(image_repo)
    IDM-->>-MW: DBマネージャー
    MW->>+FSM: FileSystemManager()
    FSM-->>-MW: ファイルシステムマネージャー
    MW->>+ITR: ImageTextFileReader(idm)
    ITR-->>-MW: テキストリーダー
    MW->>+IPS: ImageProcessingService(config, fsm, idm)
    IPS-->>-MW: 画像処理サービス
    MW->>+PW: ProgressWidget()
    PW-->>-MW: プログレスウィジェット
    MW->>+PC: Controller(progress_widget)
    PC-->>-MW: プログレスコントローラー

    Note over MW: init_pages()
    MW->>MW: 各ページ初期化
    MW->>MW: connect_signals()
    MW->>MW: init_dataset_selector()
    MW->>MW: init_statusbar()
```

### Image Processing Flow

```mermaid
sequenceDiagram
    participant User
    participant MW as MainWindow
    participant PC as ProgressController
    participant IPS as ImageProcessingService
    participant IPM as ImageProcessingManager
    participant IDM as ImageDatabaseManager
    participant FSM as FileSystemManager

    User->>+MW: 画像処理開始
    MW->>+PC: start_process(process_function, args)
    PC->>+IPS: process_images_in_list(image_paths, callbacks)

    loop 各画像に対して
        IPS->>+IDM: detect_duplicate_image(image_file)
        IDM-->>-IPS: image_id or None

        alt 画像が未登録の場合
            IPS->>+IDM: register_original_image(image_file, fsm)
            IDM->>+FSM: get_image_info(image_file)
            FSM-->>-IDM: メタデータ
            IDM-->>-IPS: (image_id, metadata)
        else 画像が登録済みの場合
            IPS->>+IDM: get_image_metadata(image_id)
            IDM-->>-IPS: メタデータ
        end

        IPS->>+IDM: check_processed_image_exists(image_id, resolution)
        IDM-->>-IPS: 処理済み画像の存在確認

        alt 処理済み画像が存在しない場合
            IPS->>+IPM: process_image(file, has_alpha, mode, upscaler)
            IPM-->>-IPS: 処理済み画像
            IPS->>+FSM: save_processed_image(image, file)
            FSM-->>-IPS: 保存パス
            IPS->>+IDM: register_processed_image(id, path, metadata)
            IDM-->>-IPS: 登録完了
        end

        IPS->>MW: progress_callback(progress)
        IPS->>MW: status_callback(status)
    end

    IPS-->>-PC: 処理完了
    PC-->>-MW: 完了通知
    MW-->>-User: 処理完了表示
```

### AI Annotation Processing Flow

```mermaid
sequenceDiagram
    participant User
    participant IT as ImageTaggerWidget
    participant AS as AnnotationService
    participant AW as AnnotationWorker
    participant Thread as QThread
    participant AI as AI Annotator

    User->>+IT: アノテーション開始
    IT->>+AS: start_annotation(images, phash_list, models)
    AS->>AS: 入力検証
    AS->>+Thread: QThread()
    Thread-->>-AS: スレッドインスタンス
    AS->>+AW: AnnotationWorker(images, phash, models)
    AW-->>-AS: ワーカーインスタンス
    AS->>AW: moveToThread(thread)
    AS->>Thread: シグナル接続
    AS->>Thread: start()

    Thread->>+AW: run()
    AW->>+AW: run_task()
    AW->>+AI: call_annotate_library(images, models, phash)

    loop 各画像・各モデルに対して
        AI->>AI: AIモデル呼び出し
        AI->>AI: アノテーション生成
    end

    AI-->>-AW: アノテーション結果
    AW-->>-AW: run_task完了
    AW->>AS: finished(results)
    AW-->>-Thread: 処理完了

    AS->>+IT: annotationFinished(results)
    IT->>IT: 結果処理・UI更新
    IT-->>-User: アノテーション結果表示

    Thread->>Thread: quit()
    Thread->>AW: deleteLater()
    Thread->>Thread: deleteLater()
```

### Database Operation Flow

```mermaid
sequenceDiagram
    participant Service as Service Layer
    participant IDM as ImageDatabaseManager
    participant IR as ImageRepository
    participant Session as DB Session
    participant Schema as Database

    Service->>+IDM: データ操作要求
    IDM->>+IR: リポジトリメソッド呼び出し
    IR->>+Session: session_factory()
    Session-->>-IR: セッションインスタンス
    IR->>+Schema: SQLクエリ実行
    Schema-->>-IR: クエリ結果
    IR->>Session: commit() or rollback()
    IR-->>-IDM: 処理結果
    IDM-->>-Service: 結果返却
```

### Configuration Management Flow

```mermaid
sequenceDiagram
    participant User
    participant ConfigWidget as 設定画面
    participant CS as ConfigurationService
    participant File as config/lorairo.toml

    User->>+ConfigWidget: 設定変更
    ConfigWidget->>+CS: update_setting(section, key, value)
    CS->>CS: 設定値検証
    CS->>+File: TOML書き込み
    File-->>-CS: 保存完了
    CS-->>-ConfigWidget: 更新完了
    ConfigWidget->>ConfigWidget: UI更新
    ConfigWidget-->>-User: 設定変更完了表示
```

This architecture provides a solid foundation for the LoRAIro application while maintaining flexibility for future enhancements and scaling requirements.
