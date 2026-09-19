# Background sampler

This is a production-isolated Textual experiment for choosing the first visual
direction for the public presentation.

Run it from the repository root:

```bash
.venv/bin/python demos/textual_background_sampler.py
```

If your shell exports `NO_COLOR=1`, use this for the color study:

```bash
env -u NO_COLOR TERM=xterm-256color COLORTERM=truecolor \
  .venv/bin/python demos/textual_background_sampler.py
```

The sampler intentionally runs at 12fps and uses only deterministic procedural
cells. It does not read season state, call models, or depend on stock media.

Controls:

- `1` — Dust & Halation: warm light leak, film grain, and drifting motes.
- `2` — Fractal Bloom: an evolving Julia field with luminous recursive edges.
- `3` — Nocturne Signal: spectral waves, radar-like ridges, and soft scan noise.
- `Space` — pause/resume.
- `H` — hide/show the sampler label.
- `Q` or `Escape` — quit.

The code is deliberately shaped as a future media seam: later, a public scene
can choose between a procedural background, a preprocessed stock-video loop, or
a static fallback without changing story/runtime code.
