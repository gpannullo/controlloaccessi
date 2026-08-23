from common.module_access import (
    DirectoryAdministrationAccessMixin,
    DirigenzaAccessMixin,
    module_required,
)


GRUPPI_DIRIGENZA = {
    "Dirigenti",
    "Funzionari_EQ",
}


def puo_accedere_area_dirigenza(user):
    return DirigenzaAccessMixin.has_module_access(user)


dirigenza_required = module_required(DirigenzaAccessMixin)


def puo_amministrare_directory(user):
    return DirectoryAdministrationAccessMixin.has_module_access(user)


directory_admin_required = module_required(DirectoryAdministrationAccessMixin)
