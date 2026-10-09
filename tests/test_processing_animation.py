"""Headless QImage acceptance frames; run this file to export the five PNGs."""
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QTransform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qq_chat_analyzer.application.analysis_phase import AnalysisPhase
from qq_chat_analyzer.gui.processing_animation_model import ProcessingAnimationModel


def advance_sample(model, total_ms):
    remaining = total_ms
    while remaining > 1e-9:
        step = min(16.0, model.timing.max_frame_step_ms, remaining)
        model.advance(step)
        remaining -= step


def keyframes():
    frames = []
    for name, progress in [("01-open-book", 0), ("02-page-approaching", .26),
                           ("03-page-docked", .52), ("04-page-landed", 1)]:
        model = ProcessingAnimationModel()
        advance_sample(model, progress * model.timing.landing_ms)
        frames.append((name, model))
    model = ProcessingAnimationModel()
    advance_sample(model, model.timing.landing_ms)
    model.set_phase(AnalysisPhase.ANALYZING_REPORT)
    advance_sample(model, model.timing.pen_enter_ms)
    frames.append(("05-analysis-note-pen", model))
    return frames


def renderer():
    from qq_chat_analyzer.gui import processing_animation
    return processing_animation


def alpha_bounds(image):
    # Real raster output, rather than the renderer's own declared bounds.
    xs, ys = [], []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha():
                xs.append(x)
                ys.append(y)
    return QRectF(min(xs), min(ys), max(xs)-min(xs)+1, max(ys)-min(ys)+1)


def test_keyframes_are_deterministic_and_rendering_does_not_advance_model():
    r = renderer()
    images = []
    for _, model in keyframes():
        state = (model.clock_ms, model.leaves(), model.incoming, model.pen_alpha)
        image = r.render_processing_frame(model)
        assert image.size().width() == 800
        assert image.size().height() == 460
        assert image == r.render_processing_frame(model)
        assert state == (model.clock_ms, model.leaves(), model.incoming, model.pen_alpha)
        assert image.pixelColor(300, 300).alpha() == 255
        assert QRectF(100, 70, 600, 360).contains(alpha_bounds(image))
        images.append(image)
    assert all(a != b for a, b in zip(images, images[1:]))
    # The flag/barrel becomes visible above the right page only in frame 5.
    assert images[3].pixelColor(470, 190).alpha() == 0
    assert images[4].pixelColor(470, 190).alpha() > 0


@pytest.mark.parametrize("size", [(400, 230), (1600, 920), (1000, 460), (800, 600)])
def test_scaling_preserves_proportions_and_does_not_clip(size):
    r = renderer()
    model = keyframes()[-1][1]
    image = r.render_processing_frame(model, *size)
    bounds = alpha_bounds(image)
    native = alpha_bounds(r.render_processing_frame(model))
    scale = min(size[0]/800, size[1]/460)
    dx, dy = (size[0]-800*scale)/2, (size[1]-460*scale)/2
    assert bounds.x() == pytest.approx(native.x()*scale+dx, abs=2)
    assert bounds.y() == pytest.approx(native.y()*scale+dy, abs=2)
    assert bounds.width() == pytest.approx(native.width()*scale, abs=3)
    assert bounds.height() == pytest.approx(native.height()*scale, abs=3)
    assert QRectF(1, 1, size[0]-2, size[1]-2).contains(bounds)


