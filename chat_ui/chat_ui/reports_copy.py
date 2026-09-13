"""Wording for the Reports section.

A module of its own for the reason `admin_copy.py` is one: the Reports section is
a third surface with its own reader (anyone following the project, signed in or
not), and its strings should not be declared inside either of the other two.

The section's copy is Spanish, as specified for it; the status labels stay in the
workflow's English because they are the same words the story files and the
index boards use, and a reader cross-checking a report against its board should
find the same word on both.

Voice follows `copy.py`: state what is there and what to do next, no apology,
and never describe the interface by how it is built -- the one exception is the
read fault, which names `.agents/reports/` because that path *is* the thing the
reader can go and check.
"""

# --- Masthead and navigation ---------------------------------------------
WORDMARK = "HARNESS"
SECTION_TITLE = "Reports"
PAGE_TITLE = "Reports · Harness"
NAV_DISCLOSURE_LABEL = "PRDs"
NAV_ALL_LABEL = "Todos los reports"
NAV_DONE_TEMPLATE = "{done}/{total} done"
NAV_NO_STORIES = "Sin stories aún"

# --- Feed toolbar --------------------------------------------------------
SEARCH_PLACEHOLDER = "Buscar por story, PRD o commit"
SEARCH_LABEL = "Buscar reports"
STATUS_FILTER_LABEL = "Filtrar por estado"
STATUS_FILTER_ALL = "Todos los estados"

# --- Status labels -------------------------------------------------------
# Keyed by `app.services.reports.STATUS_*`. `components/reports.py` holds the
# matching inks, so a status gains a label here and a tone there, nowhere else.
STATUS_LABELS = {
    "done": "Done",
    "in-progress": "In progress",
    "planned": "Planned",
    "blocked": "Blocked",
}

# --- Feed states ---------------------------------------------------------
EMPTY_TITLE = "Todavía no hay reports"
EMPTY_BODY = "Van a aparecer acá cuando se completen stories."
EMPTY_PRD_TITLE = "Sin stories completadas todavía"
EMPTY_PRD_TEMPLATE = (
    "{prd} todavía no tiene reports. Se van a agregar acá a medida que las "
    "stories se completen."
)
NO_MATCH_TITLE = "Sin resultados"
NO_MATCH_BODY = "Ningún report coincide con los filtros. Probá con otro término o cambiá el estado."
CLEAR_FILTERS_LABEL = "Limpiar filtros"
FAULT_TITLE = "No se pudieron leer los reports"
FAULT_BODY = (
    "Hubo un problema leyendo los archivos en .agents/reports/. Revisá los "
    "permisos de la carpeta e intentá de nuevo."
)
RETRY_LABEL = "Reintentar"
PRD_NOT_FOUND_TITLE = "Ese PRD no existe"
PRD_NOT_FOUND_BODY = "No hay ningún PRD con ese identificador. Elegí uno de la barra lateral."

# --- Card ----------------------------------------------------------------
CARD_NO_SUMMARY = "Report pendiente de generación."
TITLE_SEPARATOR = " · "
NO_DATE = "—"

# Month abbreviations for "7 sep 2026". Dates are formatted in Python, where
# the format can run; components only ever see the finished label.
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

# --- Detail --------------------------------------------------------------
BREADCRUMB_ROOT = "Reports"
BREADCRUMB_SEPARATOR = "/"
SUMMARY_HEADING = "Summary"
ACCEPTANCE_HEADING = "Acceptance criteria"
FILES_TEMPLATE = "Files changed — {count} archivos"
FILES_SINGLE = "Files changed — 1 archivo"
VALIDATION_TEMPLATE = "Validation results — {passed}/{total} pasaron"
VALIDATION_EMPTY = "Validation results — sin checks registrados"
COMMIT_LINK_LABEL = "Ver commit {sha} en GitHub"
NO_REPORT_TITLE = "Todavía no hay report para esta story"
NO_REPORT_TEMPLATE = (
    "El report se genera cuando la story se completa. Estado actual: {status}."
)
VIEW_PRD_TEMPLATE = "Ver {prd} completo"
LAST_STORY = "Última story del PRD"
FIRST_STORY = "Primera story del PRD"
PREV_TEMPLATE = "← {label}"
NEXT_TEMPLATE = "{label} →"
STORY_NOT_FOUND_TITLE = "Esa story no existe"
STORY_NOT_FOUND_BODY = "No hay ninguna story con ese identificador en este PRD."
BACK_TO_REPORTS = "Volver a Reports"
