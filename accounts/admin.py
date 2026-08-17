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
