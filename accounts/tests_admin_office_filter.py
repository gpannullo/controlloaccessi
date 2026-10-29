from unittest.mock import Mock, patch

from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from accounts.admin import CustomUserAdmin, UfficioUtenteFilter
from accounts.models import CustomUser


class OfficeFilterTests(SimpleTestCase):
    def make_filter(self, value=None):
        params = {} if value is None else {"ufficio": [value]}
        with patch.object(UfficioUtenteFilter, "lookups", return_value=[(1, "Anagrafe")]):
            return UfficioUtenteFilter(
                RequestFactory().get("/admin/accounts/customuser/"),
                params, CustomUser, CustomUserAdmin(CustomUser, admin.site),
            )

    def test_registered(self):
        self.assertIn(UfficioUtenteFilter, CustomUserAdmin.list_filter)

    def test_without_selection_keeps_queryset(self):
        queryset = Mock()
        self.assertIs(self.make_filter().queryset(None, queryset), queryset)

    def test_selected_office_requires_active_assignment(self):
        queryset = Mock()
        result = self.make_filter("1").queryset(None, queryset)
        queryset.filter.assert_called_once_with(
            assegnazioni_ufficio__ufficio_id=1, assegnazioni_ufficio__attiva=True,
        )
        self.assertIs(result, queryset.filter.return_value.distinct.return_value)

    def test_invalid_selection(self):
        queryset = Mock()
        self.assertIs(self.make_filter("invalid").queryset(None, queryset), queryset.none.return_value)
