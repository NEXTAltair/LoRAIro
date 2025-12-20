# Repository Pattern Implementation Examples

Complete, real-world repository implementation examples for LoRAIro.

## Example 1: Basic ImageRepository

Full implementation of ImageRepository with CRUD operations.

```python
from typing import Optional
from sqlalchemy.orm import scoped_session, Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from loguru import logger

from src.lorairo.database.schema import Image

class ImageRepository:
    """
    Repository for Image entity data access.

    Handles all database operations for Image model including
    CRUD operations, search, and batch processing.
    """

    def __init__(self, session_factory: scoped_session):
        """
        Initialize repository with session factory.

        Args:
            session_factory: SQLAlchemy scoped_session for database access
        """
        self.session_factory = session_factory

    def get_by_id(self, image_id: int) -> Optional[Image]:
        """
        Retrieve image by ID.

        Args:
            image_id: Primary key of image

        Returns:
            Image instance if found, None otherwise
        """
        with self.session_factory() as session:
            return session.query(Image).filter(Image.id == image_id).first()

    def get_all(self, limit: Optional[int] = None) -> list[Image]:
        """
        Retrieve all images with optional limit.

        Args:
            limit: Maximum number of images to return (None for all)

        Returns:
            List of Image instances
        """
        with self.session_factory() as session:
            query = session.query(Image)
            if limit:
                query = query.limit(limit)
            return query.all()

    def add(self, image: Image) -> Image:
        """
        Add new image to database.

        Args:
            image: Image instance to add

        Returns:
            Image instance with generated ID

        Raises:
            IntegrityError: If image violates unique constraints
        """
        with self.session_factory() as session:
            session.add(image)
            session.commit()
            session.refresh(image)  # Populate ID and defaults
            return image

    def batch_add(self, images: list[Image]) -> list[Image]:
        """
        Add multiple images in single transaction.

        Args:
            images: List of Image instances to add

        Returns:
            List of Image instances with generated IDs
        """
        with self.session_factory() as session:
            session.add_all(images)
            session.commit()
            # All images now have IDs populated
            return images

    def update(self, image: Image) -> Image:
        """
        Update existing image.

        Args:
            image: Image instance with updated fields

        Returns:
            Updated Image instance
        """
        with self.session_factory() as session:
            session.merge(image)
            session.commit()
            return image

    def delete(self, image_id: int) -> bool:
        """
        Delete image by ID.

        Args:
            image_id: Primary key of image to delete

        Returns:
            True if deleted, False if not found
        """
        with self.session_factory() as session:
            image = session.query(Image).filter(Image.id == image_id).first()
            if image:
                session.delete(image)
                session.commit()
                return True
            return False

    def exists(self, image_id: int) -> bool:
        """
        Check if image exists by ID.

        Args:
            image_id: Primary key of image

        Returns:
            True if exists, False otherwise
        """
        with self.session_factory() as session:
            return session.query(Image.id).filter(Image.id == image_id).first() is not None
```

## Example 2: Advanced Search with Criteria

Type-safe search implementation using dataclass criteria.

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class ImageSearchCriteria:
    """
    Type-safe search criteria for images.

    All fields are optional; only provided fields are used in query.
    """
    tags: Optional[list[str]] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    min_width: Optional[int] = None
    min_height: Optional[int] = None
    phash: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    limit: Optional[int] = None
    offset: Optional[int] = None

