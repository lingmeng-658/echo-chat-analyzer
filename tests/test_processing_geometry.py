"""Astra geometry contract: literal fixtures come from the accepted HTML."""
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def geometry():
    from qq_chat_analyzer.gui import processing_geometry
    return processing_geometry


def test_open_pages_use_four_cubic_edges_and_mirrored_binding():
    g = geometry()
    left = g.page_points("left")
    right = g.page_points("right")
    assert left[0] == (400, 239)
    assert left[3] == (238, 216)
    assert left[6] == (223, 370)
    assert left[9] == (400, 390)
    assert right == tuple((800 - x, y) for x, y in left)
    path = g.paper_path(left)
    assert path.elementCount() == 13
    assert path.currentPosition() == QPointF(400, 239)
    assert path.contains(QPointF(300, 300))
    assert not path.contains(QPointF(450, 300))


@pytest.mark.parametrize("side", ["left", "right"])
def test_flight_docks_continuously_and_never_crosses_the_spine(side):
    g = geometry()
    assert g.flight_points(side, 0, 1.1) == g.loose_points(side)
    dock = g.flight_points(side, .52, 1.1)
    assert dock[0] == (400, 239)
    assert dock[9] == (400, 390)
    assert dock[3] == ((303, 156) if side == "left" else (497, 156))
    for t in [i / 200 for i in range(201)]:
        points = g.flight_points(side, t, 1.1)
        assert all(x <= 400 if side == "left" else x >= 400 for x, _ in points)
        if t >= .52:
            assert tuple(points[i] for i in (0, 9, 10, 11)) == tuple(dock[i] for i in (0, 9, 10, 11))
    for t in (.52 - 1e-6, .52 + 1e-6):
        points = g.flight_points(side, t, 1.1)
        assert max(abs(a - b) for p, q in zip(points, dock) for a, b in zip(p, q)) < 1e-7
    assert g.flight_points(side, 1, 1.1) == g.page_points(side, 1.1)
    assert g.page_points(side, 1.1)[3][1] == pytest.approx(214.9)


def test_coons_surface_preserves_corners_and_initial_pen_contact():
    g = geometry()
    p = g.page_points("right")
    for u, v, index in [(0, 0, 0), (1, 0, 3), (1, 1, 6), (0, 1, 9)]:
        assert g.surface(p, u, v) == pytest.approx(p[index])
    # Independently evaluated from prototype surface(page('right'), .16, .21).
    assert g.surface(p, .16, .21) == pytest.approx((426.49677004, 257.43979728))


def test_pen_flag_is_part_of_the_closed_barrel_and_nib_reaches_origin():
    g = geometry()
    body = g.pen_body_path()
    assert body.currentPosition() == QPointF(-5.8, -24)
    assert body.contains(QPointF(0, -70))
    assert body.contains(QPointF(30, -92))
    assert not body.contains(QPointF(14, -92))
    assert g.pen_nib_path().boundingRect().bottom() == 0
    assert QRectF(-10, -145, 55, 150).contains(body.boundingRect())


def test_page_edges_follow_outer_corners_and_bounded_depth():
    g = geometry()
    edges = g.page_edge_paths("left", 5.5)
    assert len(edges) == 5
    first = edges[0].elementAt(0)
    assert (first.x, first.y) == pytest.approx((238, 220.3))
    assert edges[0].currentPosition() == QPointF(400, 397.6)
    assert edges[-1].currentPosition() == QPointF(400, 392)


def test_writing_tip_and_ink_share_arc_length_endpoint_for_every_word():
    g = geometry()
    points = g.page_points("right", 2.2)
    specs = g.writing_specs()
    total = sum(s.duration + s.pause for s in specs)
    elapsed = 0
    for index, spec in enumerate(specs):
        for fraction in (.1, .5, .9):
            pose = g.writing_pose(points, (elapsed + spec.duration*fraction)/total)
            end = pose.paths[index].currentPosition()
            assert pose.lift == 0
            assert pose.point == pytest.approx((end.x(), end.y()), abs=1e-8)
            full = g.line_path(points, spec.u0, spec.u1, spec.v)
            assert pose.paths[index].length() == pytest.approx(full.length()*fraction, abs=.05)
            assert g.paper_path(points).contains(end)
        pose = g.writing_pose(points, (elapsed+spec.duration+spec.pause/2)/total)
        if index < len(specs)-1:
            assert pose.lift == pytest.approx(8 if spec.pause > 100 else 2.5)
            assert pose.paths[index+1].isEmpty()
        elapsed += spec.duration+spec.pause


def test_turn_uses_prototype_upright_and_fixed_binding():
    g = geometry()
    start = g.page_points("right", 1.1)
    assert g.turn_points(start, 2.2, 0) == start
    upright = g.turn_points(start, 2.2, .48)
    assert upright[3] == (452, 130)
    assert upright[6] == (441, 274)
    assert g.turn_points(start, 2.2, 1) == g.page_points("left", 2.2)
    for t in [i/100 for i in range(101)]:
        p = g.turn_points(start, 2.2, t)
        assert p[0] == (400, 239)
        assert p[9] == (400, 390)
