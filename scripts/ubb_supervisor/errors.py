"""Lifecycle supervisor domain exceptions."""


class SupervisorError(Exception):
    pass


class InvalidTransitionError(SupervisorError):
    pass


class ServiceNotFoundError(SupervisorError):
    pass


class ServiceBusyError(SupervisorError):
    pass


class ReadinessTimeoutError(SupervisorError):
    pass


class RestartLimitExceededError(SupervisorError):
    pass


class MaintenanceError(SupervisorError):
    pass


class DriverError(SupervisorError):
    pass
