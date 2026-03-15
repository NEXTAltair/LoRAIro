from unittest.mock import Mock

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.filter_criteria import ImageFilterCriteria


def test_get_images_count_only_calls_repository() -> None:
    repository = Mock()
    config_service = Mock()
    manager = ImageDatabaseManager(repository=repository, config_service=config_service)

    criteria = ImageFilterCriteria(tags=["cat"], use_and=True)
    repository.get_images_count_only.return_value = 42

    count = manager.get_images_count_only(criteria=criteria)

    assert count == 42
    repository.get_images_count_only.assert_called_once_with(criteria)


def test_get_images_count_only_returns_zero_on_error() -> None:
    repository = Mock()
    config_service = Mock()
    manager = ImageDatabaseManager(repository=repository, config_service=config_service)

    repository.get_images_count_only.side_effect = RuntimeError("db down")

    count = manager.get_images_count_only(criteria=ImageFilterCriteria())

    assert count == 0
