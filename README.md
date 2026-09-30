# Teacher Console — Bangla Short-Answer Grading Prototype

A local Streamlit prototype of the teacher's question and rubric workflow from the P2 report
(Figures 4.6–4.7, §4.5.1, §4.6). Grading, semantic scoring and approval are later milestones.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py          # opens http://localhost:8501
.venv/bin/pytest                        # validation and storage tests
```

On first run the worked example from §4.5.6 (water molecule, question `Q01`) is saved as version 1.

## What is implemented

| Report item | Where |
|---|---|
| Home / task selection (Fig 4.6) | `views/home.py` |
| Question and rubric editor (Fig 4.7): weighted concepts, accepted expressions, approved clauses, required items, known wrong ideas with cap / penalty / review-only | `views/editor.py` |
| Validation before saving (FR-05, §4.5.1): IDs, references, weights, mark increments, caps, penalties, overlaps, clause collisions, 2,000-character limit | `grader/validation.py` |
| Immutable versioned configurations (FR-20, Table 4.9): new `config_id` per edit, read-only JSON, SHA-256 content hash, parent link | `grader/store.py` |
| Version history, change summary, integrity check | `views/library.py` |
| NFC normalization, tokens with original offsets, clause segmentation; originals preserved | `grader/normalize.py` |
| Negation / quotation / correction marker warnings in rubric text (§4.5.2) | `grader/normalize.py`, `grader/validation.py` |
| "Test this rubric" preview: exact-match evidence states per rule, highlighted in the original answer (Table 4.5); no marks | `grader/preview.py`, `views/editor.py` |
| Submitted text displayed literally, never as markup (NFR-07) | `ui.literal`, `ui.md_escape` |

Saved configurations live in `data/configs/`. Set `GRADER_CONFIG_DIR` to use another folder.

## Hosted demo

The app runs on [Streamlit Community Cloud](https://share.streamlit.io) (main file `app.py`);
Vercel cannot host Streamlit apps. Hosted storage is temporary, so a banner reads
"Demo deployment: saved questions reset when the app restarts." It appears automatically on
Streamlit Community Cloud and never locally. Set `DEMO_DEPLOYMENT=true` or `false` to override.

## Demo walkthrough

1. **Home** — show the workspace, the locked "Grade answer" card and the progress table.
2. **Question library** — open `Q01`, show the Bangla prompt, 60/40 concept shares, R1 cap 6, W1 cap 2,
   and the passing integrity check.
3. **Edit as new version** — change the maximum mark to `10.25`: the error appears beside the field
   and Save is disabled. Put it back to `10`.
4. Paste C1's clause into W1's confirming clauses: a collision error blocks saving. Remove it.
5. Add a concept, fill it in, and save: `Q01-v2` is created; the library shows v1 unchanged, with
   "Changes from Q01-v1" listed.
6. **Test this rubric** (bottom of the editor): load samples A–E from Table 4.7. D confirms W1
   (cap 2); E is negated, so W1 is only uncertain and nothing is deducted; C (paraphrase) is
   "not detected", never "absent".
7. Type a clause pattern ending in না: a marker warning appears.
8. **New question** — create `Q02` from scratch to show the empty-form validation.
