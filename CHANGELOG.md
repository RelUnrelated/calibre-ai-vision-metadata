## [1.0.0] - 2026-10-09

漫元 MetaManga 首个独立发行版。基于原项目持续改进，完成中文界面、AI 元数据识别、翻译、多语言标题解析和 Calibre 元数据审核编辑功能。

## [1.6.29] - 2026-10-09

### Changed
* 对外名称统一为“漫元 / MetaManga”，更新 Calibre 插件显示名称、工具栏名称、说明文字和打包文件名。
* 保留内部包名 `ai_vision_metadata`，确保已有配置和升级数据继续兼容。

## [1.6.28] - 2026-10-09

### Fixed
* 修复包含中文前缀、括号副标题、汉化信息、作者社团和日文后缀的复杂文件名被截断为前半段标题的问题。
* 增加该类混合标题的回归测试，保护完整原文标题和翻译流程。

## [1.6.27] - 2026-10-09

### Fixed
* 修复汉字与韩文混合标题被误判为中文的问题。包含韩文、日文假名或实质英文内容的混合标题会进入中文翻译流程；中文标题中的 `Vol. 2` 等编号仍保留原有判定。

## [1.6.26] - 2026-10-09

### Added
* 标题语言识别和翻译支持韩语、英语；保留中文标题不重复翻译，并对韩文未翻译结果执行校验和修复请求。

## [1.6.25] - 2026-10-09

### Fixed
* 支持多个作者的统一格式。作者之间的 `、`、逗号和 `&` 会规范为 `作者1 & 作者2`，并正确拆分写入 Calibre。

## [1.6.24] - 2026-10-09

### Changed
* 隐藏标题字段旁固定的“（覆盖）”提示。

## [1.6.23] - 2026-10-09

### Changed
* 删除插件下拉菜单中的“自动应用”和“逐本审核”两个入口，统一由主插件按钮和配置复选框控制。
* 将复选框改名为“点击插件时直接应用AI元数据”。

## [1.6.22] - 2026-10-09

### Changed
* 审核窗口顶部仅保留 AI 模型、耗时和置信度，移除依据、来源、警告和“需要审核”信息。
* 配置菜单改名为“配置”，增加“点击插件时自动应用”选项，默认不勾选。

## [1.6.21] - 2026-10-09

### Changed
* 隐藏丛书、序号、出版社和出版日期的固定“（覆盖）”提示。
* 汉化插件历史记录产生的英文标题和备注警告。

## [1.6.20] - 2026-10-09

### Fixed
* 修复标签和语言下拉只显示当前书籍值的问题。审核窗口现在整合 Calibre 分类接口、字段接口，并扫描当前书库所有书籍的原生元数据作为最终回退。

## [1.6.19] - 2026-10-09

### Changed
* 审核窗口改为完整元数据编辑器，移除字段复选框，直接保存当前显示内容。
* 丛书和序号改为普通可编辑输入框；标签候选值增加当前书库分类和自定义字段回退读取。

## [1.6.18] - 2026-10-09

### Fixed
* 将 Calibre 以字符串形式返回的 `0101-01-01` 和 `0001-01-01` 未定义日期过滤为空。

## [1.6.17] - 2026-10-09

### Changed
* 移除审核窗口中的原始文件名编辑行。
* 修复标签候选值读取，改为读取当前书库分类；语言下拉预置常用语种并显示中文全称。
* 出版日期默认不勾选，并将 Calibre 未定义日期显示为空。

## [1.6.16] - 2026-10-09

### Changed
* 逐本审核中的语言和标签改为可编辑下拉框：可以从书库已有值中选择，也可以直接输入；继续支持覆盖或追加。

## [1.6.15] - 2026-10-09

### Added
* 逐本审核窗口现在会读取当前书籍的已有元数据。AI 未提供的字段会以现有值填充，作者、系列、标签、语言、出版社、日期、标识符和备注均可直接编辑并勾选写回。

## [1.6.14] - 2026-10-09

### Changed
* 将插件菜单、配置项、审核窗口、运行状态、来源信息和诊断提示统一汉化为简体中文；保留 AI、模型名、字段值和原始文件名等必要原文。
* 更新测试断言并重新生成安装包。

## [1.6.13] - 2026-10-09

### Fixed
* Validate AI-generated title numbering before selecting the final translation. When the source work has no volume/chapter/range evidence, remove unsupported explicit volume/chapter markers and added terminal numeric suffixes, including compact, decimal, and range forms. Publication/annotation numbers cannot supply source-title evidence.
* Preserve internal source-title digits and possible conversions from written Chinese/Japanese numerals. Real work numbering continues to use the protected source. Keep original filename/Comments and raw provider titles for audit, and record a warning when unsupported numbering is removed.
* Add the reported magazine `Vol.18` regression through normalization and a real calibre write. Correction is local and requires no additional API request.

