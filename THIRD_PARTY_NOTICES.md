# Kavita naming-rule adaptation

The explicit volume/chapter conventions in `filename_parser.py` are a Python
adaptation informed by Kavita's scanner parser, reviewed on 2026-10-09:

- Project: https://github.com/Kareadita/Kavita
- Source: https://github.com/Kareadita/Kavita/blob/develop/Kavita.Services/Scanner/Parser.cs
- Naming documentation: https://wiki.kavitareader.com/guides/scanner/managefiles/
- Upstream copyright: Copyright 2020-2026, Kavita contributors.
- Upstream license: GNU General Public License v3.0 (GPL-3.0).
- License source: https://github.com/Kareadita/Kavita/blob/develop/LICENSE

This plugin is also distributed under GPLv3; see `LICENSE.md` for the full
license. The adaptation was made on 2026-10-09. It uses Python regular
expressions rather than the C# implementation and does not include the Kavita
server or require .NET. It covers explicit English/French and Chinese/Japanese
volume markers, explicit English and Chinese/Japanese chapter markers, decimal
numbers, ranges, and first-marker precedence for duplicate markers.

Project-specific differences: C/c followed by 2-4 digits remains an event code;
Circle(Author), translation-group, and bilingual-title evidence remains under
the plugin's existing rules; bare terminal title numbers remain volumes.
Chapter values and ranges are recorded separately from calibre's single
numeric series index. Only title text and standalone numbering groups are
eligible; publication metadata cannot supply a work's volume. Other Kavita
language rules, implicit chapter guesses, and folder/embedded-metadata scanning
are not included in this adaptation.
