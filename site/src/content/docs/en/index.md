---
type: Guide
title: User guide
description: From image registration to AI annotation and training dataset export.
sidebar:
  order: 1
---

LoRAIro is a desktop app for registering images for LoRA training, generating tags, captions and evaluations with AI, reviewing them, and exporting datasets. It does not run training itself.

## Getting started

1. [Install on Windows](./installation/) and start the GUI.
2. [Register images](./projects/), then [search and stage them](./search/).
3. Run [annotation](./annotation/) and check the results in Jobs.
4. [Review and edit tags](./editing/), then [export the dataset](./export/).

Try the entire workflow with a few images first. Choosing a WebAPI sends images outside your computer and may incur charges.

## Scope of this guide

The user guide is available in Japanese, English, Traditional Chinese and Simplified Chinese. Japanese is the original; other languages are AI-assisted translations. If meanings differ, refer to Japanese and report the discrepancy on GitHub.

Four-language documentation does not mean that the app interface supports four languages or that image tags and captions are automatically translated. Each chapter explains the supported scope.

Developer design documents and ADRs remain in the [repository docs](https://github.com/NEXTAltair/LoRAIro/tree/main/docs). This guide follows current operations rather than the old Sphinx-generated API listing.

## Protect your data

Annotation and tag editing modify the project database. [Back up your data](./troubleshooting/) before major changes, and distinguish temporary export adjustments from persistent database changes.
