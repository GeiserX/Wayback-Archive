# Installation

## Prerequisites

- Python 3.8 or higher
- pip

## From Source

```bash
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive

# Optional: create a virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

pip install -r config/requirements.txt
```

## As a Package

```bash
cd Wayback-Archive
pip install -e .
wayback-archive  # Available as a CLI command after installation
```
