#!/usr/bin/env python3
"""Phase 4: プロダクション統合テスト

実ライブラリとLoRAIroの完全統合をテストする検証スクリプト
"""

import tempfile
from pathlib import Path

from PIL import Image

from src.lorairo.services.service_container import get_service_container


def create_test_image() -> Path:
    """テスト用画像作成"""
    # 簡単なRGB画像を作成
    image = Image.new("RGB", (300, 300), color="red")
    
    # 一時ファイルに保存
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    image.save(temp_file.name)
    
    return Path(temp_file.name)


def test_production_integration():
    """Phase 4: プロダクション統合テスト"""
    print("=" * 60)
    print("Phase 4: プロダクション統合テスト開始")
    print("=" * 60)
    
    # ServiceContainer取得
    container = get_service_container()
    
    print(f"1. ServiceContainer動作モード: {'プロダクション' if container.is_production_mode() else 'Mock'}")
    print(f"   コンテナ情報: {container.get_service_summary()}")
    print()
    
    # モデル同期テスト
    print("2. モデル同期テスト")
    try:
        model_sync_service = container.model_sync_service
        sync_result = model_sync_service.sync_available_models()
        
        print(f"   同期結果: {sync_result.summary}")
        print(f"   成功: {sync_result.success}")
        if sync_result.errors:
            print(f"   エラー: {sync_result.errors}")
    except Exception as e:
        print(f"   モデル同期エラー: {e}")
    print()
    
    # 利用可能モデル取得テスト
    print("3. 利用可能モデル取得テスト")
    try:
        adapter = container.annotator_lib_adapter
        adapter_type = type(adapter).__name__
        print(f"   使用アダプター: {adapter_type}")
        
        models = adapter.get_available_models_with_metadata()
        print(f"   利用可能モデル数: {len(models)}")
        
        # 最初の3モデルを表示
        for i, model_info in enumerate(models[:3]):
            model_name = model_info.get('name', 'unknown')
            provider = model_info.get('provider', 'unknown')
            model_type = model_info.get('model_type', 'unknown')
            print(f"   [{i+1}] {model_name}: {provider} ({model_type})")
    except Exception as e:
        print(f"   モデル取得エラー: {e}")
    print()
    
    # 単発アノテーションテスト
    print("4. 単発アノテーションテスト")
    test_image_path = None
    try:
        # テスト画像作成
        test_image_path = create_test_image()
        print(f"   テスト画像作成: {test_image_path}")
        
        # 画像読み込み
        test_image = Image.open(test_image_path)
        
        # アノテーション実行（小さなモデルセットでテスト）
        test_models = ["gpt-4o"]  # テスト用に1モデルのみ
        
        adapter = container.annotator_lib_adapter
        results = adapter.call_annotate(
            images=[test_image], 
            models=test_models,
            phash_list=["test_hash_001"]
        )
        
        print(f"   アノテーション結果取得: {len(results)}件")
        for phash, model_results in results.items():
            for model_name, result in model_results.items():
                if result.get("error"):
                    print(f"   [{phash}][{model_name}] エラー: {result['error']}")
                else:
                    print(f"   [{phash}][{model_name}] 成功")
                    if "formatted_output" in result and result["formatted_output"]:
                        formatted = result["formatted_output"]
                        if isinstance(formatted, dict):
                            # キャプション表示
                            if "captions" in formatted and formatted["captions"]:
                                caption = formatted["captions"][0][:100] + "..." if len(formatted["captions"][0]) > 100 else formatted["captions"][0]
                                print(f"       Caption: {caption}")
                            # タグ表示
                            if "tags" in formatted and formatted["tags"]:
                                tags = ", ".join(formatted["tags"][:5])
                                print(f"       Tags: {tags}")
                        
    except Exception as e:
        print(f"   アノテーションテストエラー: {e}")
    finally:
        # テスト画像削除
        if test_image_path and test_image_path.exists():
            test_image_path.unlink()
            print(f"   テスト画像削除: {test_image_path}")
    print()
    
    # サービス状況確認
    print("5. サービス状況確認")
    try:
        from src.lorairo.services.enhanced_annotation_service import EnhancedAnnotationService
        
        annotation_service = EnhancedAnnotationService()
        service_status = annotation_service.get_service_status()
        
        print(f"   {service_status['service_name']}: {service_status['phase']}")
        print(f"   コンテナサマリー: {service_status['container_summary']['phase']}")
        
        initialized_services = service_status['container_summary']['initialized_services']
        initialized_count = sum(1 for v in initialized_services.values() if v)
        total_services = len(initialized_services)
        print(f"   初期化済みサービス: {initialized_count}/{total_services}")
        
    except Exception as e:
        print(f"   サービス状況確認エラー: {e}")
    
    print()
    print("=" * 60)
    print("Phase 4: プロダクション統合テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    test_production_integration()