#!/usr/bin/env python3
"""
LoRAIro テストコードベース分析スクリプト
tests/ ディレクトリの構造・重複・品質を分析
"""

import json
import subprocess
from pathlib import Path
from collections import defaultdict
import re

def count_lines(file_path):
    """ファイルの行数をカウント"""
    try:
        with open(file_path) as f:
            return len(f.readlines())
    except Exception:
        return 0

def extract_test_names(file_path):
    """テストファイルからテスト関数名を抽出"""
    tests = []
    try:
        with open(file_path) as f:
            content = f.read()
            # test_* 関数を抽出
            pattern = r'def (test_\w+)\('
            tests = re.findall(pattern, content)
    except Exception:
        pass
    return tests

def analyze_directory_structure():
    """ディレクトリ構造を分析"""
    test_root = Path("/workspaces/LoRAIro/tests")

    stats = {
        "total_test_files": 0,
        "total_tests": 0,
        "total_lines": 0,
        "by_directory": {},
        "test_names": defaultdict(list),
    }

    # conftest.py の確認
    conftest_files = list(test_root.rglob("conftest.py"))
    stats["conftest_locations"] = [str(f.relative_to(test_root)) for f in conftest_files]

    # テストファイル一覧
    test_files = list(test_root.rglob("test_*.py"))
    stats["total_test_files"] = len(test_files)

    for test_file in test_files:
        rel_path = test_file.relative_to(test_root)
        directory = str(rel_path.parent)

        if directory not in stats["by_directory"]:
            stats["by_directory"][directory] = {
                "files": 0,
                "tests": 0,
                "lines": 0,
                "test_list": [],
            }

        lines = count_lines(test_file)
        tests = extract_test_names(test_file)

        stats["by_directory"][directory]["files"] += 1
        stats["by_directory"][directory]["tests"] += len(tests)
        stats["by_directory"][directory]["lines"] += lines
        stats["by_directory"][directory]["test_list"].append({
            "file": str(rel_path),
            "test_count": len(tests),
            "lines": lines,
            "tests": tests,
        })

        stats["total_tests"] += len(tests)
        stats["total_lines"] += lines

        # テスト名を記録（重複検出用）
        for test_name in tests:
            stats["test_names"][test_name].append(str(rel_path))

    return stats

def detect_duplicates(stats):
    """重複テストを検出"""
    duplicates = []

    # 同じ名前のテストが複数箇所に存在する場合
    for test_name, locations in stats["test_names"].items():
        if len(locations) > 1:
            duplicates.append({
                "test_name": test_name,
                "locations": locations,
                "type": "same_name",
            })

    return duplicates

def analyze_fixtures(conftest_files):
    """フィクスチャを分析"""
    fixtures = {}

    for conftest_file in conftest_files:
        try:
            with open(conftest_file) as f:
                content = f.read()
                # @pytest.fixture デコレータを検出
                pattern = r'@pytest\.fixture.*?\ndef (\w+)\('
                fixture_names = re.findall(pattern, content, re.DOTALL)
                fixtures[str(conftest_file)] = fixture_names
        except Exception:
            pass

    return fixtures

def run_pytest_collection():
    """pytest で全テストを列挙"""
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "--collect-only", "-q"],
            cwd="/workspaces/LoRAIro",
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error collecting tests: {e}"

def main():
    print("=" * 80)
    print("LoRAIro テストコードベース分析")
    print("=" * 80)

    # 構造分析
    print("\n📊 ディレクトリ構造分析中...")
    stats = analyze_directory_structure()

    # 重複検出
    print("🔍 重複テスト検出中...")
    duplicates = detect_duplicates(stats)

    # フィクスチャ分析
    print("📍 フィクスチャ分析中...")
    conftest_files = [Path(p) for p in stats["conftest_locations"]]
    fixtures = analyze_fixtures(conftest_files)

    # pytest 実行
    print("⚡ pytest テスト列挙中...")
    pytest_output = run_pytest_collection()

    # 結果出力
    print("\n" + "=" * 80)
    print("分析結果")
    print("=" * 80)

    print(f"\n📊 統計情報:")
    print(f"  総テストファイル数: {stats['total_test_files']}")
    print(f"  総テスト数: {stats['total_tests']}")
    print(f"  総行数: {stats['total_lines']}")
    print(f"  conftest.py 数: {len(conftest_files)}")

    print(f"\n📂 ディレクトリ別詳細:")
    for directory, dir_stats in sorted(stats["by_directory"].items()):
        print(f"\n  {directory}/")
        print(f"    ファイル数: {dir_stats['files']}")
        print(f"    テスト数: {dir_stats['tests']}")
        print(f"    総行数: {dir_stats['lines']}")
        for test_file_info in dir_stats["test_list"]:
            print(f"      - {test_file_info['file']}: {test_file_info['test_count']}件")

    if duplicates:
        print(f"\n⚠️  重複テスト検出: {len(duplicates)}件")
        for dup in duplicates[:10]:
            print(f"    - {dup['test_name']}: {len(dup['locations'])}箇所")
            for loc in dup['locations']:
                print(f"      - {loc}")

    if fixtures:
        print(f"\n🔧 フィクスチャ定義:")
        for conftest, fixture_list in fixtures.items():
            if fixture_list:
                print(f"  {conftest}:")
                for fixture in fixture_list:
                    print(f"    - {fixture}")

    print(f"\n📊 pytest 列挙結果（先頭20行）:")
    for line in pytest_output.split('\n')[:20]:
        if line.strip():
            print(f"  {line}")

    # JSON 出力
    output_file = Path("/workspaces/LoRAIro/.serena/memories/test_analysis_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    analysis_data = {
        "stats": stats,
        "duplicates": duplicates,
        "fixtures": fixtures,
        "pytest_collection": pytest_output[:1000],  # 先頭1000文字
    }

    with open(output_file, 'w') as f:
        json.dump(analysis_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 分析結果を保存しました: {output_file}")

if __name__ == "__main__":
    main()
