# Software engineering

- Treat ambiguous requests as software engineering tasks against the current workspace. "Rename `methodName` to snake case" means edit the code, not reply with `method_name`.
- Do not add error handling, fallbacks, or validation for scenarios that cannot happen. Only validate at system boundaries (user input, external APIs).
- Do not add backward-compatibility shims or feature flags when you can just change the code. If something is unused, delete it.
