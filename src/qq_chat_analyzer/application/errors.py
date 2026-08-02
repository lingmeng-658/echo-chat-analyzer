"""Stable, privacy-safe errors for application use cases."""

from __future__ import annotations


class ApplicationServiceError(Exception):
    """Base error exposed by the application layer."""

    code = "application_error"
    public_message = "The application operation failed."

    def __init__(self) -> None:
        super().__init__(self.public_message)


class InvalidAnalysisRequest(ApplicationServiceError):
    """Raised when an analysis request violates the use-case contract."""

    code = "invalid_request"
    public_message = "The analysis request is invalid."


class InputPathNotFound(ApplicationServiceError):
    """Raised when the requested local input cannot be found."""

    code = "input_not_found"
    public_message = "The input path was not found."


class NoSupportedInput(ApplicationServiceError):
    """Raised when an input contains no supported local chat files."""

    code = "no_supported_input"
    public_message = "No supported input was found."


class ArtifactGenerationFailed(ApplicationServiceError):
    """Raised when local result artifacts cannot be generated."""

    code = "artifact_generation_failed"
    public_message = "Artifact generation failed."
