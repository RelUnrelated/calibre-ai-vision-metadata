## [1.1.0] - 2026-06-??

### Added:

* Added support for OpenRouter.ai
* Added support for Anthropic's new model availability API
* Improved handling of "Service Unavailable" and "Rate Limited" errors, retrying with exponential backoff
* Added value for week number to series index options
* Added text descriptors to series index options

### Fixed:

* Filter out series index options that are incompatible with Calibre
* Limit image size, resizing if needed, to fix error from input size being too large
* Improved results filtering to eliminate extraneous info outside of JSON data

## [1.0.0] - 2026-03-25
_Initial public release of AI Vision Metadata plugin_

## [0.9.0] - 2026-02-26
_Pre-release testing, architecture validation, and UI stabilization._