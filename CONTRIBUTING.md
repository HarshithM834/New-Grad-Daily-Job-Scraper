# Contributing to CareerOps

Thanks for helping improve an accessible job-search tool for new graduates.

## Quick development setup

1. Fork the repository and create a topic branch (`fix/redirect-handler`, `feat/source-adapter`, etc.).
2. Install Python requirements and Playwright Chromium as documented in the main README.
3. Run `python -m unittest discover -s tests -v` before opening a pull request.
4. For dashboard changes, run `cd web && npm install && npm run build` and check keyboard navigation, visible focus and both narrow and wide layouts.
5. Open a PR explaining the problem, what changed, how you tested it and any limitations.

## Useful contributions

- Source adapters and safe pagination behavior for official/public job listings.
- Reliable ATS application-link extraction and meaningful failure reasons.
- Small, focused tests with fixtures that do not include personal data.
- Accessibility improvements, clear documentation and reproducible bug reports.

## Security and privacy

Do **not** commit service-account JSON, API keys, personal trackers, applicant notes, or browser session cookies. Use sanitized example records. Never bypass a site's authentication, CAPTCHA, anti-bot controls, or rate limits. Submit potential vulnerabilities privately to the maintainer rather than in public issues.

## Style

Favor small, dependency-light changes with explicit error handling and accurate reporting. Do not claim features are validated unless a test or real run demonstrates them.