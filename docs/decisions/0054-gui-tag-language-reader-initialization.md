---
type: ADR
title: GUI tag language reader initialization
status: Accepted
timestamp: 2026-06-03
tags: []
---
# ADR 0054: GUI tag language reader initialization

- **Related Issue**: #603
- **Related PR**: #609

## Context

ADR 0050 made tag DB initialization lazy so read-only CLI startup does not initialize
genai-tag-db-tools. That kept `AnnotationRepository.merged_reader` as `None` until a tag DB
operation explicitly needs it.

`WidgetSetupService.setup_selected_image_details()` still read the repository attribute directly
during GUI setup. Because direct attribute reads do not trigger the repository lazy path, the image
details widget received `None` and hid the tag language selector even when tag translation languages
were available.

## Decision

`AnnotationRepository` exposes `get_merged_reader()` as the public accessor for callers that
intentionally need external tag DB support.

GUI selected image details setup uses that accessor and injects the returned reader into
`SelectedImageDetailsWidget`. The `merged_reader` attribute remains an implementation cache, not the
authoritative external API for GUI wiring.

## Rationale

This preserves ADR 0050's side-effect-light repository construction while making GUI translation
support opt in at the integration boundary that needs it.

The nearest alternative was making `merged_reader` a property with implicit initialization. That
would make every attribute read potentially initialize external tag DB state and would obscure which
runtime paths are allowed to pay that cost.

## Consequences

- Read-only CLI startup continues to avoid eager tag DB initialization.
- GUI image details setup initializes the tag reader intentionally, so the tag language selector can
  be populated when tag languages exist.
- Tests must cover the setup integration path, not only widget behavior after a reader has already
  been injected.

## Related

- ADR 0050 (CLI Tag DB Lazy Initialization) - establishes lazy external tag DB initialization.
- PR #609 - implements `AnnotationRepository.get_merged_reader()` and GUI setup wiring.