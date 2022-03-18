#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from pathlib import Path

from setuptools import setup


def get_version(package):
    """
    Return package version as listed in `__version__.py`.
    """
    version = Path(package, "__version__.py").read_text()
    return re.search("__version__ = ['\"]([^'\"]+)['\"]", version).group(1)


def get_long_description():
    """
    Return the README.
    """
    long_description = ""
    with open("README.md", encoding="utf8") as f:
        long_description += f.read()
    # long_description += "\n\n"
    # with open("CHANGELOG.md", encoding="utf8") as f:
    #     long_description += f.read()
    return long_description


def get_packages(package):
    """
    Return root package and all sub-packages.
    """
    return [str(path.parent) for path in Path(package).glob("**/__init__.py")]


setup(
    name="httpx-caching",
    python_requires=">=3.7",
    version=get_version("httpx_caching"),
    url="https://github.com/johtso/httpx-caching",
    project_urls={
        "Source": "https://github.com/johtso/httpx-caching",
    },
    license="Apache-2.0",
    description="Caching for HTTPX.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Johannes (johtso)",
    author_email="johtso@gmail.com",
    package_data={"httpx_caching": ["py.typed"]},
    packages=get_packages("httpx_caching"),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "httpx==0.22.*",
        "msgpack",  
        "anyio",
        "multimethod",
    ],
    extras_require={},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
    ],
)