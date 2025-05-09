from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kimiconfig",
    version="0.2.4",
    author="kimifish",
    author_email="kimifish@proton.me",
    description="A flexible configuration management system for Python applications",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kimifish/kimiconfig",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pyyaml>=5.1",
        "rich>=10.0.0",
        "typing>=3.7.4",
    ],
) 