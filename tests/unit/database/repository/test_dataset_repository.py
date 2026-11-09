"""`DatasetRepository` の単体テスト (Issue #1413)。

FK 制約を有効にした既存の接続設定 (`create_db_engine`) で、版・フォルダ・学習テキスト・
学習設定の永続化と、同名衝突時に中途半端な行が残らないことを検証する。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_core import create_db_engine
from lorairo.database.repository.dataset import (
    DatasetConflictError,
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
    TrainingConfigSpec,
)
from lorairo.database.schema import (
    KOHYA_DATASET_LITELLM_ID,
    MANUAL_EDIT_LITELLM_ID,
    Base,
    DatasetFolder,
    DatasetFolderImage,
    DatasetLearningText,
    Image,
    Model,
    Tag,
)
from lorairo.services.dataset_version_diff import ChangeStatus, DatasetVersionDiffService

pytestmark = pytest.mark.unit


@pytest.fixture
def fk_engine(tmp_path: Path) -> Iterator[Engine]:
    """`PRAGMA foreign_keys=ON` を設定する既存の接続設定で作ったエンジン。"""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'dataset_repo.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(fk_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=fk_engine)


@pytest.fixture
def repo(session_factory: Callable[[], Session]) -> DatasetRepository:
    return DatasetRepository(session_factory=session_factory)


def _insert_image(session_factory: Callable[[], Session], uuid: str = "img-1") -> int:
    """テスト用画像を 1 件作成して id を返す。"""
    with session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=f"/tmp/{uuid}.png",
            stored_image_path=f"/tmp/{uuid}.png",
            width=512,
            height=512,
            format="PNG",
            extension=".png",
            filename=f"{uuid}.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


def _folder(dir_name: str = "10_kariginu", position: int = 0) -> FolderSpec:
    name = dir_name.split("_", 1)[1]
    return FolderSpec(
        dir_name=dir_name, name=name, num_repeats=10, trigger_word="Kariginu", position=position
    )


def _text(raw_text: str) -> LearningTextSpec:
    return LearningTextSpec(extension=".txt", raw_text=raw_text, elements=raw_text.split(", "))


def _count(session_factory: Callable[[], Session], model: type[Base]) -> int:
    with session_factory() as session:
        count: int = session.execute(select(func.count()).select_from(model)).scalar_one()
    return count


def test_ensure_dataset_returns_same_id_for_same_name(repo: DatasetRepository) -> None:
    first = repo.ensure_dataset("kariginu", "狩衣")
    second = repo.ensure_dataset("kariginu")

    assert first == second


def test_same_image_in_two_folders_keeps_separate_texts(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")

    repo.add_folder(
        version_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    repo.add_folder(
        version_id,
        _folder("5_style", 1),
        [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("(style:1.2), long_sleeves")])],
    )

    snapshot = repo.get_version_snapshot(version_id)
    raw_texts = [folder.images[0].texts[0].raw_text for folder in snapshot.folders]

    assert snapshot.dataset_name == "kariginu"
    assert snapshot.version_name == "v01"
    assert [folder.dir_name for folder in snapshot.folders] == ["10_kariginu", "5_style"]
    assert raw_texts == ["Kariginu, 1girl", "(style:1.2), long_sleeves"]
    assert snapshot.folders[1].images[0].texts[0].elements == ["(style:1.2)", "long_sleeves"]
    # 画像直下のタグには書かない
    assert _count(session_factory, Tag) == 0


def test_create_version_with_same_name_raises_conflict(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    repo.create_version(dataset_id, "v01")

    with pytest.raises(DatasetConflictError):
        repo.create_version(dataset_id, "v01")


def test_add_folder_with_same_dir_name_raises_conflict(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    images = [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("a")])]
    repo.add_folder(version_id, _folder(), images)

    with pytest.raises(DatasetConflictError):
        repo.add_folder(version_id, _folder(), images)

    assert _count(session_factory, DatasetFolder) == 1
    assert _count(session_factory, DatasetFolderImage) == 1
    assert _count(session_factory, DatasetLearningText) == 1


def test_add_folder_is_atomic(repo: DatasetRepository, session_factory: Callable[[], Session]) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    images = [
        FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("Kariginu")]),
        # 存在しない image_id (FK 違反)
        FolderImageSpec(image_id=image_id + 999, file_stem="b", texts=[_text("broken")]),
    ]

    with pytest.raises(DatasetConflictError):
        repo.add_folder(version_id, _folder(), images)

    assert _count(session_factory, DatasetFolder) == 0
    assert _count(session_factory, DatasetFolderImage) == 0
    assert _count(session_factory, DatasetLearningText) == 0


def test_update_learning_text_elements_keeps_raw_text(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        version_id,
        _folder(),
        [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    committed_text = repo.get_version_snapshot(version_id).folders[0].images[0].texts[0]
    assert committed_text.is_edited is False

    # 確定済みの版に対する直接編集は拒否される
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.update_learning_text_elements(committed_text.id, ["Kariginu", "狩衣"])

    working = repo.create_working_version(dataset_id, base_version_id=version_id)
    text = repo.get_version_snapshot(working.id).folders[0].images[0].texts[0]
    assert text.is_edited is False

    repo.update_learning_text_elements(text.id, ["Kariginu", "狩衣"])

    updated = repo.get_version_snapshot(working.id).folders[0].images[0].texts[0]
    assert updated.raw_text == "Kariginu, 1girl"
    assert updated.elements == ["Kariginu", "狩衣"]
    assert updated.is_edited is True
    # 派生元の確定済み版は書き換わらない
    assert repo.get_version_snapshot(version_id).folders[0].images[0].texts[0] == committed_text
    with session_factory() as session:
        stored = session.get(DatasetLearningText, text.id)
        assert stored is not None
        # 日本語は ensure_ascii=False のまま保存される
        assert stored.elements_json == json.dumps(["Kariginu", "狩衣"], ensure_ascii=False)


def test_set_folder_trigger_word(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    committed_folder_id = repo.add_folder(version_id, _folder(), [])

    # 確定済みの版のフォルダは書き換えできない
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.set_folder_trigger_word(committed_folder_id, None)

    working = repo.create_working_version(dataset_id, base_version_id=version_id)
    folder_id = repo.get_version_snapshot(working.id).folders[0].id

    repo.set_folder_trigger_word(folder_id, None)

    folder = repo.get_version_snapshot(working.id).folders[0]
    assert folder.id == folder_id
    assert folder.trigger_word is None
    assert repo.get_version_snapshot(version_id).folders[0].trigger_word == "Kariginu"


def test_version_parent_is_recorded(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    parent_id = repo.create_version(dataset_id, "v01")
    child_id = repo.create_version(dataset_id, "v02", parent_version_id=parent_id)

    assert repo.get_version_snapshot(child_id).parent_version_id == parent_id
    assert repo.get_version_snapshot(parent_id).parent_version_id is None


def test_get_version_snapshot_missing_raises(repo: DatasetRepository) -> None:
    with pytest.raises(LookupError):
        repo.get_version_snapshot(12345)


def test_training_config_roundtrip(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    spec = TrainingConfigSpec(
        source_kind="kohya_gui_json",
        source_file_name="kariginu.json",
        raw_content='{"output_name": "kariginu"}',
        normalized_json='{"output_name": "kariginu"}',
        unmapped_json="{}",
        target_script="sdxl_train_network.py",
        output_name="kariginu",
        base_model="sd_xl_base_1.0.safetensors",
        resolution="1024,1024",
        network_dim=32,
        network_alpha=16.0,
        learning_rate=0.0001,
    )

    config_id = repo.add_training_config(dataset_id, version_id, spec)
    fetched = repo.get_training_config(config_id)
    listed = repo.list_training_configs(dataset_id)

    assert fetched.id == config_id
    assert fetched.dataset_id == dataset_id
    assert fetched.version_id == version_id
    assert fetched.created_at is not None
    for field in TrainingConfigSpec.__dataclass_fields__:
        assert getattr(fetched, field) == getattr(spec, field)
    assert listed == [fetched]


def test_get_training_config_missing_raises(repo: DatasetRepository) -> None:
    with pytest.raises(LookupError):
        repo.get_training_config(999)


# --- 学習テキストをライブラリの Tag へ写す (Issue #1454 / ADR 0104) ---


def _two_folder_version(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> tuple[int, int, int]:
    """画像 a が 2 フォルダに、画像 b が 1 フォルダ目だけにある版を作る。"""
    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        version_id,
        _folder("10_kariginu", 0),
        [
            FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, long_sleeves")]),
            FolderImageSpec(image_id=image_b, file_stem="b", texts=[_text("Kariginu, (smile:1.2)")]),
        ],
    )
    repo.add_folder(
        version_id,
        _folder("5_style", 1),
        [
            FolderImageSpec(
                image_id=image_a,
                file_stem="a",
                texts=[
                    _text("style, long_sleeves"),
                    LearningTextSpec(extension=".caption", raw_text="a girl", elements=["a girl"]),
                ],
            )
        ],
    )
    return version_id, image_a, image_b


def _tags_by_image(session_factory: Callable[[], Session]) -> dict[int, list[tuple[str, str]]]:
    with session_factory() as session:
        rows = session.execute(
            select(Tag.image_id, Tag.tag, Model.litellm_model_id).join(Model, Tag.model_id == Model.id)
        ).all()
    result: dict[int, list[tuple[str, str]]] = {}
    for image_id, tag, litellm_id in rows:
        result.setdefault(image_id, []).append((tag, litellm_id))
    return {key: sorted(value) for key, value in result.items()}


def test_copy_learning_texts_to_tags_uses_kohya_model_and_verbatim_elements(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    version_id, image_a, image_b = _two_folder_version(repo, session_factory)

    result = repo.copy_learning_texts_to_tags(version_id, dir_names=["10_kariginu"])

    assert (result.folders, result.images, result.tags_added, result.tags_skipped) == (1, 2, 4, 0)
    tags = _tags_by_image(session_factory)
    assert tags[image_a] == [
        ("Kariginu", KOHYA_DATASET_LITELLM_ID),
        ("long_sleeves", KOHYA_DATASET_LITELLM_ID),
    ]
    # 表記はそのまま (重み付き・大文字・アンダースコアを保つ)
    assert tags[image_b] == [
        ("(smile:1.2)", KOHYA_DATASET_LITELLM_ID),
        ("Kariginu", KOHYA_DATASET_LITELLM_ID),
    ]
    with session_factory() as session:
        row = session.execute(select(Tag).limit(1)).scalar_one()
        assert (row.tag_id, row.existing, row.is_edited_manually) == (None, True, False)
        model = session.execute(
            select(Model).where(Model.litellm_model_id == KOHYA_DATASET_LITELLM_ID)
        ).scalar_one()
        assert (model.name, model.provider, model.requires_api_key, model.model_types) == (
            "KOHYA_DATASET",
            "user",
            False,
            [],
        )


def test_copy_learning_texts_to_tags_unions_selected_folders(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """同じ画像が選んだ複数フォルダにあるときは要素の和集合を写す。.caption は既定では写さない。"""
    version_id, image_a, _ = _two_folder_version(repo, session_factory)

    result = repo.copy_learning_texts_to_tags(version_id)

    assert result.folders == 2
    assert result.images == 2
    assert [tag for tag, _ in _tags_by_image(session_factory)[image_a]] == [
        "Kariginu",
        "long_sleeves",
        "style",
    ]


def test_copy_learning_texts_to_tags_with_caption_extension(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    version_id, image_a, _ = _two_folder_version(repo, session_factory)

    result = repo.copy_learning_texts_to_tags(version_id, extension=".caption")

    assert result.images == 1
    assert _tags_by_image(session_factory)[image_a] == [("a girl", KOHYA_DATASET_LITELLM_ID)]


def test_copy_learning_texts_to_tags_is_add_only_and_keeps_other_models(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """写し直しは追加だけ。soft-reject 済みの行も、他モデル (MANUAL_EDIT) の同じ表記の行も触らない。"""
    version_id, image_a, _ = _two_folder_version(repo, session_factory)
    repo.copy_learning_texts_to_tags(version_id, dir_names=["10_kariginu"])
    with session_factory() as session:
        manual = Model(name="MANUAL_EDIT", provider="user", litellm_model_id=MANUAL_EDIT_LITELLM_ID)
        session.add(manual)
        session.flush()
        session.add(
            Tag(image_id=image_a, model_id=manual.id, tag="style", existing=False, is_edited_manually=True)
        )
        rejected = session.execute(
            select(Tag).where(Tag.image_id == image_a, Tag.tag == "Kariginu")
        ).scalar_one()
        rejected.rejected_at = rejected.created_at
        session.commit()

    result = repo.copy_learning_texts_to_tags(version_id)

    # a: Kariginu(既存 reject), long_sleeves(既存) は skip、style を追加。b: 2 つとも既存
    assert (result.tags_added, result.tags_skipped) == (1, 4)
    assert _tags_by_image(session_factory)[image_a] == [
        ("Kariginu", KOHYA_DATASET_LITELLM_ID),
        ("long_sleeves", KOHYA_DATASET_LITELLM_ID),
        ("style", KOHYA_DATASET_LITELLM_ID),
        ("style", MANUAL_EDIT_LITELLM_ID),
    ]
    with session_factory() as session:
        still_rejected = session.execute(
            select(Tag.rejected_at).where(Tag.image_id == image_a, Tag.tag == "Kariginu")
        ).scalar_one()
    assert still_rejected is not None


def test_copy_learning_texts_to_tags_dry_run_writes_nothing(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    version_id, _, _ = _two_folder_version(repo, session_factory)

    result = repo.copy_learning_texts_to_tags(version_id, dry_run=True)

    assert result.tags_added == 5
    assert result.dry_run is True
    assert _count(session_factory, Tag) == 0
    assert _count(session_factory, Model) == 0


def test_copy_learning_texts_to_tags_unknown_folder_or_version_raises(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    version_id, _, _ = _two_folder_version(repo, session_factory)

    with pytest.raises(LookupError):
        repo.copy_learning_texts_to_tags(version_id, dir_names=["10_kariginu", "nope"])
    with pytest.raises(LookupError):
        repo.copy_learning_texts_to_tags(9999)
    assert _count(session_factory, Tag) == 0


def test_copy_learning_texts_to_tags_chunks_existing_lookup(
    repo: DatasetRepository, session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """既存行の照会は BATCH_CHUNK_SIZE ごとに分割しても結果が変わらない (SQLite の変数上限対策)。"""
    version_id, _, _ = _two_folder_version(repo, session_factory)
    repo.copy_learning_texts_to_tags(version_id, dir_names=["10_kariginu"])
    monkeypatch.setattr(repo, "BATCH_CHUNK_SIZE", 1)

    result = repo.copy_learning_texts_to_tags(version_id)

    assert (result.tags_added, result.tags_skipped) == (1, 4)


# --- 学習テキストを写した Tag の取り消し (Issue #1490 / ADR 0104) ---


def test_revoke_learning_texts_from_tags_deletes_only_kohya_dataset_rows(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """KOHYA_DATASET の行だけを削除し、MANUAL_EDIT や AI モデルの行は残す。"""
    version_id, image_a, image_b = _two_folder_version(repo, session_factory)
    repo.copy_learning_texts_to_tags(version_id)
    with session_factory() as session:
        manual = Model(name="MANUAL_EDIT", provider="user", litellm_model_id=MANUAL_EDIT_LITELLM_ID)
        ai = Model(name="wd-tagger", provider="local", litellm_model_id="local/wd-tagger")
        session.add_all([manual, ai])
        session.flush()
        session.add_all(
            [
                Tag(
                    image_id=image_a,
                    model_id=manual.id,
                    tag="Kariginu",
                    existing=False,
                    is_edited_manually=True,
                ),
                Tag(
                    image_id=image_b,
                    model_id=ai.id,
                    tag="standing",
                    confidence_score=0.95,
                    existing=False,
                    is_edited_manually=False,
                ),
            ]
        )
        session.commit()

    result = repo.revoke_learning_texts_from_tags(version_id)

    assert (result.folders, result.images, result.tags_removed, result.tags_revoked, result.dry_run) == (
        2,
        2,
        5,
        5,
        False,
    )
    assert _tags_by_image(session_factory) == {
        image_a: [("Kariginu", MANUAL_EDIT_LITELLM_ID)],
        image_b: [("standing", "local/wd-tagger")],
    }


def test_revoke_learning_texts_from_tags_filters_by_folder(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """特定フォルダ指定時はそのフォルダの画像に付いた KOHYA_DATASET 行だけを削除する。"""
    version_id, _image_a, image_b = _two_folder_version(repo, session_factory)
    repo.copy_learning_texts_to_tags(version_id)

    # 5_style には image_a のみ所属 -> image_a の 3 件だけ削除され、image_b の 2 件は残る
    result = repo.revoke_learning_texts_from_tags(version_id, dir_names=["5_style"])

    assert (result.folders, result.images, result.tags_removed) == (1, 1, 3)
    assert _tags_by_image(session_factory) == {
        image_b: [
            ("(smile:1.2)", KOHYA_DATASET_LITELLM_ID),
            ("Kariginu", KOHYA_DATASET_LITELLM_ID),
        ],
    }


def test_revoke_learning_texts_from_tags_project_wide(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """version_id=None ならプロジェクト全体の KOHYA_DATASET 行を一括削除する。"""
    v1, image_a, _ = _two_folder_version(repo, session_factory)
    image_c = _insert_image(session_factory, "img-c")
    dataset_id = repo.ensure_dataset("other")
    v2 = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        v2,
        _folder("1_other", 0),
        [FolderImageSpec(image_id=image_c, file_stem="c", texts=[_text("other_tag")])],
    )
    repo.copy_learning_texts_to_tags(v1)
    repo.copy_learning_texts_to_tags(v2)
    with session_factory() as session:
        manual = Model(name="MANUAL_EDIT", provider="user", litellm_model_id=MANUAL_EDIT_LITELLM_ID)
        session.add(manual)
        session.flush()
        session.add(
            Tag(
                image_id=image_a, model_id=manual.id, tag="keep_me", existing=False, is_edited_manually=True
            )
        )
        session.commit()

    result = repo.revoke_copied_tags(version_id=None)

    assert (result.folders, result.images, result.tags_removed) == (0, 3, 6)
    assert _tags_by_image(session_factory) == {
        image_a: [("keep_me", MANUAL_EDIT_LITELLM_ID)],
    }


def test_revoke_learning_texts_from_tags_dry_run_writes_nothing(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    version_id, _, _ = _two_folder_version(repo, session_factory)
    # モデル未作成時の dry_run でもモデル行を作らない
    empty_preview = repo.revoke_learning_texts_from_tags(version_id, dry_run=True)
    assert (empty_preview.tags_removed, empty_preview.dry_run) == (0, True)
    assert _count(session_factory, Model) == 0

    repo.copy_learning_texts_to_tags(version_id)
    preview = repo.revoke_learning_texts_from_tags(version_id, dry_run=True)

    assert (preview.folders, preview.images, preview.tags_removed, preview.dry_run) == (2, 2, 5, True)
    assert _count(session_factory, Tag) == 5


def test_revoke_learning_texts_from_tags_errors_and_chunking(
    repo: DatasetRepository, session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    version_id, _, _ = _two_folder_version(repo, session_factory)
    with pytest.raises(ValueError):
        repo.revoke_learning_texts_from_tags(version_id=None, dir_names=["10_kariginu"])
    with pytest.raises(LookupError):
        repo.revoke_learning_texts_from_tags(9999)
    with pytest.raises(LookupError):
        repo.revoke_learning_texts_from_tags(version_id, dir_names=["nope"])

    repo.copy_learning_texts_to_tags(version_id)
    monkeypatch.setattr(repo, "BATCH_CHUNK_SIZE", 1)
    result = repo.revoke_learning_texts_from_tags(version_id)
    assert result.tags_removed == 5
    assert _count(session_factory, Tag) == 0


# --- 版の一覧 (Issue #1456) ---


def test_list_versions_returns_counts_per_version(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    dataset_id = repo.ensure_dataset("kariginu")
    v1 = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        v1,
        _folder("10_kariginu", 0),
        [
            FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("a")]),
            FolderImageSpec(image_id=image_b, file_stem="b", texts=[_text("b")]),
        ],
    )
    repo.add_folder(v1, _folder("5_style", 1), [FolderImageSpec(image_id=image_a, file_stem="a", texts=[])])
    v2 = repo.create_version(dataset_id, "v02", parent_version_id=v1)
    other = repo.create_version(repo.ensure_dataset("another"), "x")

    versions = repo.list_versions()

    assert [(v.dataset_name, v.version_name) for v in versions] == [
        ("another", "x"),
        ("kariginu", "v01"),
        ("kariginu", "v02"),
    ]
    by_id = {v.version_id: v for v in versions}
    assert (by_id[v1].folder_count, by_id[v1].image_count) == (2, 3)
    assert (by_id[v2].folder_count, by_id[v2].image_count, by_id[v2].parent_version_id) == (0, 0, v1)
    assert by_id[other].dataset_id != by_id[v1].dataset_id
    assert by_id[v1].created_at is not None


def test_list_versions_empty(repo: DatasetRepository) -> None:
    assert repo.list_versions() == []


# --- 作業中の版の編集・確定・破棄と確定済み版の不変性 (Issue #1486 / ADR 0098) ---


def test_committed_version_rejects_all_edit_and_discard_operations(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """確定済みの版 (`is_working=False`) はどの操作でも書き換わらず、編集・破棄・再確定は拒否される。"""
    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    folder_id = repo.add_folder(
        version_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    before = repo.get_version_snapshot(version_id)
    assert before.is_working is False
    text_id = before.folders[0].images[0].texts[0].id

    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.update_learning_text_elements(text_id, ["Kariginu", "edited"])
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.update_learning_text_elements(learning_text_id=text_id, elements=["Kariginu", "edited"])
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.add_image_to_working_folder(folder_id, image_b, "b", elements=["1girl"])
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.replace_image_in_working_folder(folder_id, "a", image_b)
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.remove_image_from_working_folder(folder_id, "a")
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.update_working_folder_trigger_word(folder_id, "NewTrig")
    with pytest.raises(ValueError, match="既に確定済みの版です"):
        repo.commit_working_version(version_id)
    with pytest.raises(ValueError, match="確定済みの版は破棄できません"):
        repo.discard_working_version(version_id)

    after = repo.get_version_snapshot(version_id)
    assert after == before


def test_create_working_version_copies_latest_or_specified_base_and_blocks_duplicate(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """作業中の版は最新または指定した確定済み版から全量コピーで作られ、同時に 2 つは作れない。"""
    dataset_id = repo.ensure_dataset("kariginu")
    # 確定済みの版が 1 つも無いときは作れない
    with pytest.raises(ValueError, match="派生元となる確定済みの版が見つかりません"):
        repo.create_working_version(dataset_id)

    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    v1 = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        v1,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    v2 = repo.create_version(dataset_id, "v02", parent_version_id=v1)
    repo.add_folder(
        v2,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_b, file_stem="b", texts=[_text("Kariginu, solo")])],
    )

    # base_version_id 省略時は最新の確定済み版 (v2) から作られる
    working = repo.create_working_version(dataset_id)
    assert working.is_working is True
    assert working.parent_version_id == v2
    assert working.name == "v02-working"
    snap = repo.get_version_snapshot(working.id)
    assert snap.is_working is True
    assert snap.parent_version_id == v2
    assert [img.file_stem for img in snap.folders[0].images] == ["b"]

    # 未確定の作業中の版がある間は 2 つ目を作れない
    with pytest.raises(ValueError, match="作業中の版が既に存在します"):
        repo.create_working_version(dataset_id, base_version_id=v1)

    repo.discard_working_version(working.id)

    # 明示指定した base_version_id (v1) から作れる
    working_from_v1 = repo.create_working_version(dataset_id, base_version_id=v1, version_name="v03-draft")
    assert working_from_v1.parent_version_id == v1
    assert working_from_v1.name == "v03-draft"
    snap_v1 = repo.get_version_snapshot(working_from_v1.id)
    assert [img.file_stem for img in snap_v1.folders[0].images] == ["a"]


def test_working_version_edits_commit_and_diff_against_parent(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """作業中の版を編集して確定すると新しい版になり、親の版との diff で編集内容が出る。"""
    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    image_b2 = _insert_image(session_factory, "img-b2")
    image_c = _insert_image(session_factory, "img-c")
    image_d = _insert_image(session_factory, "img-d")
    dataset_id = repo.ensure_dataset("kariginu")
    base_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        base_id,
        _folder("10_kariginu", 0),
        [
            FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, 1girl, smile")]),
            FolderImageSpec(image_id=image_b, file_stem="b", texts=[_text("Kariginu, old_b")]),
            FolderImageSpec(image_id=image_d, file_stem="d", texts=[_text("Kariginu, remove_me")]),
        ],
    )
    base_snapshot_before = repo.get_version_snapshot(base_id)

    working = repo.create_working_version(dataset_id, base_version_id=base_id)
    working_snap = repo.get_version_snapshot(working.id)
    folder_id = working_snap.folders[0].id
    text_a_id = working_snap.folders[0].images[0].texts[0].id

    # 1. 学習テキスト要素の編集
    repo.update_learning_text_elements(
        learning_text_id=text_a_id, elements=["Kariginu", "1girl", "serious"]
    )
    # 2. 画像の追加 (トリガーワード自動先頭付与)
    added_c = repo.add_image_to_working_folder(folder_id, image_c, "c", elements=["long_sleeves"])
    assert _load_json_elements(added_c.learning_texts[0].elements_json) == ["Kariginu", "long_sleeves"]
    # 3. 画像の差し替え (既定 inherit_texts=True で旧学習テキストを引き継ぐ)
    replaced_b = repo.replace_image_in_working_folder(folder_id, "b", image_b2)
    assert replaced_b.image_id == image_b2
    assert _load_json_elements(replaced_b.learning_texts[0].elements_json) == ["Kariginu", "old_b"]
    # 4. 画像の削除
    repo.remove_image_from_working_folder(folder_id, "d")
    # 5. トリガーワードの変更
    repo.update_working_folder_trigger_word(folder_id, "Kariginu_v2")

    # 確定する
    committed = repo.commit_working_version(working.id, version_name="v02")
    assert committed.is_working is False
    assert committed.name == "v02"
    assert committed.parent_version_id == base_id

    # 確定後は編集も破棄も拒否される
    with pytest.raises(ValueError, match="確定済みの版は編集できません"):
        repo.update_learning_text_elements(text_a_id, ["nope"])
    with pytest.raises(ValueError, match="確定済みの版は破棄できません"):
        repo.discard_working_version(committed.id)

    # 親の確定済み版は一切書き換わっていない
    assert repo.get_version_snapshot(base_id) == base_snapshot_before

    # 親の版との diff で編集内容が出る
    diff = DatasetVersionDiffService(repo).diff_versions(base_id, committed.id)
    assert diff.has_changes is True
    (folder_diff,) = diff.folders
    assert folder_diff.dir_name == "10_kariginu"
    assert folder_diff.trigger_word == ("Kariginu", "Kariginu_v2")
    by_stem = {img.file_stem: img for img in folder_diff.images}
    assert by_stem["a"].status is ChangeStatus.CHANGED
    assert by_stem["a"].texts[0].added_elements == ["serious"]
    assert by_stem["a"].texts[0].removed_elements == ["smile"]
    assert by_stem["b"].status is ChangeStatus.REPLACED
    assert (by_stem["b"].base_image_id, by_stem["b"].target_image_id) == (image_b, image_b2)
    assert by_stem["b"].texts == []
    assert by_stem["c"].status is ChangeStatus.ADDED
    assert by_stem["d"].status is ChangeStatus.REMOVED
    assert diff.summary.images_added == 1
    assert diff.summary.images_removed == 1
    assert diff.summary.images_replaced == 1
    assert diff.summary.images_changed == 1


def _load_json_elements(elements_json: str) -> list[str]:
    return [str(x) for x in json.loads(elements_json)]


def test_replace_image_without_inheriting_texts_resets_to_trigger_or_empty(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """差し替え時に inherit_texts=False を指定すると、トリガーワードがあればそれだけ、無ければ空になる。"""
    image_1 = _insert_image(session_factory, "img-1")
    image_2 = _insert_image(session_factory, "img-2")
    image_3 = _insert_image(session_factory, "img-3")
    dataset_id = repo.ensure_dataset("kariginu")
    base_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        base_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_1, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    repo.add_folder(
        base_id,
        FolderSpec(dir_name="5_notrig", name="notrig", num_repeats=5, trigger_word=None, position=1),
        [FolderImageSpec(image_id=image_1, file_stem="b", texts=[_text("solo, smile")])],
    )

    working = repo.create_working_version(dataset_id, base_version_id=base_id)
    snap = repo.get_version_snapshot(working.id)
    folder_with_trig = snap.folders[0].id
    folder_no_trig = snap.folders[1].id

    replaced_a = repo.replace_image_in_working_folder(
        folder_with_trig, "a", image_2, new_file_stem="a_new", inherit_texts=False
    )
    assert replaced_a.file_stem == "a_new"
    assert _load_json_elements(replaced_a.learning_texts[0].elements_json) == ["Kariginu"]
    assert replaced_a.learning_texts[0].raw_text == "Kariginu"
    assert replaced_a.learning_texts[0].is_edited is True

    replaced_b = repo.replace_image_in_working_folder(folder_no_trig, "b", image_3, inherit_texts=False)
    assert _load_json_elements(replaced_b.learning_texts[0].elements_json) == []
    assert replaced_b.learning_texts[0].raw_text == ""


def test_add_image_trigger_word_prepend_and_find_missing_trigger_word(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """トリガーワード自動付与の有効/無効と、トリガーワード欠落画像の検出を検証する。"""
    image_1 = _insert_image(session_factory, "img-1")
    image_2 = _insert_image(session_factory, "img-2")
    image_3 = _insert_image(session_factory, "img-3")
    dataset_id = repo.ensure_dataset("kariginu")
    base_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        base_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_1, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    repo.add_folder(
        base_id,
        FolderSpec(dir_name="5_notrig", name="notrig", num_repeats=5, trigger_word=None, position=1),
        [FolderImageSpec(image_id=image_1, file_stem="x", texts=[_text("no_trigger_needed")])],
    )

    working = repo.create_working_version(dataset_id, base_version_id=base_id)
    folder_id = repo.get_version_snapshot(working.id).folders[0].id

    # 既にトリガーワードが含まれている場合は重複付与しない
    added_dup = repo.add_image_to_working_folder(folder_id, image_2, "b", elements=["Kariginu", "smile"])
    assert _load_json_elements(added_dup.learning_texts[0].elements_json) == ["Kariginu", "smile"]

    # auto_prepend_trigger_word=False でトリガーワードを付けずに追加
    repo.add_image_to_working_folder(
        folder_id, image_3, "c", elements=["smile"], auto_prepend_trigger_word=False
    )

    missing = repo.find_images_missing_trigger_word(working.id)
    assert [(m.folder.dir_name, m.file_stem, m.image_id) for m in missing] == [
        ("10_kariginu", "c", image_3)
    ]


def test_discard_working_version_deletes_working_rows_without_affecting_committed(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """作業中の版を破棄すると、確定した版に影響せず作業中の行だけがすべて消える。"""
    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    dataset_id = repo.ensure_dataset("kariginu")
    base_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        base_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    base_before = repo.get_version_snapshot(base_id)

    working = repo.create_working_version(dataset_id, base_version_id=base_id)
    working_folder_id = repo.get_version_snapshot(working.id).folders[0].id
    repo.add_image_to_working_folder(working_folder_id, image_b, "b", elements=["extra"])
    assert _count(session_factory, DatasetFolder) == 2
    assert _count(session_factory, DatasetFolderImage) == 3

    repo.discard_working_version(working.id)

    with pytest.raises(LookupError):
        repo.get_version_snapshot(working.id)
    assert repo.get_version_snapshot(base_id) == base_before
    assert _count(session_factory, DatasetFolder) == 1
    assert _count(session_factory, DatasetFolderImage) == 1
    assert _count(session_factory, DatasetLearningText) == 1

    # 破棄した後は再び作業中の版を作れる
    recreated = repo.create_working_version(dataset_id, base_version_id=base_id)
    assert recreated.is_working is True
    assert recreated.parent_version_id == base_id


# --- 画像から使われたデータセット・版・フォルダ・学習テキストを引く (Issue #1461) ---


def test_list_image_usage_across_datasets_versions_and_folders(
    repo: DatasetRepository, session_factory: Callable[[], Session], fk_engine: Engine
) -> None:
    """複数データセット・複数版・複数フォルダに入る画像の所属と学習テキストを 2 クエリ以内で返す。"""
    image_a = _insert_image(session_factory, "img-a")
    image_b = _insert_image(session_factory, "img-b")
    ds_kariginu = repo.ensure_dataset("kariginu")
    v1 = repo.create_version(ds_kariginu, "v01")
    f_v1_main = repo.add_folder(
        v1,
        _folder("10_kariginu", 0),
        [
            FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, 1girl")]),
            FolderImageSpec(image_id=image_b, file_stem="b", texts=[_text("Kariginu, solo")]),
        ],
    )
    f_v1_style = repo.add_folder(
        v1,
        FolderSpec(dir_name="5_style", name="style", num_repeats=5, trigger_word=None, position=1),
        [
            FolderImageSpec(
                image_id=image_a,
                file_stem="a_style",
                texts=[
                    _text("(style:1.2), long_sleeves"),
                    LearningTextSpec(extension=".caption", raw_text="a girl", elements=["a girl"]),
                ],
            )
        ],
    )
    v2 = repo.create_version(ds_kariginu, "v02", parent_version_id=v1)
    f_v2_main = repo.add_folder(
        v2,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_a, file_stem="a", texts=[_text("Kariginu, 1girl, smile")])],
    )
    ds_other = repo.ensure_dataset("another")
    v_other = repo.create_version(ds_other, "init")
    f_other = repo.add_folder(
        v_other,
        FolderSpec(dir_name="3_sub", name="sub", num_repeats=3, trigger_word="SubTrig", position=0),
        [FolderImageSpec(image_id=image_a, file_stem="sub_a", texts=[])],
    )

    select_statements: list[str] = []

    def _record_select(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(fk_engine, "before_cursor_execute", _record_select)
    try:
        usages = repo.list_image_usage(image_a)
    finally:
        event.remove(fk_engine, "before_cursor_execute", _record_select)

    # N+1 にならない (所属+親テーブルの JOIN 1 クエリ + 学習テキストの selectinload 1 クエリ)
    assert len(select_statements) <= 2

    # データセット名 -> 版 ID -> フォルダ position 順
    assert [
        (u.dataset_name, u.version_name, u.dir_name, u.file_stem, [t.raw_text for t in u.texts])
        for u in usages
    ] == [
        ("another", "init", "3_sub", "sub_a", []),
        ("kariginu", "v01", "10_kariginu", "a", ["Kariginu, 1girl"]),
        ("kariginu", "v01", "5_style", "a_style", ["(style:1.2), long_sleeves", "a girl"]),
        ("kariginu", "v02", "10_kariginu", "a", ["Kariginu, 1girl, smile"]),
    ]
    assert [u.folder_id for u in usages] == [f_other, f_v1_main, f_v1_style, f_v2_main]
    assert usages[0].dataset_id == ds_other
    assert usages[0].version_id == v_other
    assert usages[0].trigger_word == "SubTrig"
    assert usages[1].dataset_id == ds_kariginu
    assert usages[1].version_id == v1
    assert usages[1].parent_version_id is None
    assert usages[1].folder_name == "kariginu"
    assert usages[1].num_repeats == 10
    assert usages[1].trigger_word == "Kariginu"
    assert [t.extension for t in usages[2].texts] == [".txt", ".caption"]
    assert usages[2].texts[0].elements == ["(style:1.2)", "long_sleeves"]
    assert usages[3].parent_version_id == v1


def test_list_image_usage_unused_image_returns_empty_list(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    """使われていない画像や未登録の image_id でもエラーにせず空リストを返す。"""
    unused_id = _insert_image(session_factory, "img-unused")
    used_id = _insert_image(session_factory, "img-used")
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        version_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=used_id, file_stem="u", texts=[_text("Kariginu")])],
    )

    assert repo.list_image_usage(unused_id) == []
    assert repo.list_image_usage(999999) == []
