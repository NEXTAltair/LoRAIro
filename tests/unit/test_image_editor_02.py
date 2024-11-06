from editor.image_processor import ImageProcessingManager, FileSystemManager


def test_image_processing_manager_init():
    fsm = FileSystemManager()
    target_resolution = 512
    preferred_resolutions = [(512, 512), (768, 512)]

    ipm = ImageProcessingManager(fsm, target_resolution, preferred_resolutions)
    assert ipm.target_resolution == target_resolution
