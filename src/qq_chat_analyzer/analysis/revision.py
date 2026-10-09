"""Revision of the analysis semantics recorded in newly generated reports."""

# Advance when acquisition interpretation, identity, filtering, tokenization,
# or statistical rules change results. Presentation-only changes do not advance it.
# v2: local burst bounds, unordered expression pairs, message-level expression
# counts, mixed-expression classification, and intact laughter tokens.
# v3: sender filtering is scoped to the stable sender identity, so messages from
# a member who shares a nickname are no longer removed (Smart Profile decisions
# and burst-run continuity); interactive automation evidence is kept for review
# and never deletes messages on its own.
ANALYSIS_REVISION = "echo-analysis.v3"
