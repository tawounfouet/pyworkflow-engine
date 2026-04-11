"""Minimal AG Grid test to debug 'No Rows To Show'."""

from nicegui import ui


@ui.page("/")
def index():
    ui.label("Test AG Grid").classes("text-h4")

    # Test 1: plain grid with explicit rowData — should ALWAYS work
    ui.label("Test 1: plain grid").classes("text-h6")
    ui.aggrid(
        {
            "columnDefs": [
                {"headerName": "Name", "field": "name"},
                {"headerName": "Age", "field": "age"},
            ],
            "rowData": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
            ],
        }
    ).classes("w-full").style("height: 200px")

    # Test 2: same with html_columns (like run_table)
    ui.label("Test 2: html_columns").classes("text-h6")
    ui.aggrid(
        {
            "columnDefs": [
                {"headerName": "Name", "field": "name"},
                {"headerName": "Status", "field": "status", "cellRenderer": None},
            ],
            "rowData": [
                {"name": "Alice", "status": "<b>OK</b>"},
                {"name": "Bob", "status": "<i>FAIL</i>"},
            ],
        },
        html_columns=[1],
    ).classes("w-full").style("height: 200px")

    # Test 3: grid inside a ui.card (like dashboard)
    ui.label("Test 3: inside card").classes("text-h6")
    with ui.card().classes("w-full"):
        ui.aggrid(
            {
                "columnDefs": [
                    {"headerName": "Name", "field": "name"},
                    {"headerName": "Age", "field": "age"},
                ],
                "rowData": [
                    {"name": "Alice", "age": 30},
                    {"name": "Bob", "age": 25},
                    {"name": "Charlie", "age": 35},
                ],
            }
        ).classes("w-full").style("height: 200px")


ui.run(port=8099, title="AG Grid Debug", dark=True, show=False, reload=False)
