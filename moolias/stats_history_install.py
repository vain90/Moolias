from __future__ import annotations

from moolias.stats_history_state import enrich_ui_state_with_history


def install_history_state_enrichment() -> None:
    # The redesigned alias router imports the UI state loader by value, while the
    # remaining redesigned pages resolve it from moolias.ui at request time. Keep
    # both references on the same history-aware loader.
    import moolias.alias_table_ui as alias_table_ui
    import moolias.ui as ui

    current = ui._load_ui_state
    if getattr(current, "_moolias_history_enriched", False):
        alias_table_ui._load_ui_state = current
        return

    async def history_aware_state(request):
        state = await current(request)
        return await enrich_ui_state_with_history(request, state)

    history_aware_state._moolias_history_enriched = True
    ui._load_ui_state = history_aware_state
    alias_table_ui._load_ui_state = history_aware_state
