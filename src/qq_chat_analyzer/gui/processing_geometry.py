"""Astra's 800 x 460 geometry, without a clock or mutable animation state.

Ported from processing-book-prototype/dist/index.html: page, loose, docking,
poseFlight, surface, line, updateEdges and the original book/pen SVG paths.
Points are twelve controls for four cubic edges; indices 0, 9, 10, 11 are
the binding. SVG quadratic segments use QPainterPath.quadTo (Qt >= 6.6).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtGui import QPainterPath

from .processing_animation_model import PaperSide, clamp01, ease, mix

Point = tuple[float, float]
Points = tuple[Point, ...]
LOGICAL_WIDTH = 800
LOGICAL_HEIGHT = 460


def _side(points: Points, side: PaperSide | str, right_dy: float = 0) -> Points:
    return points if PaperSide(side) is PaperSide.LEFT else tuple(
        (800 - x, y + right_dy) for x, y in points
    )


def page_points(side: PaperSide | str, depth: float = 0) -> Points:
    return _side((
        (400, 239), (350, 213-depth), (290, 203-depth), (238, 216-depth),
        (233, 264), (228, 325), (223, 370-depth), (286, 357-depth),
        (342, 366-depth), (400, 390), (398, 343), (397, 282),
    ), side)


def loose_points(side: PaperSide | str) -> Points:
    return _side((
        (277, 127), (244, 112), (205, 98), (174, 97), (161, 124),
        (152, 152), (145, 179), (177, 181), (218, 195), (252, 211),
        (260, 185), (269, 155),
    ), side, -14)


def docking_points(side: PaperSide | str) -> Points:
    return _side((
        (400, 239), (376, 196), (338, 165), (303, 156), (281, 188),
        (265, 228), (263, 275), (307, 288), (361, 343), (400, 390),
        (398, 343), (397, 282),
    ), side)


def _pt(a: Point, b: Point, t: float) -> Point:
    return mix(a[0], b[0], t), mix(a[1], b[1], t)


def flight_points(side: PaperSide | str, progress: float, depth: float) -> Points:
    t = clamp01(progress)
    if t < .52:
        a, b, amount = loose_points(side), docking_points(side), ease(t / .52)
    else:
        a, b, amount = docking_points(side), page_points(side, depth), ease((t-.52)/.48)
    return tuple(_pt(p, q, amount) for p, q in zip(a, b))


def paper_path(points: Points) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(*points[0])
    for i in (1, 4, 7, 10):
        path.cubicTo(*points[i], *points[i+1], *points[(i+2) % 12])
    path.closeSubpath()
    return path


def _cubic(a: Point, b: Point, c: Point, d: Point, t: float) -> Point:
    s = 1-t
    return tuple(s*s*s*a[i] + 3*s*s*t*b[i] + 3*s*t*t*c[i] + t*t*t*d[i]
                 for i in (0, 1))


def surface(p: Points, u: float, v: float) -> Point:
    """Prototype Coons patch; keeps paragraph marks on the curved paper."""
    top = _cubic(p[0], p[1], p[2], p[3], u)
    bottom = _cubic(p[9], p[8], p[7], p[6], u)
    inner = _cubic(p[0], p[11], p[10], p[9], v)
    outer = _cubic(p[3], p[4], p[5], p[6], v)
    bilinear = _pt(_pt(p[0], p[3], u), _pt(p[9], p[6], u), v)
    return tuple(mix(top[i], bottom[i], v) + mix(inner[i], outer[i], u) - bilinear[i]
                 for i in (0, 1))


def line_path(p: Points, u0: float, u1: float, v: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(*surface(p, u0, v))
    path.cubicTo(*surface(p, mix(u0, u1, .33), v-.004),
                 *surface(p, mix(u0, u1, .67), v+.004), *surface(p, u1, v))
    return path


@dataclass(frozen=True)
class WordSpec:
    u0: float
    u1: float
    v: float
    duration: float
    pause: float


@lru_cache(maxsize=1)
def writing_specs() -> tuple[WordSpec, ...]:
    words = ((.18, .37, .23), (.12, .25, .30, .08), (.25, .18, .15),
             (.20, .14, .25, .11), (.12, .31, .18), (.24, .13, .18, .09))
    specs = []
    for row, lengths in enumerate(words):
        start = .16
        for index, length in enumerate(lengths):
            end = start + length*.68
            specs.append(WordSpec(start, end, .21+row*.096+(.052 if row > 2 else 0),
                                  length*.68*4400+80, 70+(190 if index == len(lengths)-1 else 0)))
            start = end+.035
    return tuple(specs)


def paper_ink_path(p: Points, side: PaperSide | str, detailed: bool = False) -> QPainterPath:
    path = QPainterPath()
    for index, spec in enumerate(writing_specs()):
        if detailed or index % 2 == 0:
            u0, u1 = (1-spec.u0, 1-spec.u1) if PaperSide(side) is PaperSide.LEFT else (spec.u0, spec.u1)
            path.addPath(line_path(p, u0, u1, spec.v))
    return path


@lru_cache(maxsize=32)
def _writing_paths(p: Points) -> tuple[QPainterPath, ...]:
    return tuple(line_path(p, s.u0, s.u1, s.v) for s in writing_specs())


def _prefix(path: QPainterPath, amount: float) -> QPainterPath:
    """Split a cubic at its arc-length fraction, using only Qt 6.6 APIs.

    De Casteljau preserves the actual curve. Both ink and tip use the same
    split endpoint, avoiding a second sampled/polyline pen trajectory.
    """
    if amount <= 0:
        return QPainterPath()
    if amount >= 1:
        return QPainterPath(path)
    t = path.percentAtLength(path.length()*amount)
    points = tuple((path.elementAt(i).x, path.elementAt(i).y) for i in range(4))
    a, b, c = (_pt(points[i], points[i+1], t) for i in range(3))
    d, e = _pt(a, b, t), _pt(b, c, t)
    end = _pt(d, e, t)
    prefix = QPainterPath()
    prefix.moveTo(*points[0])
    prefix.cubicTo(*a, *d, *end)
    return prefix


@dataclass(frozen=True)
class WritingPose:
    paths: tuple[QPainterPath, ...]
    point: Point
    angle: float
    lift: float


def writing_pose(p: Points, progress: float) -> WritingPose:
    specs, full = writing_specs(), _writing_paths(p)
    at = clamp01(progress)*sum(s.duration+s.pause for s in specs)
    elapsed, point, angle, lift = 0.0, None, 31.0, 0.0
    paths = []
    for i, (spec, path) in enumerate(zip(specs, full)):
        amount = clamp01((at-elapsed)/spec.duration)
        prefix = _prefix(path, amount)
        paths.append(prefix)
        if elapsed <= at < elapsed+spec.duration+spec.pause:
            xy = prefix.currentPosition() if amount > 0 else path.pointAtPercent(0)
            point = (xy.x(), xy.y())
            angle = 30+3*math.sin(amount*math.pi)
            if amount == 1 and i+1 < len(full):
                dest = full[i+1].pointAtPercent(0)
                hop = clamp01((at-elapsed-spec.duration)/spec.pause)
                point = _pt(point, (dest.x(), dest.y()), ease(hop))
                lift = math.sin(hop*math.pi)*(8 if spec.pause > 100 else 2.5)
        elapsed += spec.duration+spec.pause
    if point is None:
        end = full[-1].pointAtPercent(1)
        point = (end.x(), end.y())
    return WritingPose(tuple(paths), point, angle, lift)


def turn_points(start: Points, target_depth: float, progress: float) -> Points:
    upright = ((400, 239), (419, 182), (443, 135), (452, 130), (460, 169),
               (457, 218), (441, 274), (428, 308), (412, 354), (400, 390),
               (398, 343), (397, 282))
    t = clamp01(progress)
    a, b, amount = (start, upright, ease(t/.48)) if t < .48 else (
        upright, page_points(PaperSide.LEFT, target_depth), ease((t-.48)/.52))
    return tuple(_pt(p, q, amount) for p, q in zip(a, b))


def page_edge_paths(side: PaperSide | str, depth: float) -> tuple[QPainterPath, ...]:
    p = page_points(side, depth)
    edges = []
    for i in range(4, -1, -1):
        dy = i*1.7+3
        path = QPainterPath()
        path.moveTo(p[3][0], p[3][1]+dy)
        path.lineTo(p[6][0], p[6][1]+dy)
        path.cubicTo(p[7][0], p[7][1]+dy, p[8][0], p[8][1]+dy, 400, 392+i*1.4)
        edges.append(path)
    return tuple(edges)


def book_cover_path() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(400, 249)
    p.cubicTo(340, 219, 282, 213, 230, 223)
    p.lineTo(213, 380)
    p.cubicTo(276, 367, 341, 380, 395, 406)
    p.quadTo(400, 409, 405, 406)
    p.cubicTo(460, 380, 524, 367, 587, 380)
    p.lineTo(570, 223)
    p.cubicTo(519, 213, 460, 219, 400, 249)
    p.closeSubpath()
    return p


def cover_edge_path() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(217, 383)
    p.cubicTo(284, 373, 344, 385, 395, 407)
    p.quadTo(400, 410, 405, 407)
    p.cubicTo(459, 385, 520, 373, 583, 383)
    return p


def gutter_path() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(400, 239)
    p.cubicTo(397, 280, 398, 347, 400, 390)
    return p


def binding_tail_path() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(400, 390)
    p.quadTo(398, 399, 396, 401)
    return p


def pen_body_path() -> QPainterPath:
    """Single closed SVG contour: barrel, stem and musical flag."""
    p = QPainterPath()
    p.moveTo(-5.8, -24)
    p.lineTo(-5.8, -101)
    p.quadTo(-5.8, -120, 0, -140)
    p.cubicTo(4, -123, 20, -122, 29, -109)
    p.cubicTo(42, -91, 32, -74, 15, -66)
    p.cubicTo(24, -77, 27, -88, 20, -99)
    p.cubicTo(16, -105, 11, -108, 6, -113)
    p.lineTo(6, -24)
    p.closeSubpath()
    return p


def pen_nib_path() -> QPainterPath:
    p = QPainterPath()
    p.moveTo(-5.5, -23)
    p.lineTo(5.5, -23)
    p.lineTo(7, -17)
    p.quadTo(3, -6, 0, 0)
    p.quadTo(-3, -6, -7, -17)
    p.closeSubpath()
    return p
