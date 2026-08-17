from django.contrib.auth.models import Group
from access_control.models import GruppoOrganizzativo

from .sync_result import SyncResult


class GroupSyncService:

    MAX_GROUP_NAME_LENGTH = 150

    def _safe_name(self, description, group_name):
        """
        Restituisce un nome compatibile con il limite DB.

        La description AD può superare i 150 caratteri e può anche
        essere duplicata tra gruppi diversi. In questi casi si usa
        il CN/directory_name come nome visualizzato, che è l'identità
        più stabile del gruppo.
        """
        description = (description or "").strip()
        group_name = (group_name or "").strip()

        if (
            description
            and len(description) <= self.MAX_GROUP_NAME_LENGTH
            and not GruppoOrganizzativo.objects.filter(
                nome=description
            ).exists()
        ):
            return description

        return group_name[:self.MAX_GROUP_NAME_LENGTH]

    def sync(self, snapshot):
        result = SyncResult()

        for group_data in snapshot.groups:
            group_name = (group_data["name"] or "").strip()
            group_sid = group_data.get("sid", "")
            description = group_data.get("description") or ""

            # django.contrib.auth.models.Group.name è max_length=150.
            django_group_name = group_name[:self.MAX_GROUP_NAME_LENGTH]

            django_group, _ = Group.objects.get_or_create(
                name=django_group_name,
            )

            gruppo = None

            if group_sid:
                gruppo = GruppoOrganizzativo.objects.filter(
                    directory_sid=group_sid,
                ).first()

            if gruppo is None:
                gruppo = GruppoOrganizzativo.objects.filter(
                    directory_name=group_name[:self.MAX_GROUP_NAME_LENGTH],
                ).first()

            if gruppo is None:
                safe_name = self._safe_name(
                    description,
                    group_name,
                )

                GruppoOrganizzativo.objects.create(
                    nome=safe_name,
                    directory_name=(
                        group_name[:self.MAX_GROUP_NAME_LENGTH]
                    ),
                    directory_sid=group_sid or None,
                    django_group=django_group,
                    attivo=True,
                    sincronizzato=True,
                    note=(
                        description
                        if description != safe_name
                        else ""
                    ),
                )

                result.add_created()
                continue

            changed = False

            safe_directory_name = (
                group_name[:self.MAX_GROUP_NAME_LENGTH]
            )

            if gruppo.directory_name != safe_directory_name:
                gruppo.directory_name = safe_directory_name
                changed = True

            if gruppo.directory_sid != (group_sid or None):
                gruppo.directory_sid = group_sid or None
                changed = True

            if gruppo.django_group_id != django_group.id:
                gruppo.django_group = django_group
                changed = True

            if not gruppo.sincronizzato:
                gruppo.sincronizzato = True
                changed = True

            if not gruppo.attivo:
                gruppo.attivo = True
                changed = True

            if changed:
                gruppo.save()
                result.add_updated()
            else:
                result.skipped += 1

        return result
