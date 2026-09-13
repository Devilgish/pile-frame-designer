"""Решатель перекрёстной системы балок (грильяжа).

Эталоны — справочные коэффициенты для неразрезных балок постоянной жёсткости
при равномерной нагрузке и ручной расчёт простых схем.
"""

import pytest

from pile_frame.grillage import Grillage

EI = 2.06e5 * 240.7e4  # Н·мм², значение не влияет на усилия в статически неопределимой балке
Q = 10.0  # Н/мм
L = 3000.0  # мм


def test_two_span_continuous_beam_matches_handbook_coefficients():
    g = Grillage()
    a, b, c = g.node(0, 0, support=True), g.node(L, 0, support=True), g.node(2 * L, 0, support=True)
    ab, bc = g.beam(a, b, EI), g.beam(b, c, EI)
    g.line_load(ab, Q)
    g.line_load(bc, Q)

    result = g.solve()

    assert result.reaction(a) == pytest.approx(0.375 * Q * L)
    assert result.reaction(b) == pytest.approx(1.25 * Q * L)
    assert result.reaction(c) == pytest.approx(0.375 * Q * L)
    assert result.end_moments(ab)[1] == pytest.approx(-Q * L**2 / 8)  # момент над опорой b


def test_three_span_continuous_beam_matches_handbook_coefficients():
    g = Grillage()
    nodes = [g.node(i * L, 0, support=True) for i in range(4)]
    beams = [g.beam(nodes[i], nodes[i + 1], EI) for i in range(3)]
    for beam in beams:
        g.line_load(beam, Q)

    result = g.solve()

    assert result.reaction(nodes[0]) == pytest.approx(0.4 * Q * L)
    assert result.reaction(nodes[1]) == pytest.approx(1.1 * Q * L)
    assert result.end_moments(beams[0])[1] == pytest.approx(-0.1 * Q * L**2)


def test_two_crossing_beams_share_a_point_load_equally():
    # Две однопролётные балки 4 м крест-накрест, груз P в общем узле посередине.
    # Жёсткости равны → каждая берёт P/2: реакции P/4, момент (P/2)·L/4.
    span, force = 4000.0, 10_000.0
    g = Grillage()
    west, east = g.node(0, 2000, support=True), g.node(span, 2000, support=True)
    south, north = g.node(2000, 0, support=True), g.node(2000, span, support=True)
    middle = g.node(2000, 2000)
    along_x = [g.beam(west, middle, EI), g.beam(middle, east, EI)]
    g.beam(south, middle, EI)
    g.beam(middle, north, EI)
    g.point_load(middle, force)

    result = g.solve()

    for support in (west, east, south, north):
        assert result.reaction(support) == pytest.approx(force / 4)
    assert result.end_moments(along_x[0])[1] == pytest.approx(force / 2 * span / 4)
