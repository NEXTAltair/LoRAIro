<!--
WARNING: Do not rename this file manually!
File name: strategies-00006.md
This file is managed by ByteRover CLI. Only edit the content below.
Renaming this file will break the link to the playbook metadata.
-->

SelectedImageDetailsWidget scroll update (2025-09-30) is now the reference for PySide6 panels: inherit QScrollArea, set widgetResizable=true with vertical scrollbars AsNeeded/horizontal off, and move contents into scrollAreaWidgetContents with spacing=10, margins=5. Reuse this pattern whenever converting other MainWindow panels to scrollable layouts.