"""
UEFA Euro 2024 group assignments (December 2023 final draw).

Seeds 1–24 map to groups A–F (four teams each) in draw-table order.
"""

# group code -> teams in draw-table order (positions 1–4)
TEAMS_BY_GROUP: dict[str, list[str]] = {
    "A": ["Germany", "Scotland", "Hungary", "Switzerland"],
    "B": ["Spain", "Croatia", "Italy", "Albania"],
    "C": ["Slovenia", "Denmark", "Serbia", "England"],
    "D": ["Poland", "Netherlands", "Austria", "France"],
    "E": ["Belgium", "Slovakia", "Romania", "Ukraine"],
    "F": ["Türkiye", "Portugal", "Georgia", "Czechia"],
}

# Stable contestant identifiers (override auto-slug where needed)
TEAM_IDENTIFIERS: dict[str, str] = {
    "Türkiye": "turkiye",
    "Czechia": "czechia",
}
