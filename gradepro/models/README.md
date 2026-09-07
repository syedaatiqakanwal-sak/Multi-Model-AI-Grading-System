# GradePro local models

Large HuggingFace weights live here and are gitignored.

Expected layout (copy, do not commit):

```
models/ai_detector_v2/          # sequence-classification (0=human, 1=ai_generated)
models/plagiarism_detector_v1/  # sentence-transformers SBERT
```

Set `MODELS_DIR` (default `./models`, Docker `/app/models`).
