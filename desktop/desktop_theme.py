"""Shared visual constants for the FitLens desktop application."""


COLORS = {
    "background": "#101315",
    "sidebar": "#171B1E",
    "card": "#1B2024",
    "card_border": "#2A3238",
    "text": "#F4F7F8",
    "muted": "#9AA6AD",
    "accent": "#61D7C5",
    "accent_dark": "#1D4A47",
    "green": "#6FE7A1",
    "green_dark": "#173A2B",
    "yellow": "#F6CF70",
    "yellow_dark": "#483B1C",
    "red": "#FF8F87",
    "red_dark": "#4D2727",
}


LOOKBACK_CHOICES = {
    "Past year (recommended)": ("days", 365),
    "Past 6 months": ("days", 182),
    "Past 2 years": ("days", 730),
    "All of my history": ("all", None),
}