def test_painter_restores_transform_clip_opacity_and_pen():
    r = renderer()
    image = QImage(1000, 600, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#fbf9f4"))
    painter = QPainter(image)
    try:
        painter.setTransform(QTransform().translate(7, 11))
        painter.setClipRect(QRectF(0, 0, 980, 580))
        painter.setOpacity(.8)
        before = (painter.transform(), painter.clipBoundingRect(), painter.opacity(), painter.pen())
        r.paint_processing_frame(painter, QRectF(10, 20, 800, 460), keyframes()[0][1])
        assert before == (painter.transform(), painter.clipBoundingRect(), painter.opacity(), painter.pen())
    finally:
        painter.end()


def test_live_writing_renders_growth_and_moves_the_pen_with_the_ink():
    r = renderer()
    model = keyframes()[-1][1]
    initial = r.render_processing_frame(model)
    advance_sample(model, 1500)
    pose = r.pen_pose(model)
    assert pose.point != pytest.approx((426.49677004, 257.43979728))
    assert initial != r.render_processing_frame(model)
    pose_before = pose
    image_before = r.render_processing_frame(model)
    model.set_phase(AnalysisPhase.READING)
    assert r.pen_pose(model) == pose_before
    assert r.render_processing_frame(model) == image_before


def test_paper_binding_and_turn_landing_have_no_disappearance_or_flash():
    r = renderer()
    model = ProcessingAnimationModel()
    advance_sample(model, model.timing.landing_ms - .001)
    before = r.render_processing_frame(model)
    advance_sample(model, .001)
    after = r.render_processing_frame(model)
    # Binding updates the visible page edges; the opaque face must stay intact.
    assert_face_continuity(before, after)
    model.set_phase(AnalysisPhase.ANALYZING_REPORT)
    advance_sample(model, model.timing.pen_enter_ms)
    advance_sample(model, model.timing.writing_ms + model.timing.rest_ms + model.timing.turn_ms - .001)
    before = r.render_processing_frame(model)
    assert model.turn is not None
    advance_sample(model, .001)
    after = r.render_processing_frame(model)
    assert model.turn is None
    # Pen drop starts at the same lifted point, and the turned leaf stays opaque.
    assert_face_continuity(before, after)


def assert_face_continuity(before, after):
    for y in range(250, 340):
        for x in range(250, 390):
            a, b = before.pixelColor(x, y), after.pixelColor(x, y)
            assert a.alpha() == b.alpha() == 255
            assert max(abs(c-d) for c, d in zip(a.getRgb(), b.getRgb())) <= 1


def export_keyframes(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, model in keyframes():
        image = renderer().render_processing_frame(model, background=QColor("#fbf9f4"))
        target = directory / (name + ".png")
        assert image.save(str(target), "PNG")
        print(target)


def dynamic_keyframes():
    frames = keyframes()
    for name, ms in [
        ("06-writing-first-line", 1525), ("07-writing-later-lines", 3355),
        ("08-pen-lift-rest", 6460), ("09-turn-upright", 6820+1650*.48),
        ("10-turn-landing", 6820+1650*.8), ("11-turn-landed-pen-drop", 8470),
    ]:
        model = keyframes()[-1][1]
        advance_sample(model, ms)
        frames.append((name, model))
    return frames


def test_turn_keyframes_render_distinct_opaque_paper_with_fixed_binding():
    r = renderer()
    images = dict((name, r.render_processing_frame(model)) for name, model in dynamic_keyframes())
    upright = images["09-turn-upright"]
    assert upright.pixelColor(430, 220).alpha() == 255
    assert upright.pixelColor(400, 320).alpha() == 255
    assert images["08-pen-lift-rest"] != upright
    assert upright != images["10-turn-landing"]
    assert images["10-turn-landing"] != images["11-turn-landed-pen-drop"]


def export_dynamic(directory):
    """20 seconds at 20fps, sampled deterministically through the same model."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, model in dynamic_keyframes():
        target = directory / (name + ".png")
        assert renderer().render_processing_frame(model, background=QColor("#fbf9f4")).save(str(target), "PNG")
        print(target)
    sequence = directory / "sequence"
    sequence.mkdir(exist_ok=True)
    model = ProcessingAnimationModel()
    rows = ["frame,time_ms,phase,clock_ms,turn_progress"]
    for frame in range(401):
        if frame == 148:  # two full reading cycles, then manual analysis event
            model.set_phase(AnalysisPhase.ANALYZING_REPORT)
        target = sequence / f"frame-{frame:04d}.png"
        assert renderer().render_processing_frame(model, background=QColor("#fbf9f4")).save(str(target), "PNG")
        rows.append(f"{frame},{frame*50},{model.phase.value},{model.clock_ms},{model.turn_progress}")
        if frame < 400:
            advance_sample(model, 50)
    (directory / "sequence.csv").write_text("\n".join(rows)+"\n", encoding="utf-8")
    # Local-only review player, independent of the production Qt implementation.
    (directory / "sequence.html").write_text('''<!doctype html>
<meta charset="utf-8"><title>Echo · Stage 2B-2 帧序列</title>
<style>body{background:#fbf9f4;color:#352f29;text-align:center;font-family:sans-serif}img{max-width:100%}</style>
<h3>读取 → 分析 → 翻页 · 20秒 / 20fps</h3>
<img id="scene" width="800" height="460" src="sequence/frame-0000.png"><br>
<button id="play">播放</button><input id="seek" type="range" min="0" max="400" value="0"><span id="time">0.00s</span>
<script>
const scene=document.getElementById('scene'),seek=document.getElementById('seek'),time=document.getElementById('time'),play=document.getElementById('play');
let frame=0,timer=null;
function show(){scene.src='sequence/frame-'+String(frame).padStart(4,'0')+'.png';seek.value=frame;time.textContent=(frame*.05).toFixed(2)+'s';}
function stop(){clearInterval(timer);timer=null;play.textContent='播放';}
play.onclick=()=>{if(timer){stop();return;}play.textContent='暂停';timer=setInterval(()=>{frame=(frame+1)%401;show();},50);};
seek.oninput=()=>{stop();frame=Number(seek.value);show();};
</script>''', encoding="utf-8")
    print(directory / "sequence.html")
    print(f"{sequence}: 401 PNG frames / 20 seconds")


if __name__ == "__main__":
    if "--stage2b2" in sys.argv:
        export_dynamic(ROOT / "output" / "processing-native-stage2b2")
    else:
        export_keyframes(ROOT / "output" / "processing-native-stage2b1")
