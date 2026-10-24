from setuptools import setup, find_packages

setup(
    name="bugslayer",
    version="1.0.0",
    description="Autonomous Setup & README Verifier for Open-Source Repositories",
    author="NST Hack Day Team",
    packages=find_packages(),
    install_requires=[
        "rich>=13.0.0",
        "google-genai>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "bugslayer=bugslayer.cli:main",
        ],
    },
    python_requires=">=3.10",
)
