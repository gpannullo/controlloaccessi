from .directory_service import DirectoryService


class LDAPDirectoryService(DirectoryService):

    def authenticate(self, username, password):
        raise NotImplementedError()

    def get_groups(self):
        raise NotImplementedError()

    def get_users(self):
        raise NotImplementedError()

    def get_user_groups(self, username):
        raise NotImplementedError()