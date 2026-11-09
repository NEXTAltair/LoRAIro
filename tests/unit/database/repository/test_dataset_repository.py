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
    text = repo.get_version_snapshot(version_id).folders[0].images[0].texts[0]
    assert text.is_edited is False

    repo.update_learning_text_elements(text.id, ["Kariginu", "狩衣"])

    updated = repo.get_version_snapshot(version_id).folders[0].images[0].texts[0]
    assert updated.raw_text == "Kariginu, 1girl"
    assert updated.elements == ["Kariginu", "狩衣"]
    assert updated.is_edited is True
    with session_factory() as session:
        stored = session.get(DatasetLearningText, text.id)
        assert stored is not None
        # 日本語は ensure_ascii=False のまま保存される
        assert stored.elements_json == json.dumps(["Kariginu", "狩衣"], ensure_ascii=False)


def test_set_folder_trigger_word(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    folder_id = repo.add_folder(version_id, _folder(), [])

    repo.set_folder_trigger_word(folder_id, None)

    folder = repo.get_version_snapshot(version_id).folders[0]
    assert folder.id == folder_id
    assert folder.trigger_word is None


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
