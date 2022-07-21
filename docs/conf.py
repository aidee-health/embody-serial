"""Sphinx configuration."""
project = "Embody Serial Communicator"
author = "Espen Westgaard"
copyright = "2022, Espen Westgaard"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
    "myst_parser",
]
autodoc_typehints = "description"
html_theme = "furo"
