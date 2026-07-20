---
name: validate-client-patch
description: Validate changes to the native-plant-finder React/Vite client before finalizing a patch. Use when Codex modifies files under client/, client public data consumers, frontend validation/sanitization logic, geocoding/data-loading code, pagination/rendering behavior, or any app code that affects client-side security, reliability, or user-visible behavior.
---

# Validate Client Patch

## Workflow

Before finalizing any patch that changes client behavior, validate the change from three angles: tests, regression risk, and user/security impact.

1. Inspect the changed client files and nearby tests.
2. Add or update focused tests before running validation.
3. Run unit tests and end-to-end tests.
4. Run a production build when source, config, routing, public data, or deployment behavior changed.
5. Report exactly what was run, what passed, and any untested residual risk.

## Test Expectations

Write tests for both happy and unhappy paths introduced or affected by the patch.

Cover happy paths such as valid inputs, successful data loads, successful geocoding, correct pagination, expected formatting, and expected rendering.

Cover unhappy paths such as invalid user input, malformed or missing data, rejected fetches, empty results, provider errors, rate limits, unsafe URLs, boundary/matching misses, and retry behavior after transient failures.

Prefer unit tests for pure logic, validators, formatters, data clients, geocoder behavior, pagination, and security helpers. Prefer E2E tests for user flows across the rendered app: entering a location, submitting, viewing results, pagination, and visible error states.

## Risk Review

Before finalizing, scan the patch for:

- User-controlled values rendered into links, URLs, text, fetch paths, or query strings.
- External `href` values that need scheme, host, path, and required-parameter validation.
- Fetch/cache behavior that can permanently trap rejected promises or stale failures.
- Input validation gaps for postal codes, city names, coordinates, ecoregion IDs, and numeric fields.
- Rendering assumptions that break on null, empty arrays, unexpected enum values, long text, or non-finite numbers.
- Latency regressions such as extra network round trips before showing paginated results.
- GitHub Pages compatibility issues such as incorrect Vite `base`, absolute paths, or missing public data.

## Commands

Run from `client/`:

```powershell
npm run test
npm run test:e2e
npm run build
```

If `npm run build` fails on Windows with `EPERM` around `client/dist/data/...`, stop the local Vite dev server and rerun the build. Do not treat that filesystem lock as a code failure once the build passes after stopping the server.

Run repository Python tests when the patch touches ETL-generated app data, dataset contracts, or client data preparation:

```powershell
python -m unittest discover tests
```