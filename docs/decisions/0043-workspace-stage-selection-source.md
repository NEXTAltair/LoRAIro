# 0043. Workspace stage button selection source

## Context

Issue #570 reports that the workspace toolbar button "選択をステージングへ" can show a
"no selection" message and fail to add images to the batch tag staging area even when thumbnails
appear selected. The Qt Designer button connection can invoke `send_selected_to_batch_tag()` with
the `QPushButton.clicked(bool)` payload, while the context-menu path passes visible selected IDs
explicitly.

## Decision

Keep `DatasetStateManager` as the primary selection source. Treat a `bool` slot payload as a
button invocation rather than explicit selected IDs. Add a read-only
`ThumbnailSelectorWidget.get_visible_selected_image_ids()` helper and let
`MainWindow.send_selected_to_batch_tag()` use it only when the caller did not provide an explicit
ID list and the dataset selection is empty.

## Rationale

This preserves existing right-click and explicit-ID behavior while keeping `DatasetStateManager` as
the only authoritative selection source. Raw `QGraphicsScene.selectedItems()` was rejected because
Qt scene selection can become stale after application-level deselect actions, while painting is
driven by `DatasetStateManager`. Updating the toolbar slot to require image IDs was rejected because
the Qt Designer connection is a plain button click and should remain compatible with Qt's optional
checked-state payload.

## Consequences

Tests must cover both selection sources and the no-selection warning path. Future workspace staging
entry points should either pass explicit IDs or use the same visible-selection fallback instead of
adding another selection-resolution path.
