## [1.2.0] - 2026-09-20

### Added:
* **Blind Batch Processing:** Introduced a bypass mechanism via the context menu, allowing simultaneous metadata application to multiple documents without per-book manual review. Includes a safety-first warning dialog
* **Granular Append/Overwrite Controls:** Replaced static merge logic with explicit "Overwrite" or "Append / Merge" dropdowns for relevant metadata fields

### Fixed:
* Limited the series index input to floating-point numbers with 2 decimal places to strictly align with Calibre's internal format
* Made slight adjustments to the default prompt, explicitly including "editors" and "Managing Editor" to reduce hallucinations on periodicals

## [1.1.1] - 2026-06-19

### Fixed:
* Improved local LLM JSON parsing to aggressively strip markdown formatting and conversational padding
* Added schema validation to detect when models hallucinate keys, replacing silent failures with clear, actionable UI error popups

## [1.1.0] - 2026-06-17

### Added:
* Native OpenRouter integration with dynamic model fetching and automatic fallback routing
* Anthropic integration now uses the dynamic /v1/models endpoint for automatic access to future Claude releases
* Implemented an exponential backoff routine to seamlessly handle Google 503 traffic errors and 429 rate limits
* Added value for week number to series index options
* Added text descriptors to series index options

### Fixed:
* Filter out series index options that are incompatible with Calibre
* Limit image size, resizing if needed, to fix error from input size being too large
* Improved results filtering to eliminate conversational padding outside of JSON data

## [1.0.0] - 2026-03-25
_Initial public release of AI Vision Metadata plugin_

## [0.9.0] - 2026-02-26
_Pre-release testing, architecture validation, and UI stabilization._