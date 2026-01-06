
## Relations
@@structure/tag-registration

''The tag registration process in LoRAIro, specifically within `ImageRepository._get_or_create_tag_id_external`, is designed to be resilient. It includes specific error handling for race conditions. If a call to `TagRegisterService.register_tag` results in an `IntegrityError`, it indicates that another process likely registered the same tag in the small window between the initial search and the registration attempt. To handle this, the system catches the `IntegrityError`, logs a warning about the race condition, and then immediately retries the search for the tag. This ensures that the correct `tag_id` is retrieved without failing the entire operation.

Additionally, the system employs a graceful fallback mechanism. If the external tag database services (`MergedTagReader` or `TagRegisterService`) are unavailable for any reason (e.g., initialization failure), the function will return `tag_id=None` instead of raising an exception. This allows the application to continue saving tag information locally, albeit without the link to the central tag taxonomy, preventing data loss and ensuring application stability.
'''
