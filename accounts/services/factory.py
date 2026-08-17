from .active_directory_service import ActiveDirectoryService


class DirectoryFactory:
    @staticmethod
    def get_service():
        return ActiveDirectoryService()

    @staticmethod
    def create():
        return DirectoryFactory.get_service()