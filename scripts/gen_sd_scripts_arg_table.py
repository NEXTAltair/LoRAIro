"""sd-scripts の引数表 (src/lorairo/services/sd_scripts_arg_table.py) を生成する開発用スクリプト。

sd-scripts を ``git fetch --depth 1 origin <commit>`` で取得したディレクトリを ``ast`` で読むだけで、
sd-scripts のコードは実行も import もしない。

使い方:
    python scripts/gen_sd_scripts_arg_table.py <sd-scripts dir> <commit> <生成日>
"""

import ast
import sys
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "src/lorairo/services/sd_scripts_arg_table.py"
TARGET_FILES = ("train_network.py", "sdxl_train_network.py")
TYPE_NAMES = {"int": "int", "float": "float", "str": "str"}
BOOL_ACTIONS = {"store_true", "store_false"}


def _classify(call: ast.Call) -> str:
    """add_argument 呼び出しから引数の型名 (int / float / str / bool) を判定する。"""
    for keyword in call.keywords:
        if keyword.arg == "type" and isinstance(keyword.value, ast.Name):
            return TYPE_NAMES.get(keyword.value.id, "str")
    for keyword in call.keywords:
        if (
            keyword.arg == "action"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value in BOOL_ACTIONS
        ):
            return "bool"
    return "str"


def _arg_name(call: ast.Call) -> str | None:
    """最初の ``--xxx`` 文字列定数を ``xxx`` (ハイフンはアンダースコア) で返す。"""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--"):
            return arg.value[2:].replace("-", "_")
    return None


def collect_arg_types(source_files: list[Path]) -> dict[str, str]:
    """ファイル群から引数名と型の表を集める。同名は最初に見つけたものを採用する。"""
    table: dict[str, str] = {}
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                continue
            name = _arg_name(node)
            if name is not None:
                table.setdefault(name, _classify(node))
    return dict(sorted(table.items()))


def render(table: dict[str, str], commit: str, date: str) -> str:
    """生成物のソース文字列を作る。Ruff (行長 108) を通る形で出力する。"""
    lines = [
        f"# sd-scripts (kohya-ss/sd-scripts) コミット {commit} から生成 (生成日 {date})。",
        "# scripts/gen_sd_scripts_arg_table.py で生成した。手で編集しない。",
        '"""sd-scripts の学習引数名と型の表。"""',
        "",
        "SD_SCRIPTS_ARG_TYPES: dict[str, str] = {",
    ]
    lines.extend(f'    "{name}": "{type_name}",' for name, type_name in table.items())
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    """エントリポイント。"""
    if len(argv) != 4:
        print(__doc__)
        return 2
    root = Path(argv[1])
    files = sorted((root / "library").glob("*.py")) + [root / name for name in TARGET_FILES]
    table = collect_arg_types(files)
    OUTPUT_PATH.write_text(render(table, argv[2], argv[3]), encoding="utf-8")
    print(f"{len(table)} 件を {OUTPUT_PATH} に書き出した")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
