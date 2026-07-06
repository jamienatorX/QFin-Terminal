# UI UX Pro Max Skill Setup for QFin Terminal

The UI UX Pro Max repository is not a normal Figma or Lovable plugin. It is an npm CLI package that installs AI design-skill files for coding assistants.

Official npm package:

```bash
ui-ux-pro-max-cli
```

The CLI command it provides is:

```bash
uipro
```

## What was added to this repo

A root `package.json` was added with these scripts:

```bash
npm run uiux:versions
npm run uiux:init:all
npm run uiux:init:codex
npm run uiux:init:claude
npm run uiux:init:cursor
npm run uiux:update
npm run uiux:uninstall
```

## How to install locally

From the root of this repo:

```bash
npm install
npm run uiux:init:all
```

Or install globally:

```bash
npm install -g ui-ux-pro-max-cli
uipro init --ai all
```

## Recommended for QFin Terminal

If you are using ChatGPT/Codex-style workflow:

```bash
npm install
npm run uiux:init:codex
```

If you also use Cursor:

```bash
npm run uiux:init:cursor
```

If you use Claude Code:

```bash
npm run uiux:init:claude
```

## Important Notes

- Do not install old `uipro-cli`; use `ui-ux-pro-max-cli`.
- This does not directly change the Lovable frontend by itself.
- This gives your AI coding/design workflow better UI/UX rules.
- For Lovable, copy the QFin Lovable prompt from `docs/qfin-component-system.md`.
- For Figma, the Figma MCP tool call limit must reset before we can push more components directly.

## QFin Design Use

Use this skill together with:

```text
docs/qfin-component-system.md
```

That file contains the actual QFin Terminal-specific design system, colors, components, news UI rules, and chat behavior fixes.
