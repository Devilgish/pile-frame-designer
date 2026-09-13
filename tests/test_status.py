"""Статус проверки: коэффициент использования → проходит / предупреждение / не проходит."""

import pytest

from pile_frame.status import Status, classify


@pytest.mark.parametrize(
    ("utilization", "status"),
    [
        (0.0, Status.OK),
        (0.89, Status.OK),
        (0.90, Status.WARNING),  # запас меньше 10 % — предупреждение
        (1.00, Status.WARNING),  # ровно на пределе ещё проходит
        (1.01, Status.FAIL),
    ],
)
def test_utilization_is_classified_with_ten_percent_warning_margin(utilization, status):
    assert classify(utilization) is status


def test_every_status_has_text_and_icon_not_only_color():
    for status in Status:
        assert status.label
        assert status.icon in {"check", "alert", "cross"}
    assert len({s.icon for s in Status}) == len(Status)
