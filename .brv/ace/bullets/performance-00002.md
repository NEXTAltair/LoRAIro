<!--
WARNING: Do not rename this file manually!
File name: performance-00002.md
This file is managed by ByteRover CLI. Only edit the content below.
Renaming this file will break the link to the playbook metadata.
-->

Optimized FileSystemManager.get_image_files() to use single rglob pass instead of per-extension iteration, reducing directory traversal overhead for large datasets