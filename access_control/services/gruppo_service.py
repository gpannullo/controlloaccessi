from django.contrib.auth.models import Group

from access_control.models import GruppoOrganizzativo


class GruppoService:

    def sync(self, directory_service):

        groups = directory_service.get_groups()

        for group_name in groups:

            django_group, _ = Group.objects.get_or_create(
                name=group_name
            )

            GruppoOrganizzativo.objects.get_or_create(
                directory_name=group_name,
                defaults={
                    "nome": group_name,
                    "django_group": django_group
                }
            )