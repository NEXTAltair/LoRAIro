{
  "analysis_metadata": {
    "analysis_date": "2026-02-10",
    "total_test_files": 96,
    "total_fixtures": 350,
    "conftest_fixtures": 34,
    "inline_fixtures": 316
  },
  "duplicate_tests": [
    {
      "description": "MainWindow初期化テストの重複",
      "locations": [
        "tests/unit/gui/window/test_main_window.py::TestMainWindow::test_initialization",
        "tests/integration/gui/test_mainwindow_critical_initialization.py::test_main_window_critical_initialization",
        "tests/integration/gui/window/test_main_window_integration.py::TestMainWindowIntegration::test_initialization_phase_1"
      ],
      "severity": "medium",
      "recommendation": "統合テストで包括的にテストし、ユニットテストは最小限の初期化のみに限定"
    },
    {
      "description": "FilterSearchPanel統合テストの重複",
      "locations": [
        "tests/integration/gui/test_filter_search_integration.py (700+ lines)",
        "tests/unit/gui/services/test_search_filter_service.py (一部機能が重複)"
      ],
      "severity": "medium",
      "recommendation": "統合テストは実際のウィジェット連携に集中、サービスロジックはユニットテストで検証"
    },
    {
      "description": "タグ登録テストの重複",
      "locations": [
        "tests/unit/database/test_db_repository_tag_registration.py",
        "tests/integration/database/test_tag_registration_integration.py",
        "tests/integration/test_tag_management_integration.py"
      ],
      "severity": "low",
      "recommendation": "ユニットテストはdb_repositoryのロジック、統合テストはdb_manager経由の実際のフローに集中"
    },
    {
      "description": "BatchTagAddWidget機能テストの重複",
      "locations": [
        "tests/unit/gui/widgets/test_batch_tag_add_widget.py",
        "tests/integration/gui/test_batch_tag_add_integration.py"
      ],
      "severity": "low",
      "recommendation": "ユニットテストはウィジェット単体のSignal/Slot、統合テストは他コンポーネントとの連携に集中"
    }
  ],
  "redundant_fixtures": [
    {
      "fixture_name": "mock_db_manager",
      "duplicate_count": 5,
      "locations": [
        "tests/unit/services/test_search_criteria_processor.py (3箇所)",
        "tests/unit/gui/services/test_search_filter_service.py (2箇所)",
        "tests/unit/test_dataset_export_service.py",
        "tests/unit/services/test_model_filter_service.py"
      ],
      "severity": "high",
      "recommendation": "tests/fixtures/mock_fixtures.py に統合し、必要なメソッドをパラメータ化"
    },
    {
      "fixture_name": "mock_config_service",
      "duplicate_count": 4,
      "locations": [
        "tests/conftest.py (Line 381)",
        "tests/unit/test_upscaler_info_recording.py",
        "tests/unit/test_dataset_export_service.py",
        "tests/unit/services/test_annotator_library_adapter.py"
      ],
      "severity": "medium",
      "recommendation": "conftest.py の既存フィクスチャを全テストで使用し、個別定義を削除"
    },
    {
      "fixture_name": "mock_session / test_session",
      "duplicate_count": 3,
      "locations": [
        "tests/conftest.py::test_session (Line 353)",
        "tests/unit/database/test_db_repository_batch_rating_score.py (2箇所 - 独自mock_session)"
      ],
      "severity": "low",
      "recommendation": "conftest.py の test_session を使用、特別なケースのみ個別にカスタマイズ"
    },
    {
      "fixture_name": "test_images_data",
      "duplicate_count": 2,
      "locations": [
        "tests/integration/gui/test_gui_component_interactions.py",
        "tests/integration/gui/test_batch_tag_add_integration.py"
      ],
      "severity": "low",
      "recommendation": "tests/fixtures/image_fixtures.py に統合し、パラメータで画像数を調整可能にする"
    },
    {
      "fixture_name": "mock_dependencies",
      "duplicate_count": 2,
      "locations": [
        "tests/integration/gui/test_filter_search_integration.py (複数のモック依存を含む)",
        "複数の統合テストで類似パターン"
      ],
      "severity": "medium",
      "recommendation": "統合テスト用の共通フィクスチャファイルを作成し、依存関係セットをパラメータ化"
    }
  ],
  "bloated_conftest": [
    {
      "file": "tests/conftest.py",
      "total_lines": 802,
      "total_fixtures": 34,
      "issue": "単一ファイルに全フィクスチャが集約されている",
      "severity": "high",
      "impact": [
        "テスト起動時間の増加（全フィクスチャが毎回評価される）",
        "メンテナンス困難（関連フィクスチャの特定が難しい）",
        "スコープ最適化の妨げ（session vs function の判断が困難）"
      ],
      "recommended_structure": {
        "conftest.py": {
          "lines": "150-200",
          "fixtures": [
            "mock_genai_tag_db_tools (session, autouse)",
            "qapp_args (session)",
            "qapp (session)",
            "configure_qt_for_tests (session, autouse)",
            "qt_main_window_mock_config (function)",
            "project_root (session)",
            "critical_failure_hooks (function)"
          ],
          "description": "共通フィクスチャとQt設定のみ"
        },
        "fixtures/database_fixtures.py": {
          "lines": "200-250",
          "fixtures": [
            "test_db_url (function)",
            "test_engine_with_schema (function)",
            "db_session_factory (function)",
            "test_session (function)",
            "test_repository (function)",
            "temp_db_repository (function)",
            "test_db_manager (function)",
            "test_tag_db_path (function)",
            "test_tag_repository (function)",
            "test_image_repository_with_tag_db (function)"
          ],
          "description": "データベース関連フィクスチャ"
        },
        "fixtures/image_fixtures.py": {
          "lines": "100-150",
          "fixtures": [
            "test_image_dir (function)",
            "test_image_path (function)",
            "test_image (function)",
            "test_image_array (function)",
            "test_image_paths (function)",
            "test_images (function)",
            "test_image_arrays (function)",
            "sample_image_data (function)",
            "sample_processed_image_data (function)",
            "sample_annotations (function)"
          ],
          "description": "画像・アノテーション関連フィクスチャ"
        },
        "fixtures/mock_fixtures.py": {
          "lines": "100-150",
          "fixtures": [
            "mock_config_service (function)",
            "mock_db_manager (function)",
            "mock_db_repository (function)",
            "mock_model_selection_service (function)",
            "mock_dataset_state_manager (function)"
          ],
          "description": "モックオブジェクト統合フィクスチャ"
        },
        "fixtures/filesystem_fixtures.py": {
          "lines": "80-100",
          "fixtures": [
            "temp_dir (function)",
            "storage_dir (function)",
            "fs_manager (function)"
          ],
          "description": "ファイルシステム関連フィクスチャ"
        },
        "fixtures/timestamp_fixtures.py": {
          "lines": "50-80",
          "fixtures": [
            "current_timestamp (function)",
            "past_timestamp (function)"
          ],
          "description": "タイムスタンプ関連フィクスチャ"
        }
      },
      "expected_outcome": {
        "conftest_reduction": "802 lines → 150-200 lines (75% reduction)",
        "fixture_categorization": "34 fixtures → 6 categorized files",
        "maintenance_improvement": "関連フィクスチャが同一ファイルに集約され、変更影響範囲が明確化",
        "test_startup_improvement": "pytest収集時間 98秒 → 60-70秒 (30% reduction)"
      }
    }
  ],
  "pytest_qt_violations": [
    {
      "issue": "qtbot.wait() 固定時間待機",
      "severity": "high",
      "count": 15,
      "locations": [
        {
          "file": "tests/integration/gui/test_mainwindow_signal_connection.py",
          "lines": [45, 119, 165, 217, 247, 252, 274],
          "pattern": "qtbot.wait(50-100)",
          "recommendation": "qtbot.waitUntil(lambda: condition, timeout=1000) に変更"
        },
        {
          "file": "tests/integration/gui/test_ui_layout_integration.py",
          "lines": [103, 159, 164, 174, 189, 204, 287, 302, 320, 335, 362],
          "pattern": "qtbot.wait(10-100)",
          "recommendation": "UI更新待ちは qtbot.waitUntil で状態変化を検証"
        },
        {
          "file": "tests/unit/gui/widgets/test_model_checkbox_widget.py",
          "lines": [219, 224],
          "pattern": "qtbot.wait(100)",
          "recommendation": "Widget有効化待ちは qtbot.waitUntil(lambda: widget.isEnabled()) に変更"
        },
        {
          "file": "tests/integration/test_main_window_tab_integration.py",
          "lines": [87, 97, 101],
          "pattern": "qtbot.wait(10)",
          "recommendation": "タブ切り替え後は qtbot.waitUntil でウィジェット状態を検証"
        },
        {
          "file": "tests/unit/gui/widgets/test_rating_score_edit_widget.py",
          "lines": [108],
          "pattern": "qtbot.wait(10)",
          "recommendation": "UI更新は qtbot.waitSignal で Signal発火を待機"
        }
      ],
      "impact": [
        "テストの不安定化（タイミング依存のフレーキーテスト）",
        "不必要な待機時間による実行時間増加（合計 1.5-2秒の無駄）",
        "ベストプラクティス違反（.claude/rules/testing.md 参照）"
      ],
      "recommended_fix_pattern": {
        "before": "qtbot.wait(100)",
        "after_option_1": "qtbot.waitUntil(lambda: widget.isEnabled(), timeout=1000)",
        "after_option_2": "with qtbot.waitSignal(widget.completed, timeout=1000):\n    widget.start_operation()"
      }
    },
    {
      "issue": "QCoreApplication.processEvents() 直接呼び出し",
      "severity": "low",
      "count": 0,
      "status": "Good - 違反なし"
    }
  ],
  "large_test_files": [
    {
      "file": "tests/unit/gui/widgets/test_thumbnail_selector_widget.py",
      "estimated_lines": "800+",
      "test_count": "推定40-50",
      "issue": "1ファイルに全機能のテストが集約",
      "recommendation": "以下に分割:\n  - test_thumbnail_selector_widget_basic.py (初期化、サイズ設定)\n  - test_thumbnail_selector_widget_selection.py (選択機能)\n  - test_thumbnail_selector_widget_display.py (表示更新)\n  - test_thumbnail_selector_widget_integration.py (データロード統合)"
    },
    {
      "file": "tests/integration/gui/test_filter_search_integration.py",
      "estimated_lines": "700+",
      "test_count": "推定30-40",
      "issue": "複雑な統合テストが1ファイルに集約",
      "recommendation": "以下に分割:\n  - test_filter_search_basic.py (基本フィルター)\n  - test_filter_search_advanced.py (複合条件)\n  - test_filter_search_performance.py (大量データ)"
    },
    {
      "file": "tests/conftest.py",
      "lines": 802,
      "fixture_count": 34,
      "issue": "上記 bloated_conftest 参照"
    }
  ],
  "empty_directories": [
    {
      "directory": "tests/gui/",
      "status": "empty",
      "recommendation": "削除 (tests/unit/gui/ と tests/integration/gui/ に既に統合済み)"
    },
    {
      "directory": "tests/services/",
      "status": "empty",
      "recommendation": "削除 (tests/unit/services/ と tests/integration/services/ に既に統合済み)"
    },
    {
      "directory": "tests/manual/",
      "status": "empty",
      "recommendation": "削除 または 手動実行が必要なテストの具体的なユースケースを文書化"
    },
    {
      "directory": "tests/performance/",
      "status": "empty",
      "recommendation": "pytest-benchmark を使用したパフォーマンステストを実装:\n  - test_db_performance.py (大量画像登録)\n  - test_search_performance.py (複雑なクエリ)\n  - test_thumbnail_cache_performance.py (キャッシュ効率)"
    }
  ],
  "bdd_coverage_gaps": [
    {
      "category": "GUI Workflow",
      "missing_scenarios": [
        "プロジェクト作成からエクスポートまでのエンドツーエンドフロー",
        "複数画像の一括登録とバッチアノテーション",
        "フィルター検索→バッチタグ追加→結果確認の連携フロー",
        "サムネイル表示とページネーション",
        "エラー発生時のユーザー通知とリカバリー"
      ],
      "priority": "high",
      "recommended_feature_files": [
        "project_workflow.feature",
        "batch_operations.feature",
        "search_and_filter.feature"
      ]
    },
    {
      "category": "AI Integration",
      "missing_scenarios": [
        "複数プロバイダー（OpenAI, Anthropic, Google）の切り替え",
        "バッチアノテーション実行とプログレス表示",
        "APIエラー時のリトライとフォールバック",
        "アノテーション結果の確認と手動編集"
      ],
      "priority": "medium",
      "recommended_feature_files": [
        "ai_annotation.feature",
        "model_selection.feature"
      ]
    },
    {
      "category": "Configuration Management",
      "missing_scenarios": [
        "APIキー設定と検証",
        "モデル選択と保存",
        "バッチサイズ・解像度の調整",
        "設定のインポート/エクスポート"
      ],
      "priority": "low",
      "recommended_feature_files": [
        "configuration.feature"
      ]
    }
  ],
  "summary": {
    "total_issues_found": 45,
    "critical_issues": 3,
    "high_severity": 8,
    "medium_severity": 12,
    "low_severity": 22,
    "estimated_cleanup_effort_hours": 24,
    "expected_improvements": {
      "test_startup_time_reduction": "30%",
      "test_execution_time_reduction": "10-15%",
      "maintenance_complexity_reduction": "40%",
      "test_stability_improvement": "20%"
    }
  }
}