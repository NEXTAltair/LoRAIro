# main.py Startup Efficiency Plan (2026-01-29)

## Status
in-progress

## Scope
- Review and reduce avoidable startup work in `src/lorairo/main.py`.
- Keep behavior stable unless explicitly changed.

## Plan
- Clarify config precedence for `qt.platform` and `qt.font_dir` vs OS auto-detection.
- Avoid duplicate font family enumeration; reuse cached list or limit to debug paths.
- Reduce startup UI forcing (`raise_`, `activateWindow`, extra `processEvents`) to minimum necessary.
- Consider minor micro-optimizations (e.g., `set` lookup for font families).

## Decisions
- No behavior change without confirming desired precedence rules.

## Risks
- Changing platform/font selection order may alter expected UI behavior on some OS setups.
- Reducing window forcing might regress rare startup visibility issues.

## Next Steps
- Confirm intended precedence with maintainer.
- Implement minimal changes + add targeted tests if needed.
