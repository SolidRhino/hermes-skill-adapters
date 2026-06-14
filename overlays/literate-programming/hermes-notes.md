
## Hermes Notes

This Hermes-compatible packaging preserves upstream supporting files beside `SKILL.md`:

- `scripts/`
- `references/`
- `assets/`

Before weaving PDFs, check whether these commands are available in the active project environment:

```bash
which bun
which pandoc
which xelatex
which mermaid-filter
```

Treat the generated `.lit.md` file as the source of truth once a project has been converted to a literate program. Tangle before overwriting existing source files, and use verify/diff workflows where available.
