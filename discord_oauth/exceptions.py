class InvalidGrant(Exception):
    """An Exception raised when grant is invalid."""


class Unauthorized(Exception):
    """An Exception raised when authorization is invalid."""


class RateLimited(Exception):
    """An Exception raised when rate limit is reached."""


class AccessTokenExpired(Exception):
    """An Exception raised when access token is expired."""


class UnkownUser(Exception):
    """An Exception raised when user is unknown."""


class InvalidToken(Exception):
    """An Exception raised when an invalid token is used."""


class InvalidScope(Exception):
    """An Exception raised when an invalid scope is used."""
