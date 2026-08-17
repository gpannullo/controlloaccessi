from dataclasses import dataclass, field


@dataclass
class DirectorySnapshot:
    users: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    generated_at: str = ""