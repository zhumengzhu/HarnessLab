# Diagram Conventions

## Purpose

This document defines a strict, reusable style for all Mermaid diagrams in
HarnessLab. The goal is consistency, readability, and low maintenance cost.

## Core Rules

1. Use one diagram per concern
   - Structure: `flowchart`
   - Runtime interactions: `sequenceDiagram`
   - Lifecycle states: `stateDiagram-v2`
   - Data relations: `erDiagram`
   - Schedule: `gantt`
2. Use stable domain names
   - Prefer `Core Loop`, `Model Port`, `Policy Port`, `Tool Runtime`,
     `Session Store`, `Trace Recorder`.
   - Avoid temporary names like `A`, `B`, `X`.
3. Keep labels short and noun-first
   - Good: `Policy Validation`, `Tool Lookup`
   - Avoid full sentences in node labels
4. Keep decision branches explicit
   - Use `allow/deny`, `success/failure`, `assistant/tool`
5. Avoid visual noise
   - No decorative styling unless it conveys semantic meaning
   - Keep edge labels lowercase and concise

## Naming Standard

- Component names: Title Case (`Tool Runtime`)
- Actions on edges: lowercase verbs (`execute`, `record`, `append`)
- State names: lowercase single words (`requested`, `executing`, `recorded`)
- Entity names in ER diagrams: UPPER_SNAKE_CASE (`TOOL_CALL`)

## Diagram Checklist

Before merging a diagram:

- Is the diagram type correct for the content?
- Are terms aligned with architecture contracts?
- Are all branch outcomes explicit?
- Can a new contributor read it in under one minute?
- Does it avoid implementation details that change frequently?

## Change Policy

When a contract name changes, update diagrams in the same PR:

- `docs/architecture/overview.md`
- `docs/architecture/tool-runtime.md`
- `docs/architecture/data-model.md`
- `docs/roadmap.md` (if timeline scope changes)
- `README.md` and `AGENTS.md` when CLI surface or agent phase changes

