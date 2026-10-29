from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class TipoProtocollo(str, Enum):
    ARRIVO = 'arrivo'
    PARTENZA = 'partenza'
    INTERNO = 'interno'

    def __str__(self):
        return self.value


@dataclass(frozen=True)
class Documento:
    nome: str
    contenuto: bytes = field(repr=False)
    marca_segnatura: bool = False


@dataclass(frozen=True)
class Soggetto:
    denominazione: str
    codice: str = ''
    codice_fiscale: str = ''
    email: str = ''
    indirizzo: str = ''
    cap: str = ''
    citta: str = ''
    provincia: str = ''


@dataclass(frozen=True)
class Firmatario:
    codice: str
    ufficio: str


@dataclass(frozen=True)
class Trasmissione:
    ufficio: str
    soggetto: str = ''
    gestione: bool = False
    responsabile: bool = False


@dataclass(frozen=True)
class RichiestaProtocollo:
    oggetto: str
    tipo: TipoProtocollo
    documento: Documento
    classificazione: str
    ufficio: str = ''
    firmatari: tuple[Firmatario, ...] = ()
    mittenti: tuple[Soggetto, ...] = ()
    destinatari: tuple[Soggetto, ...] = ()
    trasmissioni: tuple[Trasmissione, ...] = ()
    riservato: bool = True
    allegati: tuple[Documento, ...] = ()


@dataclass(frozen=True)
class EsitoProtocollo:
    identificativo: str
    anno: str
    numero: str
    tipo: str
    data: str
    segnatura: str
    avviso: bool = False


class ErroreProtocollo(Exception):
    """Messaggi sicuri: non includere SOAP, credenziali o contenuto documenti."""


class ConfigurazioneProtocolloError(ErroreProtocollo):
    pass


class ValidazioneProtocolloError(ErroreProtocollo):
    pass


class EsitoIncertoError(ErroreProtocollo):
    """Il server potrebbe aver registrato il documento: vietato reinviare."""


class InvioBloccatoError(ErroreProtocollo):
    pass


class ProtocolloBackend(ABC):
    @abstractmethod
    def valida(self, richiesta: RichiestaProtocollo) -> None:
        """Validazione locale senza aprire connessioni."""

    @abstractmethod
    def protocolla(self, richiesta: RichiestaProtocollo) -> EsitoProtocollo:
        """Una sola registrazione; mai retry automatico dopo l'invio."""
