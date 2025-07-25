from setuptools import setup, find_packages

setup(
    name="csv-assistant",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn[standard]>=0.27.0",
        "openai>=1.2.0",
        "pandas>=2.0.0",
        "matplotlib>=3.5.0",
        "seaborn>=0.12.0",
    ],
    entry_points={
        "console_scripts": [
            "csv-assistant=cli:main",
        ],
    },
    python_requires=">=3.8",
    author="Yunfeng Liu",
    description="A ChatGPT-powered CSV data analysis assistant",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
) 