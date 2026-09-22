from __future__ import print_function
from setuptools import setup, find_packages
import os


here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "requirements.txt"), encoding="utf-8") as f:
    requirements = [
        line.strip()
        for line in f
        if line.strip() and not line.lstrip().startswith("#")
    ]

version = os.environ.get("TION_BTLE_VERSION", "3.3.7.dev1")

setup(
    name='tion_btle',
    version=version,
    long_description="Module for working with Tion breezers",
    url='https://github.com/TionAPI/tion_python/tree/dev',
    install_requires=requirements,
    description='Python module for interacting with Tion breezers',
    packages=find_packages(),
)
