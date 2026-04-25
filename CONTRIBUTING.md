# Contributing

Contributions welcome. Here's how to get started.

## Setup

```bash
git clone https://github.com/escipionpedroza147-commits/API-Sentinel.git
cd API-Sentinel
pip install -r requirements.txt
cp .env.example .env
python -m pytest tests/ -v
```

## Guidelines

- All 77 tests must pass before submitting a PR
- New features need tests
- Type hints on all function signatures
- Update pricing in `src/core/pricing.py` when OpenAI releases new models
- Keep the README current

## PR Process

1. Fork → branch → code → test → PR
2. Describe what and why
3. One feature per PR
