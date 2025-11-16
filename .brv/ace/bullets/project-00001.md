<!--
WARNING: Do not rename this file manually!
File name: project-00001.md
This file is managed by ByteRover CLI. Only edit the content below.
Renaming this file will break the link to the playbook metadata.
-->

MainWindow Phase2 refactor (2025-11-15) finished: window shrank 1645竊・87 lines and delegates workflows to 5 controllers (Dataset/AnnotationWorkflow/Settings/Export/Hybrid) plus 6 services (DataTransform/SelectionState/PipelineControl/ProgressState/ResultHandler/WidgetSetup). MainWindow now focuses on DI + widget wiring; see .serena/memories/mainwindow_refactoring_phase2_completion_2025_11_15.md for metrics.