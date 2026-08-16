"""Runtime adapter domain exceptions."""


class RuntimeAdapterError(Exception):
    pass


class UnknownRuntimeError(RuntimeAdapterError):
    pass


class UnsupportedRuntimeError(RuntimeAdapterError):
    pass


class RuntimeConfigError(RuntimeAdapterError):
    pass


class RuntimeStartError(RuntimeAdapterError):
    pass


class RuntimeStopError(RuntimeAdapterError):
    pass


class RuntimeStreamError(RuntimeAdapterError):
    pass