class ImageRepository:
    # ... (previous methods)

    def search(self, criteria: ImageSearchCriteria) -> list[Image]:
        """
        Search images with type-safe criteria.

        Args:
            criteria: Search criteria dataclass

        Returns:
            List of Image instances matching criteria

        Example:
            >>> criteria = ImageSearchCriteria(
            ...     tags=["anime", "landscape"],
            ...     min_score=0.8,
            ...     limit=10
            ... )
            >>> images = repository.search(criteria)
        """
        with self.session_factory() as session:
            query = session.query(Image)

            # Apply filters only if criteria provided
            if criteria.tags:
                # Assuming tags is JSON array in database
                for tag in criteria.tags:
                    query = query.filter(Image.tags.contains(tag))

            if criteria.min_score is not None:
                query = query.filter(Image.score >= criteria.min_score)

            if criteria.max_score is not None:
                query = query.filter(Image.score <= criteria.max_score)

            if criteria.min_width is not None:
                query = query.filter(Image.width >= criteria.min_width)

            if criteria.min_height is not None:
                query = query.filter(Image.height >= criteria.min_height)

            if criteria.phash is not None:
                query = query.filter(Image.phash == criteria.phash)

            if criteria.created_after is not None:
                query = query.filter(Image.created_at >= criteria.created_after)

            if criteria.created_before is not None:
                query = query.filter(Image.created_at <= criteria.created_before)

            # Apply pagination
            if criteria.offset is not None:
                query = query.offset(criteria.offset)

            if criteria.limit is not None:
                query = query.limit(criteria.limit)

            return query.all()

    def count_matching(self, criteria: ImageSearchCriteria) -> int:
        """
        Count images matching criteria without fetching data.

        Args:
            criteria: Search criteria dataclass

        Returns:
            Number of images matching criteria
        """
        with self.session_factory() as session:
            query = session.query(Image.id)

            # Apply same filters as search()
            if criteria.tags:
                for tag in criteria.tags:
                    query = query.filter(Image.tags.contains(tag))

            if criteria.min_score is not None:
                query = query.filter(Image.score >= criteria.min_score)

            # ... (other filters same as search)

            return query.count()
```

## Example 3: Error Handling and Logging

Robust error handling with specific exception catching.

```python
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, OperationalError
from loguru import logger

class ImageRepository:
    # ... (previous methods)

    def add_safe(self, image: Image) -> Optional[Image]:
        """
        Safely add image with comprehensive error handling.

        Args:
            image: Image instance to add

        Returns:
            Image instance if successful, None on error
        """
        try:
            with self.session_factory() as session:
                session.add(image)
                session.commit()
                session.refresh(image)
                logger.info(f"Added image: {image.path}")
                return image

        except IntegrityError as e:
            logger.error(f"Integrity constraint violated for {image.path}: {e}")
            return None

        except OperationalError as e:
            logger.error(f"Database operational error: {e}")
            return None

        except SQLAlchemyError as e:
            logger.error(f"Database error adding image: {e}")
            return None

    def batch_add_safe(self, images: list[Image]) -> tuple[list[Image], list[tuple[Image, str]]]:
        """
        Safely add multiple images with error tracking.

        Args:
            images: List of Image instances to add

        Returns:
            Tuple of (successful_images, failed_images_with_errors)
        """
        successful = []
        failed = []

        for image in images:
            try:
                with self.session_factory() as session:
                    session.add(image)
                    session.commit()
                    session.refresh(image)
                    successful.append(image)

            except IntegrityError as e:
                error_msg = f"Integrity error: {e}"
                failed.append((image, error_msg))
                logger.warning(f"Failed to add {image.path}: {error_msg}")

            except SQLAlchemyError as e:
                error_msg = f"Database error: {e}"
                failed.append((image, error_msg))
                logger.error(f"Failed to add {image.path}: {error_msg}")

        logger.info(f"Batch add: {len(successful)} successful, {len(failed)} failed")
        return successful, failed
```

## Example 4: Complex Queries with Joins

Advanced queries using SQLAlchemy ORM relationships.

```python
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_

