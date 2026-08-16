"""Domain errors for museum integration orchestration."""


class IntegrationError(Exception):
    """Expected integration workflow failure."""


class UnknownIntegrationError(IntegrationError):
    pass


class ArtifactRequiredError(IntegrationError):
    pass


class InstallError(IntegrationError):
    pass

