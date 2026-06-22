# AXIOM Edge serving layer.
# A read-only FastAPI service over the precomputed prediction tables (SQLite).
# The daily pipeline writes predictions; this layer serves them as typed JSON.
# Modeling code is never imported or re-run here.
