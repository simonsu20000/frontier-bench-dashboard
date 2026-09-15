"""Data pipeline for the frontier benchmark dashboard.

Sources fetch upstream leaderboards and emit ScoreRecords; build.py resolves
model identities, classifies provenance, and writes the JSON the site reads.
"""
