<!--
WARNING: Do not rename this file manually!
File name: project-00007.md
This file is managed by ByteRover CLI. Only edit the content below.
Renaming this file will break the link to the playbook metadata.
-->

AnnotationControlWidget annotation_started emits AnnotationSettings but AnnotationCoordinator._on_annotation_started still expects list[str], so align the coordinator to accept the dataclass and reuse the same structure when dispatching to services to remove the legacy signal contract.