from django.contrib.auth.models import Group
from ldap3 import Server, Connection, ALL
from django.contrib.auth import get_user_model
from access_control.models import Ufficio

User = get_user_model()


class ActiveDirectoryAuth:
    def authenticate(self, request, username=None, password=None):
        print("Verifica server")
        server = Server('ldap://192.168.15.100', get_info=ALL)

        user_dn = f"COMUNEAVERSA\\{username}"

        try:
            conn = Connection(server, user=user_dn, password=password, auto_bind=True)

            if not conn.bind():
                print("Bind fallito")
                return None

            conn.search(
                search_base="DC=COMUNEAVERSA,DC=local",
                search_filter=f"(sAMAccountName={username})",
                attributes=['memberOf', 'mail', 'givenName', 'sn']
            )

            if not conn.entries:
                return None

            entry = conn.entries[0]

            # crea/aggiorna utente Django
            user, created = User.objects.get_or_create(username=username, )

            user.email = entry.mail.value if hasattr(entry, "mail") else ""
            user.first_name = entry.givenName.value if hasattr(entry, "givenName") else ""
            user.last_name = entry.sn.value if hasattr(entry, "sn") else ""
            ad_groups = []
            for g in entry.memberOf.values:
                cn = g.split(",")[0].replace("CN=", "")
                ad_groups.append(cn)
            print(ad_groups)
            if "Administrators" in ad_groups:
                user.is_superuser = True
                user.is_staff = True

            user.set_unusable_password()
            user.save()

            user.groups.clear()
            for group_name in ad_groups:
                # 1. crea gruppo Django (tecnico)
                group, _ = Group.objects.get_or_create(name=group_name)
                user.groups.add(group)

                # 2. crea o aggiorna ufficio (logico PA)
                ufficio, created = Ufficio.objects.get_or_create(
                    ldap_group=group_name,
                    crea_ufficio=True,
                    defaults={
                        "nome": group_name,
                        "descrizione": f"Ufficio sincronizzato da Active Directory: {group_name}"
                    }
                )

            return user

        except Exception as e:
            print("LDAP ERROR:", e)
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
