"""Перекрёстная система балок (грильяж) методом конечных элементов.

Балки лежат в одной горизонтальной плоскости и идут вдоль осей X или Y. В каждом узле три
неизвестных: прогиб w (вниз положительный), поворот балок вдоль X и поворот балок вдоль Y.
Кручение балок не учитывается (в запас), поэтому повороты разных направлений независимы.
Опоры — шарнирные: w = 0, повороты свободны. Единицы: мм, Н.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

TOLERANCE_MM = 1e-6
#: Узлы и веса квадратуры Гаусса: точна для нагрузки, линейной по длине участка.
_GAUSS_POINTS, _GAUSS_WEIGHTS = np.polynomial.legendre.leggauss(6)


@dataclass
class _Beam:
    i: int
    j: int
    ei: float
    axis: int  # 0 — вдоль X, 1 — вдоль Y
    loads: list[tuple[float, float, float, float]] = field(default_factory=list)  # s0, s1, q0, q1

    def length(self, nodes: list[tuple[float, float]]) -> float:
        return math.dist(nodes[self.i], nodes[self.j])


def _stiffness(ei: float, length: float) -> np.ndarray:
    """Матрица жёсткости балочного элемента: [w_i, θ_i, w_j, θ_j]."""
    lg = length
    return (ei / lg**3) * np.array(
        [
            [12, 6 * lg, -12, 6 * lg],
            [6 * lg, 4 * lg**2, -6 * lg, 2 * lg**2],
            [-12, -6 * lg, 12, -6 * lg],
            [6 * lg, 2 * lg**2, -6 * lg, 4 * lg**2],
        ]
    )


def _equivalent_loads(length: float, q0: float, q1: float) -> np.ndarray:
    """Узловые нагрузки от линейно меняющейся нагрузки q0 → q1 на участке длиной length."""
    lg = length
    return np.array(
        [
            lg * (7 * q0 + 3 * q1) / 20,
            lg**2 * (3 * q0 + 2 * q1) / 60,
            lg * (3 * q0 + 7 * q1) / 20,
            -(lg**2) * (2 * q0 + 3 * q1) / 60,
        ]
    )


class Grillage:
    """Модель грильяжа: узлы, балки, нагрузки. ``solve()`` возвращает результат."""

    def __init__(self) -> None:
        self.nodes: list[tuple[float, float]] = []
        self.supports: set[int] = set()
        self.beams: list[_Beam] = []
        self.point_loads: dict[int, float] = {}

    def node(self, x: float, y: float, *, support: bool = False) -> int:
        self.nodes.append((float(x), float(y)))
        index = len(self.nodes) - 1
        if support:
            self.supports.add(index)
        return index

    def beam(self, i: int, j: int, ei: float) -> int:
        (xi, yi), (xj, yj) = self.nodes[i], self.nodes[j]
        if abs(yi - yj) <= TOLERANCE_MM:
            axis = 0
            if xj < xi:
                i, j = j, i
        elif abs(xi - xj) <= TOLERANCE_MM:
            axis = 1
            if yj < yi:
                i, j = j, i
        else:
            raise ValueError("Балка грильяжа должна идти вдоль оси X или Y.")
        self.beams.append(_Beam(i, j, ei, axis))
        return len(self.beams) - 1

    def line_load(self, beam: int, q0: float, q1: float | None = None, s0: float = 0.0, s1=None):
        """Линейная нагрузка на участке балки [s0, s1] от её начала (меньшей координаты)."""
        b = self.beams[beam]
        length = b.length(self.nodes)
        b.loads.append((s0, length if s1 is None else s1, q0, q0 if q1 is None else q1))

    def point_load(self, node: int, force: float) -> None:
        self.point_loads[node] = self.point_loads.get(node, 0.0) + force

    # --- решение ------------------------------------------------------------------------

    def _dofs(self, beam: _Beam) -> list[int]:
        rot = 1 + beam.axis
        return [3 * beam.i, 3 * beam.i + rot, 3 * beam.j, 3 * beam.j + rot]

    def _fixed_end(self, beam: _Beam) -> np.ndarray:
        """Узловые нагрузки элемента от всех его распределённых нагрузок."""
        length = beam.length(self.nodes)
        total = np.zeros(4)
        for s0, s1, q0, q1 in beam.loads:
            total += _partial_load_vector(length, s0, s1, q0, q1)
        return total

    def solve(self) -> GrillageResult:
        n = 3 * len(self.nodes)
        stiffness = np.zeros((n, n))
        loads = np.zeros(n)
        self._element_cache = []
        for beam in self.beams:
            dofs = self._dofs(beam)
            k = _stiffness(beam.ei, beam.length(self.nodes))
            fixed_end = self._fixed_end(beam)
            self._element_cache.append((dofs, k, fixed_end))
            stiffness[np.ix_(dofs, dofs)] += k
            loads[dofs] += fixed_end
        for node, force in self.point_loads.items():
            loads[3 * node] += force

        fixed = {3 * s for s in self.supports}
        # Степени свободы без жёсткости (поворот, к которому не подходит ни одна балка).
        fixed |= {d for d in range(n) if abs(stiffness[d, d]) < 1e-12}
        free = [d for d in range(n) if d not in fixed]
        displacements = np.zeros(n)
        displacements[free] = np.linalg.solve(stiffness[np.ix_(free, free)], loads[free])
        return GrillageResult(self, displacements)


def _partial_load_vector(length: float, s0: float, s1: float, q0: float, q1: float) -> np.ndarray:
    """Узловые нагрузки элемента от линейной нагрузки на участке [s0, s1].

    Участок интегрируется численно по формулам Гаусса с функциями формы балочного элемента.
    """
    if s1 - s0 <= TOLERANCE_MM:
        return np.zeros(4)
    if s0 <= TOLERANCE_MM and length - s1 <= TOLERANCE_MM:
        return _equivalent_loads(length, q0, q1)
    points, weights = _GAUSS_POINTS, _GAUSS_WEIGHTS
    vector = np.zeros(4)
    half = (s1 - s0) / 2
    for p, w in zip(points, weights, strict=True):
        s = s0 + half * (p + 1)
        q = q0 + (q1 - q0) * (s - s0) / (s1 - s0)
        xi = s / length
        shape = np.array(
            [
                1 - 3 * xi**2 + 2 * xi**3,
                length * (xi - 2 * xi**2 + xi**3),
                3 * xi**2 - 2 * xi**3,
                length * (-(xi**2) + xi**3),
            ]
        )
        vector += w * half * q * shape
    return vector


class GrillageResult:
    """Перемещения узлов, реакции опор и усилия в балках."""

    def __init__(self, model: Grillage, displacements: np.ndarray) -> None:
        self._model = model
        self._u = displacements
        self._forces = [k @ displacements[dofs] - fixed for dofs, k, fixed in model._element_cache]
        self._reactions = {node: -force for node, force in model.point_loads.items()}
        for beam, forces in zip(model.beams, self._forces, strict=True):
            self._reactions[beam.i] = self._reactions.get(beam.i, 0.0) - forces[0]
            self._reactions[beam.j] = self._reactions.get(beam.j, 0.0) - forces[2]

    def deflection(self, node: int) -> float:
        return float(self._u[3 * node])

    def _end_forces(self, beam: int) -> np.ndarray:
        return self._forces[beam]

    def reaction(self, node: int) -> float:
        """Реакция опоры вверх, Н."""
        return float(self._reactions.get(node, 0.0))

    def end_moments(self, beam: int) -> tuple[float, float]:
        """Изгибающие моменты в начале и в конце балки, Н·мм; растянутый низ — плюс."""
        forces = self._end_forces(beam)
        return float(forces[1]), float(-forces[3])

    def _load_integrals(self, beam: int, s: float) -> tuple[float, float]:
        """Нагрузка на участке [0, s]: равнодействующая и её момент относительно точки s."""
        force = moment = 0.0
        for s0, s1, q0, q1 in self._model.beams[beam].loads:
            end = min(s, s1)
            if end <= s0:
                continue
            q_end = q0 + (q1 - q0) * (end - s0) / (s1 - s0)
            length = end - s0
            part_force = (q0 + q_end) / 2 * length
            # Центр тяжести трапеции от s0.
            centroid = length * (q0 + 2 * q_end) / (3 * (q0 + q_end)) if q0 + q_end else 0.0
            force += part_force
            moment += part_force * (s - (s0 + centroid))
        return force, moment

    def shear_at(self, beam: int, s: float) -> float:
        """Поперечная сила в сечении s от начала балки, Н (вверх слева — плюс)."""
        forces = self._end_forces(beam)
        load, _ = self._load_integrals(beam, s)
        return float(-forces[0] - load)

    def moment_at(self, beam: int, s: float) -> float:
        """Изгибающий момент в сечении s от начала балки, Н·мм; растянутый низ — плюс."""
        forces = self._end_forces(beam)
        _, load_moment = self._load_integrals(beam, s)
        return float(forces[1] - forces[0] * s - load_moment)

    def transfer_force(self, node: int) -> float:
        """Сила, которую балки одного направления передают балкам другого в узле, Н.

        Балки вдоль X и вдоль Y отдают в узел вертикальные силы; меньшая по модулю из двух
        сумм — это то, что передаётся через сварное примыкание. В узле на одной прямой — 0.
        """
        totals = [0.0, 0.0]
        touched = [False, False]
        for beam, forces in zip(self._model.beams, self._forces, strict=True):
            if beam.i == node:
                totals[beam.axis] += forces[0]
                touched[beam.axis] = True
            if beam.j == node:
                totals[beam.axis] += forces[2]
                touched[beam.axis] = True
        if not all(touched):
            return 0.0
        return float(min(abs(totals[0]), abs(totals[1])))
