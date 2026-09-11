# Official database and evaluator restoration

Date: 2026-09-04 (Asia/Shanghai)

- Source: database archive linked by the official OSU-NLP-Group/TravelPlanner
  README (Google Drive file `1pF1Sw6pBmq2sFkJvm-LzJOqrmfWoQgxE`).
- Downloaded archive: 59.0 MB; ZIP integrity test passed; 307,666,432 bytes
  uncompressed; no absolute or parent-traversal paths.
- Restored without overwriting existing reference JSONL files:
  `accommodations`, `attractions`, `background`, `flights`,
  `googleDistanceMatrix`, and `restaurants` under the official `database/`.
- Loaded row counts: 3,827,360 flights; 9,551 restaurants; 4,285
  accommodations; 5,302 attractions.
- Conda `llm-learning` received the missing official runtime dependencies
  `func_timeout` and `gradio`; `gdown` was used only for the official archive.
- Official Hugging Face validation configuration is cached locally: 180 rows,
  with validation row 1 matching the Stage-A submission query.
- Official tracked source files remained unchanged. CSV/TXT database files are
  excluded by the repository's existing `.gitignore`.
