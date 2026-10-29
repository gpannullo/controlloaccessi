from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, RequestFactory
from dashboard import directory_admin_views as views


class RemovalTests(SimpleTestCase):
    def call_action(self, action, **data):
        request = RequestFactory().post('/', {'azione': action, **data})
        request.user = SimpleNamespace(username='operator')
        function = views.directory_action
        while hasattr(function, '__wrapped__'):
            function = function.__wrapped__
        return function(request, 48)

    def setUp(self):
        self.user = MagicMock(pk=48, username='target')
        self.patches = [patch.object(views, 'get_object_or_404', return_value=self.user),
                        patch.object(views, 'DirectoryAdminService'),
                        patch.object(views, 'messages'), patch.object(views, 'AuditService'),
                        patch.object(views, 'redirect')]
        self.lookup, self.service, self.messages, _, _ = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def test_remove_group_updates_local_after_ad(self):
        with patch.object(views.Group.objects, 'filter') as groups:
            groups.return_value.distinct.return_value = [123]
            self.call_action('rimuovi_gruppo_ad', gruppo_ad='Test')
        self.service.return_value.rimuovi_da_gruppo.assert_called_once_with('target', 'Test')
        self.user.groups.remove.assert_called_once_with(123)

    def test_ad_failure_preserves_local_membership(self):
        self.service.return_value.rimuovi_da_gruppo.side_effect = RuntimeError('AD unavailable')
        self.call_action('rimuovi_gruppo_ad', gruppo_ad='Test')
        self.user.groups.remove.assert_not_called()
        self.messages.error.assert_called_once()

    def test_office_removal_scoped_and_no_ad(self):
        assignment = MagicMock()
        self.lookup.side_effect = [self.user, assignment]
        self.call_action('elimina_ufficio', assegnazione='7')
        self.assertEqual(self.lookup.call_args.kwargs, {'pk': '7', 'utente': self.user})
        assignment.delete.assert_called_once()
        self.service.assert_not_called()
        self.user.groups.remove.assert_not_called()
