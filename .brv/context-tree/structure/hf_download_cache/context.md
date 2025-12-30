
The application uses a path-based caching mechanism for Hugging Face dataset files, managed via `hf_hub_download`. The cache is not a content-addressable storage (CAS) in the local application cache; instead, it is handled per `dest_dir`.

---

A manifest file within each destination directory maps a `repo/filename` key to an ETag and the local file path. The `download_with_fallback` function checks the remote ETag using `HfApi.file_metadata`. If the ETag matches the cached version, or if the application is offline, the cached path is returned. Otherwise, `hf_hub_download` is called with `local_dir=dest_dir` to download the file.

---

The `download_with_offline_fallback` function in `genai_tag_db_tools.io.hf_downloader` provides resilience by attempting a regular download and, upon network failure, falling back to a cached version by calling `download_hf_dataset_file` with `local_files_only=True`.
