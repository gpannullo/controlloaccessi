from common.module_access import (
    PortineriaAccessMixin,
    UfficiAccessMixin,
    module_required,
)


def is_portineria_user(user):
    """
    Restituisce True se l'utente appartiene
    al gruppo configurato come Portineria.
    """

    return PortineriaAccessMixin.has_module_access(user)


def portineria_required(view_func):
    """
    Consente l'accesso alle funzioni di portineria.

    I superuser possono accedere per amministrazione
    e assistenza.
    """

    return module_required(PortineriaAccessMixin)(view_func)


def ufficio_required(view_func):
    """
    Impedisce agli utenti della portineria di accedere
    alle pagine operative degli uffici.

    L'appartenenza al gruppo Portineria prevale sulle
    eventuali altre associazioni organizzative.
    """

    return module_required(UfficiAccessMixin)(view_func)