## [1.6.12] - 2026-10-09

### Changed
* Disable DeepSeek thinking by default and cap non-thinking completions at 2048 tokens. Add a saved DeepSeek thinking toggle (8192-token cap when enabled). Other providers retain their existing API parameters and model choices.
* Request compact title/translation/language/role JSON, remove duplicate full parser records from context, and place static instructions ahead of per-book input. Record provider reasoning-token counts when supplied and the effective DeepSeek thinking mode.
* Request separate `filename_roles.title_confidence`. If other roles are uncertain, allow title/filename-Comments-only automatic updates only when title confidence is at least 0.85, the literal title exactly matches the deterministic unbracketed title, language is classified, and all existing quote/conflict checks pass. Preserve authors, series/index, and language in this restricted write mode; avoid role-correction calls when a valid translated title can already be written.
* Add regressions for default/optional thinking payloads, token limits, scoped title confidence, single-request title-only behavior, and preservation of unrelated fields in a real calibre database. Runtime speedup still requires live-provider measurement.

## [1.6.11] - 2026-10-09

### Fixed
* Reject kana-bearing AI translation candidates before choosing between `translated_title` and `title`, so a source echo cannot override a valid Chinese title. Track missing Japanese translations explicitly and skip automatic writes when no translation is available.
* Allow at most one corrective metadata request for a Japanese title left untranslated or with uncertain filename roles. Reapply all quote/confidence checks; continued uncertainty still skips writing. Correction requests use the same configured provider/model and report combined successful-request timings and counts.
* Expand Last Run Results details with selected/provider titles, source-language hint, translation status, verified filename roles/confidence, and warnings. Add the two reported mixed Han/kana titles as regressions, including bounded correction and diagnostics tests.

## [1.6.10] - 2026-10-09

### Fixed
* Treat Han-only source titles as language-ambiguous candidates instead of confirmed Chinese. Ask the AI for source `filename_roles.title_language` in the same request, including when a saved prompt is used. Accept translations of validated Japanese all-kanji titles without overwriting them with source text.
* Preserve titles classified as Chinese and separate Chinese titles paired with kana-bearing Japanese originals. Unknown Han-title language, low confidence, invalid quotes, and contradictory classifications cannot enable automatic writes. Older responses without a language field retain conservative source wording.
* Recognize halfwidth kana and Katakana Phonetic Extensions as Japanese evidence. Display and record source-language hints; retain numbering, authors, filename Comments, and existing quote validation.

## [1.6.9] - 2026-10-09

### Changed
* Adapt Kavita's explicit volume/chapter naming conventions to Python: English/French volume markers, Chinese/Japanese volume markers, explicit English/Chinese/Japanese chapters, decimals, ranges, and first-marker precedence. Include upstream attribution and GPLv3 notice in the plugin ZIP.
* Preserve local event-code, Circle(Author), bilingual-title, and terminal-number-as-volume rules. Standalone numbering groups are eligible; publication metadata is not. AI role quotes may omit separate numbering groups without discarding validated numbering.
* Keep chapters/ranges in analysis records and optional review. Include source chapter numbers in formatted titles without combining them into calibre's numeric series index. Volume ranges and chapter-only works preserve existing library series/index values.
* Add regression coverage for conflicts, translation, bracketed markers, decimals, ranges, and actual calibre database/review behavior.

## [1.6.8] - 2026-10-09

### Changed
* Ask the AI to distinguish title, personal authors, circle, and annotations by meaning in the same metadata request. Return verbatim input quotes in `filename_roles`; deterministic first-bracket author guesses are hints and can be corrected.
* Validate role quotes against the selected filename/current-title input before using them. Reject invented text, annotation-as-title/author assignments, overlapping role fields, and conflicts with explicit Circle(Author) evidence or clear Chinese title wording.
* Use validated source title/author assignments for metadata normalization, retaining Chinese wording and translating Japanese originals. Optional review shows the identified source title/authors, and audit records retain role assignments.
* Skip uncertain (or role confidence below 0.8) and invalid classifications in automatic mode without dialogs. Last Run Results records the skip reason. Responses without role assignments retain the prior compatibility path.

## [1.6.7] - 2026-10-09

