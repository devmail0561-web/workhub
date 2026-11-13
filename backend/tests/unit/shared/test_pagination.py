import pytest

from workhub.shared.api import Page, PageRequest, ValidationError, paginate


def test_page_request_defaults() -> None:
    request = PageRequest()
    assert request.limit == 50
    assert request.offset == 0


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_page_request_rejects_invalid_limit(limit: int) -> None:
    with pytest.raises(ValidationError):
        PageRequest(limit=limit)


def test_page_request_rejects_negative_offset() -> None:
    with pytest.raises(ValidationError):
        PageRequest(offset=-1)


def test_paginate_returns_window_and_navigation() -> None:
    page = paginate(list(range(1, 11)), PageRequest(limit=3, offset=0))

    assert page.items == (1, 2, 3)
    assert page.total == 10
    assert page.has_next
    assert page.next_offset == 3


def test_paginate_last_window() -> None:
    page = paginate(list(range(1, 11)), PageRequest(limit=3, offset=9))

    assert page.items == (10,)
    assert not page.has_next
    assert page.next_offset is None


def test_paginate_beyond_total_returns_empty() -> None:
    page = paginate([1, 2, 3], PageRequest(limit=10, offset=20))

    assert page.items == ()
    assert not page.has_next
    assert page.next_offset is None


def test_paginate_accepts_explicit_total() -> None:
    page = paginate([1, 2, 3], PageRequest(limit=3, offset=0), total=10)

    assert page.total == 10
    assert page.has_next


def test_page_empty() -> None:
    page = Page[int].empty(PageRequest(limit=5, offset=2))

    assert page.items == ()
    assert page.total == 0
    assert page.limit == 5
    assert page.offset == 2
    assert not page.has_next


def test_page_validates_fields() -> None:
    with pytest.raises(ValidationError):
        Page[int](items=(), total=-1, limit=10, offset=0)
    with pytest.raises(ValidationError):
        Page[int](items=(), total=0, limit=0, offset=0)
    with pytest.raises(ValidationError):
        Page[int](items=(), total=0, limit=10, offset=-1)
