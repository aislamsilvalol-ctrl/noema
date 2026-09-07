# Contributing

Aquilante is research code held to engineering standards. Three rules:

1. **Measure before you add.** A new model or feature comes with a
   benchmark row (`aquilante benchmark`) and, if it is an ingredient, an
   ablation switch. If it does not improve the table, say so in the pull
   request; that is a result too.
2. **Never commit learner data.** Synthetic events only. Adapters read
   files the user downloads under the dataset's licence.
3. **Reproducibility is not optional.** Seeds in configs, dataset versions
   in runs, git commit in every run record.

Setup:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[torch,dev]"
.venv/bin/pytest
.venv/bin/ruff check aquilante tests && .venv/bin/ruff format --check aquilante tests
```

Style: `ruff` with the configuration in `pyproject.toml`; docstrings that
explain the decision, not the syntax; no "state-of-the-art" anywhere.
