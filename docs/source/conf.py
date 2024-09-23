import os
import sys
sys.path.insert(0, os.path.abspath('../../..'))  # プロジェクトルートへのパス
sys.path.insert(0, os.path.abspath('../../src'))  # srcディレクトリへのパス


# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'lora_dataset_toolsy'
copyright = '2024, NEXTAltair'
author = 'NEXTAltair'
release = '1.01'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.autosummary',
    'sphinx.ext.ifconfig',
    'sphinx.ext.githubpages',
    'myst_parser',
]
autosummary_generate = True 

templates_path = ['_templates']
exclude_patterns = []

language = 'ja'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