class ImageRepository:
    # ... (previous methods)

    def get_with_annotations(self, image_id: int) -> Optional[Image]:
        """
        Retrieve image with all related annotations in single query.

        Uses eager loading to avoid N+1 query problem.

        Args:
            image_id: Primary key of image

        Returns:
            Image instance with annotations loaded, None if not found
        """
        with self.session_factory() as session:
            return session.query(Image)\
                .options(joinedload(Image.annotations))\
                .filter(Image.id == image_id)\
                .first()

    def get_high_quality_with_tags(self, min_score: float = 0.8) -> list[Image]:
        """
        Retrieve high-quality images with their tags.

        Args:
            min_score: Minimum quality score threshold

        Returns:
            List of high-quality Image instances with tags loaded
        """
        with self.session_factory() as session:
            return session.query(Image)\
                .options(selectinload(Image.tags))\
                .filter(Image.score >= min_score)\
                .order_by(Image.score.desc())\
                .all()

    def find_similar_by_phash(self, phash: str, threshold: int = 5) -> list[Image]:
        """
        Find images with similar perceptual hash.

        Args:
            phash: Perceptual hash to compare
            threshold: Hamming distance threshold

        Returns:
            List of similar Image instances
        """
        with self.session_factory() as session:
            # Note: This is simplified; real implementation would use
            # custom SQL function for hamming distance calculation
            return session.query(Image)\
                .filter(Image.phash.like(f"{phash[:threshold]}%"))\
                .all()

    def search_complex(
        self,
        required_tags: Optional[list[str]] = None,
        optional_tags: Optional[list[str]] = None,
        exclude_tags: Optional[list[str]] = None,
        score_range: Optional[tuple[float, float]] = None
    ) -> list[Image]:
        """
        Complex search with AND/OR tag logic.

        Args:
            required_tags: All these tags must be present (AND)
            optional_tags: At least one of these tags must be present (OR)
            exclude_tags: None of these tags can be present (NOT)
            score_range: (min_score, max_score) tuple

        Returns:
            List of Image instances matching criteria
        """
        with self.session_factory() as session:
            query = session.query(Image)

            # Required tags (AND logic)
            if required_tags:
                for tag in required_tags:
                    query = query.filter(Image.tags.contains(tag))

            # Optional tags (OR logic)
            if optional_tags:
                or_conditions = [Image.tags.contains(tag) for tag in optional_tags]
                query = query.filter(or_(*or_conditions))

            # Exclude tags (NOT logic)
            if exclude_tags:
                for tag in exclude_tags:
                    query = query.filter(~Image.tags.contains(tag))

            # Score range
            if score_range:
                min_score, max_score = score_range
                query = query.filter(
                    and_(
                        Image.score >= min_score,
                        Image.score <= max_score
                    )
                )

            return query.all()
```

## Example 5: Batch Operations and Bulk Updates

Efficient bulk operations for performance.

```python
from sqlalchemy import update

class ImageRepository:
    # ... (previous methods)

    def bulk_update_scores(self, score_updates: dict[int, float]) -> int:
        """
        Bulk update image scores efficiently.

        Args:
            score_updates: Mapping of image_id to new score

        Returns:
            Number of images updated
        """
        with self.session_factory() as session:
            # Use bulk update for better performance
            session.bulk_update_mappings(
                Image,
                [{"id": id, "score": score} for id, score in score_updates.items()]
            )
            session.commit()
            return len(score_updates)

    def bulk_delete_by_ids(self, image_ids: list[int]) -> int:
        """
        Bulk delete images by IDs.

        Args:
            image_ids: List of image primary keys to delete

        Returns:
            Number of images deleted
        """
        with self.session_factory() as session:
            deleted_count = session.query(Image)\
                .filter(Image.id.in_(image_ids))\
                .delete(synchronize_session=False)
            session.commit()
            logger.info(f"Bulk deleted {deleted_count} images")
            return deleted_count

    def recalculate_all_scores(self, score_calculator) -> int:
        """
        Recalculate scores for all images using provided function.

        Args:
            score_calculator: Callable that takes Image and returns float

        Returns:
            Number of images updated
        """
        updated_count = 0

        with self.session_factory() as session:
            # Process in batches to avoid memory issues
            batch_size = 1000
            offset = 0

            while True:
                images = session.query(Image)\
                    .limit(batch_size)\
                    .offset(offset)\
                    .all()

                if not images:
                    break

                # Calculate new scores
                for image in images:
                    image.score = score_calculator(image)
                    updated_count += 1

                session.commit()
                offset += batch_size

        logger.info(f"Recalculated scores for {updated_count} images")
        return updated_count
