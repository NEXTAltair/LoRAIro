<!--
WARNING: Do not rename this file manually!
File name: strategies-00002.md
This file is managed by ByteRover CLI. Only edit the content below.
Renaming this file will break the link to the playbook metadata.
-->

Large PySide6 windows should be refactored in phases: Phase1 extract services, Phase2 introduce controllers per workflow, optional Phase3 trims residual init logic. Keep controllers thin (UI orchestration) and inject services so business logic becomes testable outside the Qt event loop.