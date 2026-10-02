# Validation sample

- `coding_sheet.csv`: blind sample of 900 posts (150 per channel), channel hidden, shuffled ids.
- `coding_sheet_key.csv`: private key (id -> channel, model labels). Coders never saw it.
- `coding_sheet_coded.csv`: second-coder labels. **The second coder is an LLM (three Claude Sonnet sub-agents, 300 posts each), not a human.** Each read only its own part, followed the codebook in the prompt, and judged mostly from the first ~250–300 characters of each post.
- `llm_coder_parts/`: the three input/output parts as produced.

Agreement (Cohen's kappa) is computed in `notebooks/05_tone.ipynb`; labels are interpreted only if kappa >= 0.6.
