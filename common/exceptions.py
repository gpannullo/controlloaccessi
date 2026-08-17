class BusinessException(Exception):
    """Eccezione base dell'applicazione."""


class DirectoryException(BusinessException):
    """Errore durante la comunicazione con la directory."""


class OfficeClosedException(BusinessException):
    """L'ufficio non riceve pubblico."""


class AppointmentConflictException(BusinessException):
    """Esiste già un appuntamento nello stesso slot."""


class VisitorAlreadyInsideException(BusinessException):
    """Il visitatore risulta già presente nella struttura."""


class TicketPrinterException(BusinessException):
    """Errore durante la stampa del ticket."""
