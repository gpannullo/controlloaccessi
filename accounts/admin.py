from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "tipo_attivita",
        "stato_presenza",
        "is_active",
        "is_staff",
    )

    list_filter = (
        "tipo_attivita",
        "stato_presenza",
        "is_active",
        "is_staff",
    )

    readonly_fields = (
        "last_login",
        "date_joined",
        "presenza_verificata_il",
        "presenza_fonte",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Organizzazione",
            {
                "fields": (
                    "tipo_attivita",
                    "stato_presenza",
                    "presenza_verificata_il",
                    "presenza_fonte",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Organizzazione",
            {
                "fields": (
                    "tipo_attivita",
                    "stato_presenza",
                )
            },
        ),
    )

    actions = (
        "imposta_amministrativisti",
        "imposta_sportellisti",
        "imposta_tecnici",
        "imposta_disuso",
    )

    @admin.action(
        description="Imposta come Amministrativista",
    )
    def imposta_amministrativisti(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.AMMINISTRATIVISTA,
        )

    @admin.action(
        description="Imposta come Sportellista",
    )
    def imposta_sportellisti(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.SPORTELLISTA,
        )

    @admin.action(
        description="Imposta come Tecnico",
    )
    def imposta_tecnici(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.TECNICO,
        )

    @admin.action(
        description="Imposta come Disuso",
    )
    def imposta_disuso(self, request, queryset):
        queryset.update(
            tipo_attivita=CustomUser.TipoAttivita.DISUSO,
        )