### Fixed
* Fill empty Comments when `#original_filename` is unavailable by preserving complete input title text before renaming. Prefer filename/input backups recovered from the same book's plugin audit history, including older releases that skipped Comments but recorded the pre-write title.
* Retain the captured text and its provenance in subsequent audit records, so reanalysis cannot replace a filename backup with the newly translated title. Custom-column filenames remain authoritative; calibre directory names and AI summaries are never used as filename backups.
* Show the Comments source in optional review and preselect a supported backup when filling empty Comments. Historical/current-title fallbacks preserve existing nonempty Comments and remain explicitly unverified as original filenames. Snapshot conflict and library checks still apply.
* Prefer unbracketed middle title text in `[Author]Title[translation][notes]` filenames. Trailing annotations such as `[禁漫去码]` no longer become Chinese titles; bracketed-title support remains available when no unbracketed title exists.
* Reject AI titles that repeat source annotation fields, while retaining valid AI translations of Japanese originals. Recovered historical input can also repair a current title already misidentified by an older release.

## [1.6.6] - 2026-10-09

### Fixed
* Format numbered titles as base name, one space, and the source volume number (for example `直到紫藤花盛开 2`). Use the same base name without the volume as series, rather than accepting a different AI series name.
* Normalize compact numbers and explicit volume markers in both automatic writes and optional review. Source volume evidence remains required; standalone works and ambiguous parenthesized filename suffixes do not acquire series/index values.
* Preserve original filename/Comments and Japanese original-title evidence while formatting the final title. Apply the naming rule independently of saved provider prompts.

## [1.6.5] - 2026-10-09

### Changed
* Toolbar and **Analyze Selected Books (Auto Apply)** now analyze and write selected books sequentially without per-book confirmation. Optional **Review Each** remains available for manual edits, with every nonempty title checked by default.
* Skip missing/failed/titleless/conflicting books and continue automatically. Automatic errors use the status bar; **Last Run Results** lists written/skipped books instead of interrupting the queue with dialogs.
* Preserve filename-derived author, series/index, language, and original-filename Comments updates. Automatic mode never writes tags, publisher, publication dates, identifiers, empty suggestions, or a directory fallback into Comments.
* Record per-attempt header/body timings, retry count/wait, response length, and output token count when supplied by the provider.

### Fixed
* Require explicit source volume evidence before suggesting series/index. Standalone titles no longer populate series, and automatic writes require a valid series/index pair. Existing library series values are preserved when no supported replacement exists.
* Prefer current Unicode metadata over calibre's potentially truncated/transliterated directory fallback, including when the current title proves that no work title is available.
* Dispatch job completion and database/UI updates on the GUI thread. Library identity, analysis snapshots, and audit records remain enforced for automatic writes.

## [1.6.4] - 2026-10-09

### Fixed
* Decode complete JSON objects individually when a provider echoes `{"type":"json_object"}` before its actual metadata result. Ignore format/schema preambles and support separate Markdown code blocks without joining unrelated objects.
* Reject ambiguous multiple metadata results and incomplete JSON instead of using nested fragments or guessing repairs.
* Add a DeepSeek response regression through the real calibre review dialog and request exactly one metadata object in the appended context instructions.

## [1.6.3] - 2026-10-09

### Fixed
* Restore manual editing and checkbox selection for tags, publisher, publication date, and identifiers. AI suggestions stay empty and unchecked; only explicitly entered and approved values are written.
* Validate manual dates and identifiers in the review dialog before closing it; invalid input cannot cause a partial metadata write.
* Recover title evidence from the complete current title when calibre's directory fallback is truncated or contains only metadata groups. Clean away filename metadata before displaying the title and preserve AI translations of supported Japanese title evidence.
* Preserve explicit Chinese titles after author/group brackets and extract their series/volume without letting AI replace the title.
* Keep every provider text-only and preserve the existing review, library, and conflict checks.

## [1.6.2] - 2026-10-09

### Fixed
* Distinguish `#original_filename` from calibre directory fallback; strip the matching directory book ID instead of treating `(2)` as a volume or duplicate filename.
* Mark fallback sources clearly, keep their Comments unchecked, and never overwrite the source filename column.
* Require manual title confirmation when the filename has no title; reject unsupported AI title/series/volume guesses.
* Parse bracketed Chinese titles while preserving author/circle information and actual title volume numbers.
* Remove all image payload branches and blind batch writes. Every queued book receives manual review.
* Cancel queued analysis on library changes and reject metadata/source-column conflicts before writing.
* Disable tag, publisher, date, and identifier writes; retain existing values and render filename markup literally in Comments.
* Preserve images/ and translations/ paths in the installable ZIP.

## [1.6.1]

* Restore filename-derived title, author, circle, translation group, event, edition, series, volume, language, and exact original-filename Comments.
* Existing Chinese filename titles take precedence over AI translations.
* Add DeepSeek at `https://api.deepseek.com/v1` with default model `deepseek-flash`.
* Keep cover upload, AI tags, publisher, publication dates, and identifiers disabled.
* Add sequential per-book review, analysis snapshots, calibre API writes, and parser/schema/writer tests.

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
