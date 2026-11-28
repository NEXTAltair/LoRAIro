"""CLI のヘルプ・出力に共通で載せる案内文 (Issue #1662)。

プロジェクト作成 (``project create``)、既存プロジェクトへの版追加 (``dataset import``)、
画像登録 (``images register``) の違いを、複数コマンドで同じ文言で案内するための定数と関数。
挙動は変えず、案内だけを提供する。
"""

# ``--project`` / ``-p`` の help。全コマンドで同じ意味 (メタデータの name) を示す。
PROJECT_OPTION_HELP = (
    "Project name: the `name` in the project's .lorairo-project metadata, not a folder path. "
    "A GUI-created project uses its folder name; a CLI-created one uses the name given to "
    "`project create`. Run `lorairo-cli project list` to see the names."
)


def project_created_next_steps(project: str) -> str:
    """``project create`` 直後に出す、次の操作の案内。

    Args:
        project: 作成したプロジェクト名。

    Returns:
        画像登録と版追加 (``dataset import``) の違いを示す案内文。
    """
    return (
        f"Next: `lorairo-cli dataset import <dir> -p {project} --dataset <dataset name>` imports a "
        f"Kohya-ss dataset as a version; `lorairo-cli images register <dir> -p {project}` only adds "
        "images and creates no version. Later versions go to this same project (do not create one "
        "project per version)."
    )


def images_register_no_version_note(project: str) -> str:
    """``images register`` の結果に添える、版が作られないことの案内。

    Args:
        project: 画像を登録したプロジェクト名。

    Returns:
        版が作られないことと、版にする方法を示す案内文。
    """
    return (
        "No dataset version was created: images register only adds images to the project. "
        f"To make a version, run `lorairo-cli dataset import <dir> -p {project} --dataset <dataset name>`."
    )
