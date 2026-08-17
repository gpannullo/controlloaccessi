from dataclasses import dataclass


@dataclass
class SyncResult:

    created: int = 0
    updated: int = 0
    disabled: int = 0
    skipped: int = 0
    errors: int = 0

    def add_created(self):
        self.created += 1

    def add_updated(self):
        self.updated += 1

    def add_disabled(self):
        self.disabled += 1