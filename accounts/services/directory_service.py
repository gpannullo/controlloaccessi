from abc import ABC, abstractmethod


class DirectoryService(ABC):
    """
    Interfaccia astratta per tutti i servizi di directory.

    Tutta l'applicazione comunica con questa interfaccia
    senza conoscere il provider sottostante.
    """

    @abstractmethod
    def authenticate(self, username: str, password: str) -> bool:
        """Autentica un utente."""
        raise NotImplementedError

    @abstractmethod
    def get_groups(self) -> list[dict]:
        """Restituisce i gruppi presenti nella directory."""
        raise NotImplementedError

    @abstractmethod
    def get_users(self) -> list[dict]:
        """Restituisce tutti gli utenti."""
        raise NotImplementedError

    @abstractmethod
    def get_user_groups(self, username: str) -> list[str]:
        """Restituisce i gruppi di un utente."""
        raise NotImplementedError