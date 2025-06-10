from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="aiden",
    version="0.1.0",
    description="AI Desktop Agent with voice interaction capabilities",
    author="Sahi",
    packages=find_packages(),
    install_requires=[req for req in requirements if not req.startswith('#')],
    entry_points={
        "console_scripts": [
            "aiden=src.main:main",
        ],
    },
    python_requires=">=3.9",
)
