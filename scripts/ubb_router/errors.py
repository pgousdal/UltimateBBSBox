"""Session router domain exceptions."""


class RouterError(Exception):
    pass


class AuthorizationError(RouterError):
    pass


class UnknownServiceError(RouterError):
    pass


class InvalidSessionTransitionError(RouterError):
    pass


class SessionNotFoundError(RouterError):
    pass


class SessionBusyError(RouterError):
    pass


class TransportError(RouterError):
    pass


class UnsupportedTransportError(TransportError):
    pass
