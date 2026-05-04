"""
Unified path validation for file operations.

Provides security checks for all file operation endpoints
to prevent path traversal and unauthorized access.
"""
import os
from pathlib import Path
from typing import List, Optional, Tuple
from fastapi import HTTPException


class PathValidator:
    """
    Validates file paths for security.

    Prevents:
    - Path traversal attacks (../)
    - Access to files outside allowed directories
    - Symlink attacks
    """

    def __init__(self, allowed_roots: List[str]):
        """
        Initialize validator with allowed root directories.

        Args:
            allowed_roots: List of directory paths that are allowed for file operations
        """
        self.allowed_roots = [
            os.path.realpath(root) if os.path.exists(root) else root
            for root in allowed_roots
        ]

    def _normalize_path(self, path: str) -> str:
        """Normalize a path to its canonical form."""
        return os.path.realpath(path)

    def _is_safe_filename(self, filename: str) -> bool:
        """Check if a filename is safe (no path separators)."""
        # Block path traversal attempts
        if '..' in filename:
            return False
        if '/' in filename or '\\' in filename:
            return False
        # Block null bytes
        if '\x00' in filename:
            return False
        return True

    def _is_within_allowed_root(self, path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a path is within an allowed root directory.

        Returns:
            (is_allowed, matched_root)
        """
        normalized = self._normalize_path(path)

        for root in self.allowed_roots:
            if os.path.exists(root):
                real_root = os.path.realpath(root)
                if normalized.startswith(real_root + os.sep) or normalized == real_root:
                    return True, root

        return False, None

    def validate_path(self, path: str, must_exist: bool = True) -> Path:
        """
        Validate a file path for security.

        Args:
            path: Path to validate
            must_exist: If True, file must exist

        Returns:
            Normalized path

        Raises:
            HTTPException: If path is invalid or not allowed
        """
        # Check for path traversal
        if '..' in path:
            raise HTTPException(
                status_code=400,
                detail="Path traversal not allowed"
            )

        # Normalize the path
        try:
            normalized = self._normalize_path(path)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid path"
            )

        # Check if within allowed roots
        is_allowed, _ = self._is_within_allowed_root(normalized)
        if not is_allowed:
            raise HTTPException(
                status_code=403,
                detail="Access denied: path outside allowed directories"
            )

        # Check existence if required
        if must_exist and not os.path.exists(normalized):
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )

        return Path(normalized)

    def validate_filename(self, filename: str) -> str:
        """
        Validate a filename for security.

        Args:
            filename: Filename to validate

        Returns:
            Safe filename

        Raises:
            HTTPException: If filename is invalid
        """
        if not self._is_safe_filename(filename):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename: contains path separators"
            )

        return filename

    def resolve_safe_path(self, filename: str, directory: str) -> Path:
        """
        Resolve a filename to a safe path within a directory.

        Args:
            filename: Filename to resolve
            directory: Target directory

        Returns:
            Resolved path

        Raises:
            HTTPException: If path is invalid
        """
        # Validate filename
        self.validate_filename(filename)

        # Normalize directory
        if not os.path.exists(directory):
            raise HTTPException(
                status_code=400,
                detail=f"Directory does not exist: {directory}"
            )

        real_dir = os.path.realpath(directory)

        # Construct full path
        full_path = os.path.join(real_dir, filename)
        normalized = self._normalize_path(full_path)

        # Ensure the resolved path is still within the directory
        if not normalized.startswith(real_dir + os.sep):
            raise HTTPException(
                status_code=403,
                detail="Resolved path escapes directory"
            )

        return Path(normalized)

    def is_safe_to_delete(self, path: str) -> bool:
        """
        Check if a path is safe to delete.

        Additional checks for deletion:
        - Not a critical system file
        - Not a directory (unless explicitly allowed)

        Args:
            path: Path to check

        Returns:
            True if safe to delete
        """
        try:
            normalized = self._normalize_path(path)
        except Exception:
            return False

        # Must be within allowed roots
        is_allowed, _ = self._is_within_allowed_root(normalized)
        if not is_allowed:
            return False

        # Must be a file, not directory (for safety)
        if os.path.isdir(normalized):
            return False

        return True


def get_default_allowed_roots() -> List[str]:
    """
    Get default allowed root directories based on environment variables.

    Returns:
        List of allowed directory paths
    """
    roots = []

    # App data directory
    app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if app_data_dir:
        roots.append(app_data_dir)

    # Clips directory
    clips_dir = os.environ.get('CLIP_CLIPS_DIR')
    if clips_dir:
        roots.append(clips_dir)
    elif app_data_dir:
        roots.append(os.path.join(app_data_dir, 'clips'))

    # Uploads directory
    roots.append('uploads')

    # Static directory
    static_dir = os.environ.get('CLIP_STATIC_DIR')
    if static_dir:
        roots.append(static_dir)
    else:
        roots.append('static')

    # Fonts directory
    fonts_dir = os.environ.get('CLIP_FONTS_DIR')
    if fonts_dir:
        roots.append(fonts_dir)
    elif app_data_dir:
        roots.append(os.path.join(app_data_dir, 'fonts'))

    # Thumbnails directory
    thumbnails_dir = os.environ.get('CLIP_THUMBNAILS_DIR')
    if thumbnails_dir:
        roots.append(thumbnails_dir)
    elif app_data_dir:
        roots.append(os.path.join(app_data_dir, 'thumbnails'))

    return roots


# Global validator instance with default allowed roots
path_validator = PathValidator(get_default_allowed_roots())
