# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two self-contained HTML files live in `analysis/technology/`:
- `AI-Compute-Industry-Chain.html` — interactive Chinese-language visualization of the AI 算力 (compute) industry chain.
- `HBM-supply-chain.html` — HBM 国产化设备链 deep-research dossier.

No build step, no dependencies, no framework, no package manager. Open either file directly
in a browser; edit in any text editor. There are no test, lint, or build commands to run.

## Architecture

Everything lives in one file: markup, CSS (in `<style>`), and JS (in `<script>`) at the
end of `<body>`. Vanilla JS, no framework. Four visual sections share one data source:

1. **Concentric "factory" rings** (`.ring.r0`–`.r5`) — six nested circles, GPU brain at
   center (r0) outward to networking (r5). Clicking/hovering a ring updates the `.info`
   side panel via `show(k)`.
2. **Info panel** (`.info`) — detail view for the selected ring.
3. **Matrix cards** (`.mcards`) — generated in JS from the same `data` object; clicking
   a card calls `show(k)` and scrolls back to the rings.
4. **Static sections** — flow chain, three-keyword cards (PCB/CPO/MLCC), and insight
   block; these are hand-written HTML, not data-driven.

### The single source of truth

`data` (an object keyed `r0`–`r5`) drives both the ring info panel and the matrix cards.
Each entry has: `tag`, `c` (CSS color var), `title`, `role`, `desc`, `players`,
`dom` (国产水平 1–5), `domLabel` (e.g. `"国产 ★★（有但受制裁）"`), and `profit`.
`oneLiner` is a parallel object adding the matrix card subtitle.

When adding/editing a link in the chain, change it **once** in `data` — both the ring
panel and the matrix card render from it.

### Conventions worth preserving

- **Domestic-level color scale** (`domColor` map): `1=#dc2626` red (weakest) →
  `5=#0891b2` teal (strongest). Meter bar widths are `dom*20%`. The matrix card
  border-left class `lv1`–`lv5` mirrors this. Keep all three in sync when adding a level.
- **Ring hit-targets**: the `.ring` circles have `pointer-events:none`; the inner label
  `<div>` re-enables events (see the comment near line 258). This prevents an outer ring
  from swallowing clicks meant for an inner ring. Don't move events back onto `.ring`.
- **Star ratings** (`★★`) are embedded in `domLabel` and parsed out via regex
  (`d.domLabel.match(/★+/)`) for display — keep the `★` characters if you edit a label.
- CSS custom properties (`--c0`…`--c5`, `--bg`, `--ink`, etc.) are defined on `:root`
  and referenced in both CSS and the `data[k].c` values.

## Content note

The page is dated 2026/06/24 and carries a "不构成投资建议" (not investment advice)
disclaimer in the footer. Company names, market-share claims, and dates are editorial
content — verify against current sources before treating as fact.
