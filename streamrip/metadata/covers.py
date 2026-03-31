class Covers:
    def __init__(self, path: str | None = None, url: str | None = None):
        self.path = path
        self.url = url

    def empty(self) -> bool:
        return self.url is None

    @classmethod
    def from_deezer(cls, resp):
        return cls(url=resp["cover_big"])

    def __repr__(self):
        return f"Covers({self.url})"
