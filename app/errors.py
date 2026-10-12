class FileError(Exception):
    """A problem with the uploaded file that the client can fix."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
