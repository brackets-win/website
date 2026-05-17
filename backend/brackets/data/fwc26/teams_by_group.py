"""
2026 FIFA World Cup group assignments (December 2025 draw).

Seeds 1–48 map to groups A–L (four teams each) in draw-table order.
"""

# group code -> teams in standings-table order (positions 1–4)
TEAMS_BY_GROUP: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Türkiye"],
    "E": ["Germany", "Curaçao", "Côte d'Ivoire", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cabo Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "Congo DR", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Stable contestant identifiers (override auto-slug where needed)
TEAM_IDENTIFIERS: dict[str, str] = {
    "United States": "united-states",
    "Côte d'Ivoire": "cote-divoire",
    "Curaçao": "curacao",
    "Cabo Verde": "cabo-verde",
    "South Korea": "south-korea",
    "South Africa": "south-africa",
    "Saudi Arabia": "saudi-arabia",
    "New Zealand": "new-zealand",
    "Bosnia and Herzegovina": "bosnia-herzegovina",
    "Czechia": "czechia",
    "Türkiye": "turkiye",
    "Congo DR": "congo-dr",
}
