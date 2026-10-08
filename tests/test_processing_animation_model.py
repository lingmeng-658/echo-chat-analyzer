"""Deterministic tests for the processing animation state model.

The model is the testable half of the accepted Astra book prototype
(``output/processing-book-prototype``): it owns the gesture timeline and the
paper bookkeeping while a separate drawing layer owns the geometry. Every duration
asserted here is read from the prototype's own ``T`` table, and every test
drives the model with explicit millisecond steps, so nothing depends on a real
clock and every run is reproducible.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


from qq_chat_analyzer.application.analysis_phase import AnalysisPhase  # noqa: E402
from qq_chat_analyzer.gui.processing_animation_model import (  # noqa: E402
    AnimationTiming,
    PaperSide,
    ProcessingAnimationModel,
    WritingStage,
    ease,
    ease_out,
    mix,
)


STEP_MS = 16.0
LEFT = PaperSide.LEFT
RIGHT = PaperSide.RIGHT
READING = AnalysisPhase.READING
ANALYSIS = AnalysisPhase.ANALYZING_REPORT


# ----------------------------------------------------------------- helpers


def _run(
    model: ProcessingAnimationModel,
    total_ms: float,
    *,
    step: float = STEP_MS,
    observe=None,
) -> None:
    """Advance the model in fixed steps, optionally observing every step."""
    remaining = float(total_ms)
    while remaining > 1e-9:
        chunk = min(step, model.timing.max_frame_step_ms, remaining)
        model.advance(chunk)
        remaining -= chunk
        if observe is not None:
            observe()


def _ids(model: ProcessingAnimationModel, side: PaperSide) -> tuple[int, ...]:
    return tuple(leaf.leaf_id for leaf in model.leaves(side))


def _snapshot(model: ProcessingAnimationModel) -> tuple:
    incoming = model.incoming
    return (
        model.phase,
        model.requested_phase,
        model.active,
        model.paused,
        model.hidden,
        model.clock_ms,
        model.reading_cycles,
        model.is_transitioning,
        model.transition_elapsed_ms,
        model.pen_alpha,
        model.pen_lift,
        model.writing_stage,
        model.writing_stage_progress,
        model.turn_progress,
        model.leaf_depth(LEFT),
        model.leaf_depth(RIGHT),
        tuple(
            (leaf.leaf_id, leaf.side, leaf.depth, leaf.landed, leaf.progress)
            for leaf in model.leaves()
        ),
        None
        if incoming is None
        else (incoming.leaf_id, incoming.side, incoming.depth, incoming.progress),
    )


def _in_flight_model() -> ProcessingAnimationModel:
    """A reading run whose first sheet is part way in."""
    model = ProcessingAnimationModel()
    _run(model, 1000)
    return model


def _landed_model() -> ProcessingAnimationModel:
    """A reading run whose first sheet has just landed."""
    model = ProcessingAnimationModel()
    _run(model, AnimationTiming().landing_ms)
    return model


def _analysis_model(clock_ms: float = 0.0) -> ProcessingAnimationModel:
    """An analysis run past its entry transition, ``clock_ms`` into writing."""
    model = _landed_model()
    model.set_phase(ANALYSIS)
    _run(model, AnimationTiming().pen_enter_ms)
    _run(model, clock_ms)
    return model


def _turning_model() -> ProcessingAnimationModel:
    """An analysis run in the middle of turning a written sheet."""
    model = _analysis_model()
    _run(model, AnimationTiming().writing_ms + AnimationTiming().rest_ms + 700)
    return model


# ---------------------------------------------------- prototype parameters


def test_timings_match_the_accepted_prototype() -> None:
    timing = AnimationTiming()

    assert timing.reading_cycle_ms == pytest.approx(3700.0)
    assert timing.landing_ratio == pytest.approx(0.88)
    assert timing.landing_ms == pytest.approx(3256.0)
    assert timing.settle_ms == pytest.approx(620.0)
    assert timing.pen_enter_ms == pytest.approx(480.0)
    assert timing.pen_drop_ms == pytest.approx(320.0)
    assert timing.writing_ms == pytest.approx(6100.0)
    assert timing.rest_ms == pytest.approx(720.0)
    assert timing.turn_ms == pytest.approx(1650.0)
    assert timing.exit_ms == pytest.approx(480.0)
    assert timing.writing_cycle_ms == pytest.approx(8790.0)
    assert timing.leaf_rise == pytest.approx(1.1)
    assert timing.max_leaves_per_side == 7
    assert timing.max_visible_page_edges == 5
    assert timing.max_leaf_depth == pytest.approx(5.5)


def test_easing_helpers_are_the_prototype_curves() -> None:
    assert ease(-1.0) == 0.0
    assert ease(0.0) == 0.0
    assert ease(0.25) == pytest.approx(0.15625)
    assert ease(0.5) == pytest.approx(0.5)
    assert ease(1.0) == 1.0
    assert ease(2.0) == 1.0

    assert ease_out(0.0) == 0.0
    assert ease_out(0.5) == pytest.approx(0.875)
    assert ease_out(1.0) == 1.0
    assert ease_out(4.0) == 1.0

    assert mix(2.0, 6.0, 0.25) == pytest.approx(3.0)
    assert mix(2.0, 6.0, 0.0) == pytest.approx(2.0)


def test_model_module_has_no_clock_or_gui_dependency() -> None:
    """The model must be drivable by tests and usable without Qt."""
    module = importlib.import_module(
        "qq_chat_analyzer.gui.processing_animation_model"
    )
    tree = ast.parse(inspect.getsource(module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint(
        {"time", "datetime", "random", "PySide6", "PyQt5", "PyQt6"}
    )


def test_the_model_only_moves_when_time_is_advanced_externally() -> None:
    model = ProcessingAnimationModel()
    before = _snapshot(model)

    time.sleep(0.02)

    assert _snapshot(model) == before
    model.advance(50.0)
    assert model.clock_ms == pytest.approx(50.0)


# -------------------------------------------------------- reading behaviour


def test_reading_cycle_lands_one_sheet_then_rests() -> None:
    timing = AnimationTiming()
    model = ProcessingAnimationModel()

    _run(model, timing.landing_ms - 1.0)
    incoming = model.incoming
    assert incoming is not None
    assert incoming.side is LEFT
    assert incoming.landed is False
    assert incoming.progress < 1.0

    _run(model, 1.0)
    assert model.incoming is None
    assert _ids(model, LEFT) == (1, incoming.leaf_id)
    assert model.leaves(LEFT)[-1].landed is True
    assert model.leaves(LEFT)[-1].progress == pytest.approx(1.0)
    assert model.leaf_depth(LEFT) == pytest.approx(timing.leaf_rise)

    _run(model, timing.reading_cycle_ms - timing.landing_ms)
    assert model.reading_cycles == 1
    assert _ids(model, LEFT) == (1, incoming.leaf_id)
    assert model.incoming is not None
    assert model.incoming.side is RIGHT
    assert model.incoming.progress == pytest.approx(0.0)


def test_sheet_state_is_continuous_across_binding() -> None:
    timing = AnimationTiming()
    model = ProcessingAnimationModel()
    seen: set[int] = set()
    bindings: list[tuple[PaperSide, int]] = []
    progress_by_id: dict[int, float] = {}
    pending: int | None = model.incoming.leaf_id

    def observe() -> None:
        nonlocal pending
        landed = model.leaves()
        landed_ids = [leaf.leaf_id for leaf in landed]
        assert len(landed_ids) == len(set(landed_ids))
        current = set(landed_ids)
        incoming = model.incoming
        if incoming is not None:
            assert incoming.leaf_id not in current
            assert incoming.landed is False
            assert incoming.progress >= progress_by_id.get(incoming.leaf_id, 0.0)
            progress_by_id[incoming.leaf_id] = incoming.progress
            current.add(incoming.leaf_id)
        # Nothing the reader already saw disappears; every landed sheet stays.
        assert current >= seen
        seen.update(current)
        assert all(leaf.progress == pytest.approx(1.0) for leaf in landed)

        if pending is not None and pending in landed_ids:
            bound = next(leaf for leaf in landed if leaf.leaf_id == pending)
            assert bound.landed is True
            bindings.append((bound.side, bound.leaf_id))
            pending = None
        if incoming is not None:
            pending = incoming.leaf_id

    _run(model, 2 * timing.reading_cycle_ms, observe=observe)

    assert [side for side, _ in bindings] == [LEFT, RIGHT]
    assert [leaf_id for _, leaf_id in bindings] == sorted(
        leaf_id for _, leaf_id in bindings
    )
    assert _ids(model, LEFT) == (1, bindings[0][1])
    assert _ids(model, RIGHT) == (2, bindings[1][1])


def test_landed_sheets_never_vanish_before_the_cap() -> None:
    timing = AnimationTiming()
    model = ProcessingAnimationModel()
    previous: dict[PaperSide, tuple[int, ...]] = {LEFT: (), RIGHT: ()}

    def observe() -> None:
        for side in (LEFT, RIGHT):
            ids = _ids(model, side)
            assert len(ids) == len(set(ids))
            assert len(ids) <= timing.max_leaves_per_side
            removed = [leaf_id for leaf_id in previous[side] if leaf_id not in ids]
            assert removed == list(previous[side][: len(removed)])
            assert not removed or len(previous[side]) == timing.max_leaves_per_side
            previous[side] = ids

    _run(model, 40 * timing.reading_cycle_ms, observe=observe)

    assert len(_ids(model, LEFT)) == timing.max_leaves_per_side
    assert len(_ids(model, RIGHT)) == timing.max_leaves_per_side


def test_book_size_and_thickness_stay_bounded() -> None:
    timing = AnimationTiming()
    model = ProcessingAnimationModel()

    def observe() -> None:
        for side in (LEFT, RIGHT):
            assert model.leaf_depth(side) <= timing.max_leaf_depth + 1e-9
            assert len(model.leaves(side)) <= timing.max_leaves_per_side
            assert all(
                leaf.depth <= timing.max_leaf_depth + 1e-9
                for leaf in model.leaves(side)
            )

    _run(model, 60 * timing.reading_cycle_ms, observe=observe)

    for side in (LEFT, RIGHT):
        leaves = model.leaves(side)
        assert len(leaves) == timing.max_leaves_per_side
        assert all(leaf.landed for leaf in leaves)
        assert model.leaf_depth(side) == pytest.approx(timing.max_leaf_depth)
        assert leaves[-1].depth == pytest.approx(timing.max_leaf_depth)


# ------------------------------------------------------- analysis behaviour


def test_reading_transitions_into_analysis_naturally() -> None:
    timing = AnimationTiming()
    model = _in_flight_model()
    incoming = model.incoming
    assert incoming is not None
    landed_sheets = len(model.leaves(LEFT)) + len(model.leaves(RIGHT))

    model.set_phase(ANALYSIS)

    assert model.phase is READING
    assert model.requested_phase is ANALYSIS
    assert model.is_transitioning is True
    assert model.pen_alpha == 0.0

    # The sheet in flight keeps settling; the pen waits for it.
    _run(model, timing.settle_ms - 1.0)
    assert model.pen_alpha == 0.0
    assert model.incoming is not None
    assert model.incoming.progress < 1.0

    _run(model, 1.0)
    assert model.incoming is None
    assert _ids(model, LEFT)[-1] == incoming.leaf_id
    assert model.leaves(LEFT)[-1].landed is True
    assert len(model.leaves()) == landed_sheets + 1
    assert model.phase is READING

    _run(model, timing.pen_enter_ms / 2)
    assert 0.0 < model.pen_alpha < 1.0
    assert model.phase is READING

    _run(model, timing.pen_enter_ms / 2)
    assert model.phase is ANALYSIS
    assert model.requested_phase is ANALYSIS
    assert model.is_transitioning is False
    assert model.pen_alpha == pytest.approx(1.0)
    assert model.writing_stage is WritingStage.WRITING
    assert model.writing_stage_progress == pytest.approx(0.0)


def test_analysis_entry_skips_the_settle_wait_when_no_sheet_is_in_flight() -> None:
    timing = AnimationTiming()
    model = _landed_model()
    assert model.incoming is None

    model.set_phase(ANALYSIS)

    _run(model, timing.pen_enter_ms / 2)
    assert model.phase is READING
    assert 0.0 < model.pen_alpha < 1.0

    _run(model, timing.pen_enter_ms / 2)
    assert model.phase is ANALYSIS
    assert model.pen_alpha == pytest.approx(1.0)
    assert model.writing_stage is WritingStage.WRITING


def test_analysis_cycle_runs_writing_rest_turn_and_pen_drop() -> None:
    timing = AnimationTiming()
    model = _analysis_model()
    written_id = _ids(model, RIGHT)[-1]

    _run(model, timing.writing_ms)
    assert model.writing_stage is WritingStage.REST
    assert model.writing_stage_progress == pytest.approx(0.0)
    assert model.turn_progress is None

    _run(model, timing.rest_ms)
    assert model.writing_stage is WritingStage.TURNING
    assert model.turn_progress == pytest.approx(0.0)
    # A blank sheet is revealed beneath the written one.
    assert _ids(model, RIGHT)[-1] != written_id
    assert len(_ids(model, RIGHT)) == 2

    _run(model, timing.turn_ms / 2)
    assert 0.4 < model.turn_progress < 0.6

    _run(model, timing.turn_ms / 2)
    assert model.turn_progress is None
    assert model.writing_stage is WritingStage.PEN_DROP
    assert model.writing_stage_progress == pytest.approx(0.0)
    # The written sheet became a left page and kept its identity.
    assert _ids(model, LEFT)[-1] == written_id
    assert model.leaves(LEFT)[-1].landed is True

    _run(model, timing.pen_drop_ms)
    assert model.writing_stage is WritingStage.WRITING
    assert model.writing_stage_progress == pytest.approx(0.0)
    assert model.leaf_depth(LEFT) > 0.0


def test_reversal_lifts_the_pen_over_the_prototype_exit_window() -> None:
    timing = AnimationTiming()
    model = _analysis_model(clock_ms=2000.0)
    book = (_ids(model, LEFT), _ids(model, RIGHT))

    model.set_phase(READING)

    assert model.requested_phase is READING
    assert model.phase is ANALYSIS

    _run(model, timing.exit_ms - 1.0)
    assert model.phase is ANALYSIS
    assert 0.0 < model.pen_alpha

    _run(model, 1.0)
    assert model.phase is READING
    assert model.is_transitioning is False
    assert model.writing_stage is None
    assert model.pen_alpha == pytest.approx(0.0)
    assert (_ids(model, LEFT), _ids(model, RIGHT)) == book
    assert model.incoming is not None


def test_reversal_resolves_an_in_flight_page_turn() -> None:
    timing = AnimationTiming()
    model = _turning_model()
    assert model.writing_stage is WritingStage.TURNING
    assert 0.0 < model.turn_progress < 1.0
    written_id = _ids(model, RIGHT)[0]

    model.set_phase(READING)

    _run(model, timing.settle_ms - 1.0)
    assert model.phase is ANALYSIS
    assert model.turn_progress is not None

    _run(model, 1.0)
    assert model.phase is READING
    assert model.turn_progress is None
    assert model.is_transitioning is False
    assert _ids(model, LEFT)[-1] == written_id
    assert model.incoming is not None


# --------------------------------------------------- lifecycle and playback


def test_repeating_the_same_phase_event_does_not_restart_the_animation() -> None:
    timing = AnimationTiming()
    model = _in_flight_model()
    before = _snapshot(model)

    model.set_phase(READING)
    assert _snapshot(model) == before
    assert model.is_transitioning is False

    model.set_phase(ANALYSIS)
    _run(model, 300.0)
    elapsed = model.transition_elapsed_ms
    assert elapsed == pytest.approx(300.0)

    model.set_phase(ANALYSIS)
    assert model.transition_elapsed_ms == pytest.approx(elapsed)
    assert model.is_transitioning is True

    _run(model, 100.0)
    assert model.transition_elapsed_ms == pytest.approx(elapsed + 100.0)
    assert model.phase is READING
    assert model.pen_alpha == 0.0
    assert elapsed + 100.0 < timing.settle_ms


def test_repeating_analysis_while_writing_keeps_the_writing_clock() -> None:
    model = _analysis_model(clock_ms=2000.0)

    model.set_phase(ANALYSIS)

    assert model.is_transitioning is False
    assert model.clock_ms == pytest.approx(2000.0)
    assert model.writing_stage is WritingStage.WRITING
    assert model.writing_stage_progress == pytest.approx(2000.0 / 6100.0)

    _run(model, STEP_MS)
    assert model.clock_ms == pytest.approx(2000.0 + STEP_MS)


def test_a_new_task_resets_every_visual_state() -> None:
    timing = AnimationTiming()
    model = _turning_model()
    assert model.leaves()

    model.reset()

    assert model.active is True
    assert model.phase is READING
    assert model.requested_phase is READING
    assert model.clock_ms == pytest.approx(0.0)
    assert model.reading_cycles == 0
    assert model.is_transitioning is False
    assert model.pen_alpha == 0.0
    assert model.pen_lift == 0.0
    assert model.turn_progress is None
    assert model.writing_stage is None
    assert model.leaf_depth(LEFT) == pytest.approx(0.0)
    assert model.leaf_depth(RIGHT) == pytest.approx(0.0)
    assert _ids(model, LEFT) == (1,)
    assert _ids(model, RIGHT) == (2,)
    assert model.incoming is not None
    assert model.incoming.leaf_id == 3
    assert model.incoming.side is LEFT
    assert model.incoming.progress == pytest.approx(0.0)

    # The reset book behaves exactly like a brand new one.
    _run(model, timing.landing_ms)
    fresh = _landed_model()
    assert _snapshot(model) == _snapshot(fresh)


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: ProcessingAnimationModel(), id="not-started"),
        pytest.param(_in_flight_model, id="sheet-in-flight"),
        pytest.param(
            lambda: _transitioning_model(), id="entering-analysis"
        ),
        pytest.param(lambda: _analysis_model(clock_ms=2000.0), id="writing"),
        pytest.param(_turning_model, id="turning"),
    ],
)
def test_a_short_task_can_stop_at_any_time(build) -> None:
    model = build()
    assert model.active is True

    model.stop()

    assert model.active is False
    assert model.is_transitioning is False
    assert model.incoming is None
    assert model.turn_progress is None
    assert model.writing_stage is None
    assert model.has_residual_activity is False

    frozen = _snapshot(model)
    model.advance(10_000.0)
    assert _snapshot(model) == frozen


def test_a_stopped_animation_ignores_further_phase_events() -> None:
    model = _in_flight_model()
    model.stop()
    frozen = _snapshot(model)

    model.set_phase(ANALYSIS)

    assert _snapshot(model) == frozen


def test_pausing_holds_the_animation_without_catching_up() -> None:
    model = _in_flight_model()

    model.set_paused(True)
    assert model.paused is True
    held = _snapshot(model)
    model.advance(2000.0)
    assert _snapshot(model) == held

    model.set_paused(False)
    assert model.paused is False
    model.advance(STEP_MS)
    assert model.clock_ms == pytest.approx(1000.0 + STEP_MS)
    assert model.reading_cycles == 0


def test_hidden_time_is_not_replayed_when_visible_again() -> None:
    model = ProcessingAnimationModel()

    model.set_hidden(True)
    assert model.hidden is True
    model.advance(5000.0)
    assert model.clock_ms == pytest.approx(0.0)

    model.set_hidden(False)
    model.advance(STEP_MS)
    assert model.clock_ms == pytest.approx(STEP_MS)
    assert model.incoming is not None
    assert model.incoming.progress == pytest.approx(
        STEP_MS / AnimationTiming().landing_ms
    )


def test_hidden_time_is_not_replayed_inside_a_transition() -> None:
    timing = AnimationTiming()
    model = _in_flight_model()
    model.set_phase(ANALYSIS)
    _run(model, 300.0)

    model.set_hidden(True)
    model.advance(4000.0)
    assert model.transition_elapsed_ms == pytest.approx(300.0)
    assert model.is_transitioning is True

    model.set_hidden(False)
    _run(model, timing.settle_ms - 300.0)
    assert model.transition_elapsed_ms == pytest.approx(timing.settle_ms)
    assert model.incoming is None
    assert model.phase is READING


def _transitioning_model() -> ProcessingAnimationModel:
    model = _in_flight_model()
    model.set_phase(ANALYSIS)
    _run(model, 300.0)
    return model


def test_a_large_external_step_discards_time_beyond_the_raf_cap() -> None:
    stepped = ProcessingAnimationModel()
    _run(stepped, 50.0)
    jumped = ProcessingAnimationModel()
    jumped.advance(3700.0)

    assert _snapshot(jumped) == _snapshot(stepped)
    assert stepped.reading_cycles == 0
    assert jumped.clock_ms == pytest.approx(50.0)


def test_a_deterministic_long_sample_resolves_a_page_turn() -> None:
    timing = AnimationTiming()
    model = _analysis_model(clock_ms=2000.0)
    written_id = _ids(model, RIGHT)[-1]
    remaining = (
        timing.writing_ms
        - 2000.0
        + timing.rest_ms
        + timing.turn_ms
        + timing.pen_drop_ms
        + 1000.0
    )

    _run(model, remaining)

    assert model.turn_progress is None
    assert model.is_transitioning is False
    assert _ids(model, LEFT)[-1] == written_id
    assert written_id not in _ids(model, RIGHT)
    assert len(_ids(model, RIGHT)) == 1
    assert model.writing_stage is WritingStage.WRITING
    assert 0.0 <= model.clock_ms < timing.writing_ms


def test_resume_with_a_stale_delta_does_not_replay_hidden_time() -> None:
    model = ProcessingAnimationModel()
    model.advance(16.0)
    model.set_hidden(True)
    model.advance(10_000.0)
    model.set_hidden(False)
    model.advance(10_000.0)
    assert model.clock_ms == pytest.approx(66.0)
    model.advance(16.0)
    assert model.clock_ms == pytest.approx(82.0)


def test_long_time_sampling_helper_caps_its_requested_step() -> None:
    model = ProcessingAnimationModel()
    _run(model, 3256.0, step=1000.0)
    assert model.clock_ms == pytest.approx(3256.0)
    assert model.incoming is None


def test_written_ink_survives_return_to_reading_and_reentry():
    model = _analysis_model(clock_ms=2000)
    written_id = model.leaves(RIGHT)[-1].leaf_id
    assert model.ink_progress == pytest.approx(2000 / 6100)
    pose = model.pen_motion
    model.set_phase(READING)
    _run(model, 200)
    assert model.pen_motion == pose  # exit lifts at the current point
    _run(model, 280)
    assert next(leaf for leaf in model.leaves(RIGHT) if leaf.leaf_id == written_id).ink_progress == pytest.approx(2000 / 6100)
    assert model.ink_progress == 0
    model.set_phase(ANALYSIS)
    _run(model, model.timing.settle_ms + model.timing.pen_enter_ms)
    assert next(leaf for leaf in model.leaves(RIGHT) if leaf.leaf_id == written_id).ink_progress == pytest.approx(2000 / 6100)


def test_turn_exposes_source_sheet_and_lands_its_content_without_disappearing():
    model = _analysis_model()
    source = model.leaves(RIGHT)[-1]
    _run(model, model.timing.writing_ms + model.timing.rest_ms)
    assert model.turn.leaf.leaf_id == source.leaf_id
    assert model.turn.leaf.depth == source.depth
    assert model.ink_progress == 0  # blank sheet beneath the turn
    _run(model, model.timing.turn_ms)
    assert model.turn is None
    assert model.leaves(LEFT)[-1].leaf_id == source.leaf_id
    assert model.leaves(LEFT)[-1].kind.value == "turned"
    assert model.leaves(RIGHT)[-1].kind.value == "base"
    assert model.leaves(RIGHT)[-1].ink_progress == 0


def test_reduced_motion_has_static_phase_poses_and_ignores_time():
    model = ProcessingAnimationModel()
    model.set_reduced_motion(True)
    assert model.incoming.progress == pytest.approx(.67)
    frozen = _snapshot(model)
    _run(model, 5000)
    assert _snapshot(model) == frozen
    model.set_phase(ANALYSIS)
    assert model.phase is ANALYSIS
    assert model.incoming is None
    assert model.pen_alpha == 1
    assert model.pen_lift == 0
    assert not model.is_transitioning
    model.reset()
    assert model.phase is READING
    assert model.reduced_motion
    assert model.incoming.progress == pytest.approx(.67)


def test_retargeted_turn_exit_keeps_pen_anchor_and_page_identity():
    model = _turning_model()
    source_id = model.turn.leaf.leaf_id
    anchor = model.pen_motion
    model.set_phase(READING)
    _run(model, 200)
    assert model.pen_motion == anchor
    model.set_phase(ANALYSIS)
    _run(model, model.timing.settle_ms + model.timing.pen_enter_ms)
    assert model.turn is None
    assert any(leaf.leaf_id == source_id for leaf in model.leaves(LEFT))
    assert model.phase is ANALYSIS


def test_exit_from_a_lifted_pen_adds_to_its_current_lift():
    model = _analysis_model(clock_ms=6460)
    assert model.pen_lift == pytest.approx(4)
    model.set_phase(READING)
    _run(model, 240)
    assert model.pen_lift == pytest.approx(12.5)  # existing 4 + half of exit's 17
