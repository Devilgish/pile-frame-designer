"""Оптимизация по массе металла: перебор раскладки, профилей и усилений с отсечением."""

import pytest

from pile_frame.design import Project, analyze
from pile_frame.optimizer import explain, optimize
from pile_frame.sections import TUBE_120x60x4, TUBE_120x120x5

SECTIONS = (TUBE_120x60x4, TUBE_120x120x5)


def _small(**changes):
    # 4000 × 2500 на сваях через 2000, лист 24 мм, 4 кПа: небольшой план для полного перебора.
    params = {"width_mm": 4000, "length_mm": 2500, "pile_step_mm": 2000, "live_load_kpa": 4.0}
    return Project(**{**params, **changes})


def _signature(variant):
    p = variant.project
    return (
        round(variant.mass_kg, 6),
        p.sheet_long_side,
        p.sheet_offset_mm,
        p.perimeter_section.name,
        p.internal_section.name,
        p.upgrades,
    )


def test_every_variant_passes_all_checks_and_they_are_sorted_by_mass():
    result = optimize(_small(), SECTIONS, step_mm=500, keep=5)

    assert 1 <= len(result.variants) <= 5
    masses = [v.mass_kg for v in result.variants]
    assert masses == sorted(masses)
    for variant in result.variants:
        design = variant.design
        assert design.failing_members() == []
        assert all(cell.check.passed for cell in design.board_cells)
        assert all(w.check.utilization <= 1 for w in design.welds)


def test_pruned_search_finds_the_same_best_variants_as_full_enumeration():
    pruned = optimize(_small(), SECTIONS, step_mm=500, keep=3)
    full = optimize(_small(), SECTIONS, step_mm=500, keep=3, prune=False)

    assert [_signature(v) for v in pruned.variants] == [_signature(v) for v in full.variants]
    assert pruned.analysed < full.analysed  # отсечение экономит расчёты


def test_failing_beams_are_upgraded_point_by_point_when_that_is_lightest():
    # 8000 × 4000, сваи через 3000, 8 кПа, только по сваям: 588,88 кг, три балки 120×60 не
    # проходят (1,144). Лучше всего облегчить периметр до 120×60 (он проходит):
    # −24 м · (17,55 − 10,48) = −169,68 кг, и точечно усилить три балки до 120×120:
    # +3 · 2,6667 · 7,07 = +56,56 кг → 475,76 кг. Только усиления без смены периметра — 645,44.
    heavy = Project(
        width_mm=8000, length_mm=4000, pile_step_mm=3000, live_load_kpa=8.0, sheet_joints=False
    )

    variants = optimize(heavy, SECTIONS, keep=3).variants

    best = variants[0]
    assert best.design.failing_members() == []
    assert best.project.perimeter_section == TUBE_120x60x4
    assert len(best.project.upgrades) == 3
    assert best.mass_kg == pytest.approx(588.88 - 169.68 + 56.56, abs=0.05)
    assert any(v.mass_kg == pytest.approx(645.44, abs=0.05) for v in variants)


def test_progress_is_reported_and_the_search_can_be_cancelled():
    seen = []

    result = optimize(
        _small(),
        SECTIONS,
        step_mm=500,
        progress=lambda done, total: seen.append((done, total)),
        cancelled=lambda: len(seen) >= 3,
    )

    assert result.cancelled
    assert [done for done, _ in seen] == sorted(done for done, _ in seen)
    assert all(total == seen[0][1] for _, total in seen)


def test_explanation_compares_the_variant_with_the_current_project():
    project = _small()
    result = optimize(project, SECTIONS, step_mm=500, keep=2)

    lines = explain(result.variants[0], analyze(project), result.variants[1:])

    assert any(
        "кг" in line and ("легче" in line or "тяжелее" in line or "совпадает" in line)
        for line in lines
    )
    assert any("Следующий вариант" in line for line in lines)
