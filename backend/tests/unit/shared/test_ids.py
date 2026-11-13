from uuid import UUID

from workhub.shared.api import new_id


def test_new_id_returns_uuid4() -> None:
    identifier = new_id()
    assert isinstance(identifier, UUID)
    assert identifier.version == 4


def test_new_id_is_unique() -> None:
    identifiers = {new_id() for _ in range(1000)}
    assert len(identifiers) == 1000
