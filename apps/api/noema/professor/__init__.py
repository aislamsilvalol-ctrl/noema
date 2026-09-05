"""The Professor Engine (V3).

Noema stopped being a chat endpoint with a good prompt. This package is the
professor: it parses what the learner wants into a goal (`intent`), turns the
goal into a curriculum (`curriculum`), decides each turn's *move* before any
model is called (`moves`), keeps a student model per journey (`student`),
writes flashcards when a concept lands (`flashcards`), assesses at checkpoints
(`assessment`), remembers in layers instead of resending the transcript
(`memory`, `budget`) and turns the model's reply into structured events the
interface can draw (`blocks`, `events`). `engine.py` composes them for one
turn of `POST /ai/professor`.

The model never chooses the UI, the animation or the move. It teaches.
"""
