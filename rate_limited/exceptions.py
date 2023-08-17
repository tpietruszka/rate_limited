class BaseException(Exception):
    pass


class ValidationError(BaseException):
    """
    API response failed the user-provided validation

    Store the invalid value for post-hoc inspection/debugging
    """

    def __init__(self, message, call, value, *args, **kwargs):
        super().__init__(message, *args, **kwargs)
        self.call = call
        self.value = value