```

## Example 6: Transaction Management

Complex multi-step transactions with rollback handling.

```python
class ImageRepository:
    # ... (previous methods)

    def move_images_to_project(
        self,
        image_ids: list[int],
        project_id: int
    ) -> tuple[bool, str]:
        """
        Move images to different project atomically.

        All operations succeed or all rollback.

        Args:
            image_ids: List of image IDs to move
            project_id: Target project ID

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            with self.session_factory() as session:
                # Verify project exists
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    return False, f"Project {project_id} not found"

                # Update all images
                updated = session.query(Image)\
                    .filter(Image.id.in_(image_ids))\
                    .update(
                        {"project_id": project_id},
                        synchronize_session=False
                    )

                if updated != len(image_ids):
                    session.rollback()
                    return False, f"Expected {len(image_ids)}, updated {updated}"

                # Update project statistics
                project.image_count += updated
                session.commit()

                logger.info(f"Moved {updated} images to project {project_id}")
                return True, f"Successfully moved {updated} images"

        except SQLAlchemyError as e:
            logger.error(f"Transaction failed: {e}")
            return False, f"Database error: {str(e)}"

    def import_images_with_annotations(
        self,
        image_data: list[dict]
    ) -> tuple[list[Image], list[str]]:
        """
        Import images with their annotations in single transaction.

        Args:
            image_data: List of dicts with 'image' and 'annotations' keys

        Returns:
            Tuple of (imported_images, error_messages)
        """
        imported_images = []
        errors = []

        try:
            with self.session_factory() as session:
                for data in image_data:
                    try:
                        # Create image
                        image = Image(**data['image'])
                        session.add(image)
                        session.flush()  # Get image.id without committing

                        # Create annotations
                        for ann_data in data.get('annotations', []):
                            annotation = Annotation(
                                image_id=image.id,
                                **ann_data
                            )
                            session.add(annotation)

                        imported_images.append(image)

                    except Exception as e:
                        error_msg = f"Failed to import {data.get('image', {}).get('path', 'unknown')}: {e}"
                        errors.append(error_msg)
                        logger.warning(error_msg)
                        # Continue with next image

                # Commit all successful imports
                session.commit()

        except SQLAlchemyError as e:
            logger.error(f"Import transaction failed: {e}")
            errors.append(f"Transaction failed: {e}")
            imported_images = []

        return imported_images, errors
```

## Usage Examples

### Basic CRUD Operations
```python
# Initialize repository
from src.lorairo.database.db_core import get_session_factory
repository = ImageRepository(get_session_factory())

# Create
new_image = Image(path="/path/to/image.jpg", phash="abc123")
saved_image = repository.add(new_image)
print(f"Created image with ID: {saved_image.id}")

# Read
image = repository.get_by_id(saved_image.id)
all_images = repository.get_all(limit=100)

# Update
image.score = 0.95
updated_image = repository.update(image)

# Delete
deleted = repository.delete(saved_image.id)
print(f"Deleted: {deleted}")
```

### Advanced Search
```python
# Type-safe search
criteria = ImageSearchCriteria(
    tags=["anime", "landscape"],
    min_score=0.8,
    min_width=1024,
    limit=50
)
results = repository.search(criteria)
count = repository.count_matching(criteria)
print(f"Found {count} images, showing {len(results)}")
```

### Batch Processing
```python
# Batch add
images = [
    Image(path=f"/image_{i}.jpg", phash=f"hash{i}")
    for i in range(100)
]
added_images = repository.batch_add(images)
print(f"Added {len(added_images)} images")

# Bulk update
score_updates = {img.id: 0.9 for img in added_images[:10]}
updated_count = repository.bulk_update_scores(score_updates)
print(f"Updated {updated_count} scores")
```
