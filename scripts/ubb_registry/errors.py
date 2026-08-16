"""Registry domain exceptions."""


class RegistryError(Exception):
    """Base class for expected registry failures."""


class DuplicateIdError(RegistryError):
    pass


class UnknownReferenceError(RegistryError):
    pass


class InvalidManifestError(RegistryError):
    pass


class UnsupportedEndpointTypeError(RegistryError):
    pass
