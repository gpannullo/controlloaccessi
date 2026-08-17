from enum import Enum


class ApplicationRole(str, Enum):

    ADMIN = "ADMIN"

    PORTINERIA = "PORTINERIA"

    RESPONSABILE_UFFICIO = "RESPONSABILE_UFFICIO"

    OPERATORE_UFFICIO = "OPERATORE_UFFICIO"

    AUDITOR = "AUDITOR"