# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
import json
import urllib.request
import os
import typing
from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                     QComboBox, QPushButton, QMessageBox, QIcon, QPixmap, 
                     pyqtSignal, Qt, QObject, QSpinBox, QMenu, QTextEdit, QTimer, QCheckBox)

from calibre.gui2 import error_dialog, Dispatcher
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob
from calibre_plugins.ai_vision_metadata.config import prefs
from calibre_plugins.ai_vision_metadata.filename_parser import parse_filename, read_filename_source, select_title_evidence
from calibre_plugins.ai_vision_metadata.result_schema import normalize_result, extract_metadata_json
from calibre_plugins.ai_vision_metadata.metadata_writer import apply_metadata_safely, snapshot_metadata, prepare_automatic_update, capture_filename_comments

# This block is only 'True' when PyCharm is reading the code.
# When Calibre runs the code, this is 'False' and gets completely ignored!
if typing.TYPE_CHECKING:
    def load_translations():
        pass


    def _(text: str) -> str:
        return text

try:
    load_translations()
except NameError:
    pass

# Built-in Simplified Chinese UI fallback. This keeps the plugin Chinese even
# when calibre has no compiled locale available; provider/model names remain
# unchanged. User prompts and filename contents are deliberately not translated.
_CALIBRE_TRANSLATE = _
_ZH_UI = {
    'Extract metadata from original filename': '从原始文件名提取元数据', 'AI Provider:': 'AI 服务商：',
    'API Key:': 'API 密钥：', 'Local Base URL (e.g., http://localhost:11434):': '本地服务地址（例如：http://localhost:11434）：',
    'Model Name:': '模型名称：', 'Fetch Available Models': '获取可用模型', 'Network Timeout (seconds):': '网络超时（秒）：',
    'DeepSeek: enable thinking (slower)': 'DeepSeek：启用思考模式（较慢）', 'System Prompt (Advanced):': '系统提示词（高级）：',
    'Restore Default': '恢复默认', 'Are you sure you want to overwrite your custom prompt with the default instructions?': '确定要用默认说明覆盖自定义提示词吗？',
    'Last Run Results': '最近运行结果', 'Show written and skipped books from the last run': '查看上次运行中已写入和跳过的书籍',
    'AI Vision Error': 'AI 元数据错误', 'Missing Key': '缺少密钥', 'Missing URL': '缺少地址',
    'Configure AI Vision': '配置', 'Settings for AI Vision Metadata': 'AI 元数据设置',
    'Auto apply when clicking the plugin': '点击插件时直接应用AI元数据',
    "Please enter your local server's Base URL.": '请输入本地服务器地址。', 'Success': '成功',
    'Models refreshed successfully!': '模型列表刷新成功！', 'Analysis is already in progress.': '分析已经在进行中。',
    'Please select at least one book.': '请至少选择一本书。', 'Analysis finished: {0} written, {1} skipped.': '分析完成：写入 {0} 本，跳过 {1} 本。',
    'Library changed. The remaining analysis queue was cancelled.': '书库已改变，剩余分析队列已取消。',
    'The analysis context or library changed. Metadata was not written.': '分析上下文或书库已改变，未写入元数据。',
    'Get Local Tools:': '获取本地工具：', 'Error': '错误', 'Analyze Selected Books (Auto Apply)': '分析选中的书籍（自动应用）',
    'Analyze and update selected books automatically': '自动分析并更新选中的书籍', 'Analyze Selected Books (Review Each)': '分析选中的书籍（逐本审核）',
    'Manually review selected books': '逐本审核选中的书籍', 'Queued {0} books for analysis.': '已加入 {0} 本书的分析队列。',
    'Analyzing filename for book ID: {0}': '正在分析书籍 {0} 的文件名', 'The AI returned an empty response for the filename request.': 'AI 对文件名请求返回了空响应。',
    'The AI job failed.': 'AI 任务失败。', 'Library changed. This analysis result was discarded.': '书库已改变，此分析结果已丢弃。',
    'UI Error': '界面错误', 'Please enter your API key for {0}.': '请输入 {0} 的 API 密钥。',
    'Book ID {0} no longer exists. Skipping.': '书籍 {0} 已不存在，跳过。', 'Unknown AI Provider selected.': '选择了未知的 AI 服务商。',
    'The AI blocked this filename request due to its safety filters.': 'AI 的安全过滤器阻止了该文件名请求。', 'AI Vision Failed': 'AI 分析失败',
    'Metadata was not written safely: {0}': '元数据未安全写入：{0}', 'Failed to fetch models: {0}': '获取模型失败：{0}',
    'The AI took too long to analyze the filename. Please try again.': 'AI 分析文件名耗时过长，请重试。',
    'API Error: {0} server was unavailable after multiple retries.': 'API 错误：{0} 服务器多次重试后仍不可用。',
    'Data Parsing Error: {0}': '数据解析错误：{0}', 'Could not launch review: {0}': '无法打开审核窗口：{0}',
    'Get Google API Key': '获取 Google API 密钥', 'Get OpenAI API Key': '获取 OpenAI API 密钥', 'Get DeepSeek API Key': '获取 DeepSeek API 密钥',
    'Get Anthropic API Key': '获取 Anthropic API 密钥', 'Get OpenRouter API Key': '获取 OpenRouter API 密钥',
    'Network connection failed: {0}': '网络连接失败：{0}', 'An unexpected error occurred: {0}': '发生意外错误：{0}',
    '{0} API Error ({1}): {2}': '{0} API 错误（{1}）：{2}', '{0} API Error (HTTP {1}): {2}': '{0} API 错误（HTTP {1}）：{2}',
    'AI result failed validation: {0}': 'AI 结果校验失败：{0}',
}
def _(text: str) -> str:
    return _ZH_UI.get(text, _CALIBRE_TRANSLATE(text))

class WorkerSignals(QObject):
    review_signal = pyqtSignal(object, object, object)
    error_signal = pyqtSignal(str)  

DEFAULT_PROMPT = (
    "Parse this manga or doujinshi using only the original filename and existing metadata. "
    "No cover image is supplied. Prioritize exact filename evidence over guesses. "
    "Preserve the wording of an existing Chinese title from the filename. "
    "With an explicit source volume number, format title as base title + one space + volume, "
    "and use that same base title without the volume as series. "
    "When there is no Chinese title, translate Japanese, Korean, or English original titles naturally into Simplified Chinese, "
    "and mark it as an AI translation rather than an official title. Separate personal authors, circles and "
    "translation groups. Never mix those values, event codes or edition markers into the title. "
    "Return ONLY a compact JSON object containing title, translated_title, languages, and filename_roles. "
    "Return tags as an empty list. Do not infer publisher, publication dates or identifiers. "
    "A trailing parenthesized number can be a calibre book ID or file collision suffix, not a volume. "
    "If the original filename is missing or truncated, extract the title from existing_title and translate it if it is Japanese, Korean, or English. "
    "If neither input contains a title, leave the title empty and require review."
)


def build_context_prompt(prompt, context):
    """Add only filename, current title, and deterministic filename evidence."""
    title_parsed, title_input_source = select_title_evidence(
        parse_filename(context.get('original_filename', '')), context.get('existing_title', ''),
        context.get('original_filename_source', 'custom_column'))
    hint_keys = ('original_title', 'translated_title', 'creators', 'circle', 'volume', 'chapter',
                 'volume_range', 'chapter_range', 'title_language_hint', 'title_candidate_kind',
                 'author_candidate_kind')
    title_hints = {key: value for key, value in title_parsed.as_dict().items() if key in hint_keys and value}
    source_context = (
        f"\noriginal_filename: {context.get('original_filename', '')}\n"
        f"filename_source: {context.get('original_filename_source', 'custom_column')}\n"
        f"existing_title: {context.get('existing_title', '')}\n"
        f"title_evidence_source: {title_input_source}\n"
        f"title_candidates: {json.dumps(title_hints, ensure_ascii=False)}\n"
    )
    return (
        prompt + "\n\nIMPORTANT COMIC FILENAME CONTEXT:\n"
        "cover_image_supplied: false. Do not claim to have inspected the cover.\n"
        "The following original filename is evidence. Preserve it exactly and never invent a replacement.\n"
        "Classify filename roles yourself; deterministic candidates are fallible hints, especially a first-bracket author guess. "
        "In the SAME metadata JSON object, return filename_roles with title_text (verbatim source title before translation), "
        "author_texts (list of verbatim personal-author quotes), circle_text (verbatim circle or empty), "
        "annotation_texts (list of verbatim annotation quotes), confidence (0 to 1), and uncertain (boolean). "
        "Also return filename_roles.title_confidence (0 to 1) for identifying the source title alone. "
        "Do not reduce title_confidence just because an author/circle is absent or unknown. "
        "Unknown authors must be []; do not invent authors. Overall confidence still covers all assigned roles. "
        "Also return filename_roles.title_language as 'zh', 'ja', 'ko', 'en', or 'unknown' for the quoted source title, "
        "not the translation language. Han/kanji characters without kana do NOT prove a title is Chinese. "
        "Determine the source title's language from its wording and filename context; Japanese titles can "
        "contain only kanji. A translation-group tag does not prove the title itself is already Chinese. "
        "For a Japanese or Korean source title, including an all-kanji Japanese title, return a natural Simplified Chinese "
        "translation in title/translated_title while keeping title_text verbatim. "
        "For an English source title, translate it into natural Simplified Chinese while preserving proper names. "
        "A han_ambiguous hint is provisional source wording, not a confirmed Chinese translation. "
        "Preserve a separately supplied Chinese title when Japanese original text is also present. "
        "If the source language is ambiguous, return title_language='unknown' and uncertain=true. "
        "A title mixing Chinese-looking Han characters and Japanese kana is still Japanese: translate "
        "the entire title into natural Simplified Chinese, including kana phrases. Do not just simplify "
        "kanji or copy the Japanese source into title/translated_title. "
        "Copy each quote exactly from the selected title input, without enclosing metadata brackets. "
        "Use original_filename for filename title evidence; use existing_title only when title_evidence_source is existing_title. "
        "Do not translate or normalize quoted roles; put the Simplified Chinese translation in title/translated_title. "
        "Exclude archive extensions and download/import collision suffixes from title_text. "
        "Separate author, title, circle, translation group, event, and edition by meaning, not just bracket position. "
        "An author must occur in the input; do not invent one or infer it from external knowledge. "
        "Preserve explicit Circle(Author) evidence and clear Chinese title wording. "
        "If roles cannot be distinguished, set uncertain=true; automatic mode will skip the book without a confirmation dialog. "
        "If the filename already contains a clear Chinese title, preserve its wording in translated_title and title. "
        "When the source has an explicit volume marker or terminal title number, format title and translated_title "
        "as the base title followed by exactly one space and the source volume number, for example '直到紫藤花盛开 2'. "
        "Use exactly that base title as series, for example '直到紫藤花盛开', without the volume number. "
        "Local naming rules take precedence: C followed by 2-4 digits is an event code, never a chapter; "
        "Circle(Author) is creator evidence; bare terminal title numbers are volumes. "
        "Keep explicit chapter numbers separate from volumes. Preserve decimal volumes and ranges exactly; "
        "never choose one volume from a range or combine chapter and volume into a decimal. "
        "Translate the base title, preserving source numbering. Separate [Vol. 2] and [Ch.15] groups "
        "may be annotation quotes and must not become authors. "
        "For translated manga return languages as ['zho']. Return tags as an empty list. Leave publisher, "
        "publication dates and identifiers empty. "
        "A calibre_path_fallback is an unreliable directory name whose terminal (number) is a book ID, not a volume. "
        "When the directory fallback is truncated or has only metadata groups, use the cleaned title_candidates "
        "from existing_title. Preserve its Chinese title, or translate its Japanese title into Simplified Chinese. "
        "Only if neither input has a title, leave it empty. Do not return the entire existing filename as the title. "
        "In the common [Author]Title[translation][notes] layout, the unbracketed middle text is the title; "
        "trailing brackets such as [中国翻译] and [禁漫去码] are annotations, never titles. "
        "For other layouts, use semantic role classification to correct bracket-position guesses; "
        "a bracket alone does not prove that its content is an author or a title. "
        "For a standalone work with no explicit volume marker or terminal title number in the source text, "
        "leave series, volume and issue_number empty. Do not copy a standalone title into series. "
        "Do not call an AI translation an official translation. Unknown facts must be empty and review_required must be true. "
        "Return exactly one complete metadata JSON object. Do not echo the response_format setting "
        "or output a separate {'type':'json_object'} object."
        " For efficient output return only title, translated_title, languages, and filename_roles. "
        "Omit redundant original_title, filename copies, explanations, evidence arrays, empty metadata, "
        "series and volume (the plugin derives numbering locally). Keep the JSON compact. "
        "Never append publication volume/issue/date numbers, event numbers, edition codes or file IDs "
        "to a translated work title. For example (COMIC magazine Vol.18) is publication metadata, "
        "not work volume 18; keep such text in annotation_texts only. "
        + source_context
        + ("\nTRANSLATION CORRECTION: Your previous response left the non-Chinese translation missing "
           "or filename-role classification uncertain. Recheck the full input and translate this "
           "verbatim source title fully into Simplified Chinese: "
           + json.dumps(context['translation_repair_source'], ensure_ascii=False)
           + ". Return the full metadata JSON and verbatim filename_roles again. "
           "title/translated_title must contain the Chinese translation, without Japanese kana or Korean Hangul. "
           "Keep the original in original_title and filename_roles.title_text."
           if context.get('translation_repair_source') else '')
    )

class ConfigWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.l = QVBoxLayout()
        self.setLayout(self.l)
        
        # --- 1. Provider Selection ---
        self.label_provider = QLabel(_('AI Provider:'))
        self.l.addWidget(self.label_provider)
        
        self.provider_combo = QComboBox(self)
        self.providers = ['Google Gemini', 'OpenAI', 'DeepSeek', 'Anthropic', 'OpenRouter', 'Local (Ollama/LM Studio)']
        self.provider_combo.addItems(self.providers)
        
        # --- Load saved provider, defaulting to Google ---
        saved_provider = prefs.get('ai_provider', 'Google Gemini')
        self.provider_combo.setCurrentText(saved_provider)
        self.provider_combo.currentIndexChanged.connect(self.toggle_provider_fields)
        self.l.addWidget(self.provider_combo)

        # --- Dynamic Helper Link Label ---
        self.link_label = QLabel()
        self.link_label.setOpenExternalLinks(True)
        self.l.addWidget(self.link_label)
        
        # --- 2. API Key Fields (Dedicated Memory Banks) ---
        self.label_key = QLabel(_('API Key:'))
        self.l.addWidget(self.label_key)
        
        # Google Key (Falls back to the old agnostic key so you don't lose it)
        self.key_google = QLineEdit(self)
        self.key_google.setText(prefs.get('api_key_google', prefs.get('api_key', '')))
        self.l.addWidget(self.key_google)
        
        # OpenAI Key
        self.key_openai = QLineEdit(self)
        self.key_openai.setText(prefs.get('api_key_openai', ''))
        self.l.addWidget(self.key_openai)

        # DeepSeek Key (OpenAI-compatible API)
        self.key_deepseek = QLineEdit(self)
        self.key_deepseek.setText(prefs.get('api_key_deepseek', ''))
        self.l.addWidget(self.key_deepseek)
        
        # Anthropic Key
        self.key_anthropic = QLineEdit(self)
        self.key_anthropic.setText(prefs.get('api_key_anthropic', ''))
        self.l.addWidget(self.key_anthropic)
        
        # OpenRouter Key
        self.key_openrouter = QLineEdit(self)
        self.key_openrouter.setText(prefs.get('api_key_openrouter', ''))
        self.l.addWidget(self.key_openrouter)
        
        # --- 3. Local Base URL Field ---
        self.label_url = QLabel(_('Local Base URL (e.g., http://localhost:11434):'))
        self.l.addWidget(self.label_url)
        self.url_input = QLineEdit(self)
        self.url_input.setText(prefs.get('local_url', 'http://localhost:11434'))
        self.l.addWidget(self.url_input)
        
        # --- 4. Model Selection Area (Dedicated Memory Banks) ---
        self.label_model = QLabel(_('Model Name:'))
        self.l.addWidget(self.label_model)
        self.model_layout = QHBoxLayout()
        
        # Google Model
        self.model_google = QComboBox(self)
        self.model_google.setEditable(True)
        # Fallback to the legacy 'model_name' so you don't lose your current setting
        saved_google = prefs.get('model_google', prefs.get('model_name', 'gemini-2.5-pro'))
        self.model_google.addItem(saved_google)
        self.model_google.setCurrentText(saved_google)
        self.model_layout.addWidget(self.model_google)
        
        # OpenAI Model
        self.model_openai = QComboBox(self)
        self.model_openai.setEditable(True)
        saved_openai = prefs.get('model_openai', 'gpt-4o')
        self.model_openai.addItem(saved_openai)
        self.model_openai.setCurrentText(saved_openai)
        self.model_layout.addWidget(self.model_openai)

        # DeepSeek Model
        self.model_deepseek = QComboBox(self)
        self.model_deepseek.setEditable(True)
        saved_deepseek = prefs.get('model_deepseek', 'deepseek-flash')
        self.model_deepseek.addItem(saved_deepseek)
        self.model_deepseek.setCurrentText(saved_deepseek)
        self.model_layout.addWidget(self.model_deepseek)
        
        # Anthropic Model
        self.model_anthropic = QComboBox(self)
        self.model_anthropic.setEditable(True)
        saved_anthropic = prefs.get('model_anthropic', 'claude-sonnet-4-6')
        self.model_anthropic.addItem(saved_anthropic)
        self.model_anthropic.setCurrentText(saved_anthropic)
        self.model_layout.addWidget(self.model_anthropic)
        
        # OpenRouter Model
        self.model_openrouter = QComboBox(self)
        self.model_openrouter.setEditable(True)
        saved_openrouter = prefs.get('model_openrouter', 'openrouter/auto')
        self.model_openrouter.addItem(saved_openrouter)
        self.model_openrouter.setCurrentText(saved_openrouter)
        self.model_layout.addWidget(self.model_openrouter)
        
        # Local Model
        self.model_local = QComboBox(self)
        self.model_local.setEditable(True)
        saved_local = prefs.get('model_local', 'llava')
        self.model_local.addItem(saved_local)
        self.model_local.setCurrentText(saved_local)
        self.model_layout.addWidget(self.model_local)
        
        self.fetch_button = QPushButton(_("Fetch Available Models"), self)
        self.fetch_button.clicked.connect(self.fetch_models)
        self.model_layout.addWidget(self.fetch_button)
        
        self.l.addLayout(self.model_layout)

        # --- 5. Timeout Configuration ---
        self.label_timeout = QLabel(_('Network Timeout (seconds):'))
        self.l.addWidget(self.label_timeout)
        
        self.timeout_spin = QSpinBox(self)
        self.timeout_spin.setRange(30, 86400) 
        self.timeout_spin.setValue(int(prefs.get('timeout', 300)))
        self.l.addWidget(self.timeout_spin)
        self.deepseek_thinking = QCheckBox(_('DeepSeek: enable thinking (slower)'), self)
        self.deepseek_thinking.setChecked(bool(prefs.get('deepseek_thinking', False)))
        self.l.addWidget(self.deepseek_thinking)
        self.auto_apply_on_click = QCheckBox(_('Auto apply when clicking the plugin'), self)
        self.auto_apply_on_click.setChecked(bool(prefs.get('auto_apply_on_click', False)))
        self.l.addWidget(self.auto_apply_on_click)


        # --- 6. Prompt Tuning Area (Dedicated Memory Banks) ---
        self.prompt_layout = QHBoxLayout()
        self.label_prompt = QLabel(_('System Prompt (Advanced):'))
        
        self.reset_prompt_btn = QPushButton(_("Restore Default"), self)
        self.reset_prompt_btn.clicked.connect(self.restore_default_prompt)
        
        self.prompt_layout.addWidget(self.label_prompt)
        self.prompt_layout.addStretch()
        self.prompt_layout.addWidget(self.reset_prompt_btn)
        self.l.addLayout(self.prompt_layout)
        
        # Google Prompt
        self.prompt_google = QTextEdit(self)
        self.prompt_google.setAcceptRichText(False)
        self.prompt_google.setMinimumHeight(150)
        self.prompt_google.setPlainText(prefs.get('prompt_google', prefs.get('custom_prompt', DEFAULT_PROMPT)))
        self.l.addWidget(self.prompt_google)
        
        # OpenAI Prompt
        self.prompt_openai = QTextEdit(self)
        self.prompt_openai.setAcceptRichText(False)
        self.prompt_openai.setMinimumHeight(150)
        self.prompt_openai.setPlainText(prefs.get('prompt_openai', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_openai)

        self.prompt_deepseek = QTextEdit(self)
        self.prompt_deepseek.setAcceptRichText(False)
        self.prompt_deepseek.setMinimumHeight(150)
        self.prompt_deepseek.setPlainText(prefs.get('prompt_deepseek', prefs.get('prompt_openai', DEFAULT_PROMPT)))
        self.l.addWidget(self.prompt_deepseek)
        
        # Anthropic Prompt
        self.prompt_anthropic = QTextEdit(self)
        self.prompt_anthropic.setAcceptRichText(False)
        self.prompt_anthropic.setMinimumHeight(150)
        self.prompt_anthropic.setPlainText(prefs.get('prompt_anthropic', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_anthropic)
        
        # OpenRouter Prompt
        self.prompt_openrouter = QTextEdit(self)
        self.prompt_openrouter.setAcceptRichText(False)
        self.prompt_openrouter.setMinimumHeight(150)
        self.prompt_openrouter.setPlainText(prefs.get('prompt_openrouter', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_openrouter)
        
        # Local Prompt
        self.prompt_local = QTextEdit(self)
        self.prompt_local.setAcceptRichText(False)
        self.prompt_local.setMinimumHeight(150)
        self.prompt_local.setPlainText(prefs.get('prompt_local', DEFAULT_PROMPT))
        self.l.addWidget(self.prompt_local)

        # --- INITIALIZATION ---
        # Run the toggle function once right now so the UI initializes in the correct state
        self.toggle_provider_fields()

    def toggle_provider_fields(self):
        """Dynamically shows/hides inputs based on the selected provider."""
        provider = self.provider_combo.currentText()
        
        # Hide all key inputs first to reset the board
        self.key_google.setVisible(False)
        self.key_openai.setVisible(False)
        self.key_deepseek.setVisible(False)
        self.key_anthropic.setVisible(False)
        self.key_openrouter.setVisible(False)
        # Hide all model combos first
        self.model_google.setVisible(False)
        self.model_openai.setVisible(False)
        self.model_deepseek.setVisible(False)
        self.model_anthropic.setVisible(False)
        self.model_openrouter.setVisible(False)
        self.model_local.setVisible(False)        
        # Hide all prompt editing areas first
        self.prompt_google.setVisible(False)
        self.prompt_openai.setVisible(False)
        self.prompt_deepseek.setVisible(False)
        self.prompt_anthropic.setVisible(False)
        self.prompt_openrouter.setVisible(False)
        self.prompt_local.setVisible(False)
        self.deepseek_thinking.setVisible(provider == 'DeepSeek')
        
        if provider == 'Local (Ollama/LM Studio)':
            self.link_label.setText(_("Get Local Tools:") + ' <a href="https://ollama.com/download">Ollama</a> | <a href="https://lmstudio.ai/">LM Studio</a>')
            self.label_key.setVisible(False)
            self.label_url.setVisible(True)
            self.url_input.setVisible(True)
            self.model_local.setVisible(True)
            self.prompt_local.setVisible(True)
        else:
            self.label_key.setVisible(True)
            self.label_url.setVisible(False)
            self.url_input.setVisible(False)
            
            if provider == 'Google Gemini':
                self.link_label.setText('<a href="https://aistudio.google.com/app/apikey">' + _("Get Google API Key") + '</a>')
                self.key_google.setVisible(True)
                self.model_google.setVisible(True)
                self.prompt_google.setVisible(True)
            elif provider == 'OpenAI':
                self.link_label.setText('<a href="https://platform.openai.com/api-keys">' + _("Get OpenAI API Key") + '</a>')
                self.key_openai.setVisible(True)
                self.model_openai.setVisible(True)
                self.prompt_openai.setVisible(True)
            elif provider == 'DeepSeek':
                self.link_label.setText('<a href="https://platform.deepseek.com/api_keys">' + _("Get DeepSeek API Key") + '</a>')
                self.key_deepseek.setVisible(True)
                self.model_deepseek.setVisible(True)
                self.prompt_deepseek.setVisible(True)
            elif provider == 'Anthropic':
                self.link_label.setText('<a href="https://console.anthropic.com/settings/keys">' + _("Get Anthropic API Key") + '</a>')
                self.key_anthropic.setVisible(True)
                self.model_anthropic.setVisible(True)
                self.prompt_anthropic.setVisible(True)
            elif provider == 'OpenRouter':
                self.link_label.setText('<a href="https://openrouter.ai/settings/keys">' + _("Get OpenRouter API Key") + '</a>')
                self.key_openrouter.setVisible(True)
                self.model_openrouter.setVisible(True)
                self.prompt_openrouter.setVisible(True)

    def fetch_models(self):
        provider = self.provider_combo.currentText()
        local_url = self.url_input.text().strip().rstrip('/')
        
        # --- 1. Identify the Active Key and Dropdown ---
        if provider == 'Google Gemini':
            api_key = self.key_google.text().strip()
            active_combo = self.model_google
        elif provider == 'OpenAI':
            api_key = self.key_openai.text().strip()
            active_combo = self.model_openai
        elif provider == 'DeepSeek':
            api_key = self.key_deepseek.text().strip()
            active_combo = self.model_deepseek
        elif provider == 'Anthropic':
            api_key = self.key_anthropic.text().strip()
            active_combo = self.model_anthropic
        elif provider == 'OpenRouter':
            api_key = self.key_openrouter.text().strip()
            active_combo = self.model_openrouter
        else:
            api_key = "" 
            active_combo = self.model_local
            
        # --- 2. Validation ---
        if provider not in ['Local (Ollama/LM Studio)', 'OpenRouter'] and not api_key:
            QMessageBox.warning(self, _("Missing Key"), _("Please enter your API key for {0}.").format(provider))
            return
            
        if provider == 'Local (Ollama/LM Studio)' and not local_url:
            QMessageBox.warning(self, _("Missing URL"), _("Please enter your local server's Base URL."))
            return
            
        # Clear ONLY the currently visible dropdown
        active_combo.clear()
        
        # --- 3. API Routing & Populating ---
        try:
            if provider == 'Google Gemini':
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                exclusion_list = ['gemini-2.0-flash', 'gemini-2.0-pro', 'gemini-1.0-pro']
                for model in data.get('models', []):
                    if 'generateContent' in model.get('supportedGenerationMethods', []):
                        model_id = model.get('name', '').replace('models/', '')
                        if model_id not in exclusion_list:
                            active_combo.addItem(model_id)
                            
            elif provider in ['OpenAI', 'DeepSeek']:
                url = "https://api.deepseek.com/v1/models" if provider == 'DeepSeek' else "https://api.openai.com/v1/models"
                req = urllib.request.Request(url, headers={'Authorization': f'Bearer {api_key}'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                for model in data.get('data', []):
                    model_id = model.get('id', '')
                    if provider == 'DeepSeek' or 'gpt-4o' in model_id or 'gpt-4-turbo' in model_id:
                        active_combo.addItem(model_id)
                        
            elif provider == 'Anthropic':
                url = "https://api.anthropic.com/v1/models"
                # Anthropic requires their specific version header alongside the key
                req = urllib.request.Request(url, headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                })
                
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                for model in data.get('data', []):
                    model_id = model.get('id', '')
                    # All current Claude models (from Claude 3 through the newest Claude 4 and 5 series) 
                    # support multimodal vision natively.
                    if 'claude' in model_id:
                        active_combo.addItem(model_id)
                
            elif provider == 'OpenRouter':
                url = "https://openrouter.ai/api/v1/models"
                req = urllib.request.Request(url) 
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                for model in data.get('data', []):
                    model_id = model.get('id', '')
                    
                    # 1. Safely extract the architectural modality string
                    architecture = model.get('architecture', {})
                    # Default to an empty string if it's missing, then make it lowercase
                    modality = architecture.get('modality', '').lower() if architecture else ''
                    
                    # 2. Check if it officially accepts images, OR fallback to our string checks
                    if 'image' in modality or 'vision' in model_id or 'llava' in model_id or 'claude' in model_id:
                        active_combo.addItem(model_id)
                        
            elif provider == 'Local (Ollama/LM Studio)':
                url = f"{local_url}/v1/models"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    
                for model in data.get('data', []):
                    active_combo.addItem(model.get('id', ''))
                    
            QMessageBox.information(self, _("Success"), _("Models refreshed successfully!"))
            
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Failed to fetch models: {0}").format(str(e)))

    def restore_default_prompt(self):
        reply = QMessageBox.question(self, _('Restore Default'), 
                                     _('Are you sure you want to overwrite your custom prompt with the default instructions?'),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            provider = self.provider_combo.currentText()
            if provider == 'Google Gemini':
                self.prompt_google.setPlainText(DEFAULT_PROMPT)
            elif provider == 'OpenAI':
                self.prompt_openai.setPlainText(DEFAULT_PROMPT)
            elif provider == 'DeepSeek':
                self.prompt_deepseek.setPlainText(DEFAULT_PROMPT)
            elif provider == 'Anthropic':
                self.prompt_anthropic.setPlainText(DEFAULT_PROMPT)
            elif provider == 'OpenRouter':
                self.prompt_openrouter.setPlainText(DEFAULT_PROMPT)
            elif provider == 'Local (Ollama/LM Studio)':
                self.prompt_local.setPlainText(DEFAULT_PROMPT)

    def save_settings(self):
        # 1. Save the active provider
        prefs['ai_provider'] = self.provider_combo.currentText()
        
        # 2. Save API Keys & URLs
        prefs['api_key_google'] = self.key_google.text().strip()
        prefs['api_key_openai'] = self.key_openai.text().strip()
        prefs['api_key_deepseek'] = self.key_deepseek.text().strip()
        prefs['api_key_anthropic'] = self.key_anthropic.text().strip()
        prefs['api_key_openrouter'] = self.key_openrouter.text().strip()
        prefs['local_url'] = self.url_input.text().strip()
        
        # 3. Save Models
        prefs['model_google'] = self.model_google.currentText().strip()
        prefs['model_openai'] = self.model_openai.currentText().strip()
        prefs['model_deepseek'] = self.model_deepseek.currentText().strip()
        prefs['model_anthropic'] = self.model_anthropic.currentText().strip()
        prefs['model_openrouter'] = self.model_openrouter.currentText().strip()
        prefs['model_local'] = self.model_local.currentText().strip()
        
        # 4. Save Custom Prompts
        prefs['prompt_google'] = self.prompt_google.toPlainText().strip()
        prefs['prompt_openai'] = self.prompt_openai.toPlainText().strip()
        prefs['prompt_deepseek'] = self.prompt_deepseek.toPlainText().strip()
        prefs['prompt_anthropic'] = self.prompt_anthropic.toPlainText().strip()
        prefs['prompt_openrouter'] = self.prompt_openrouter.toPlainText().strip()
        prefs['prompt_local'] = self.prompt_local.toPlainText().strip()
        
        # 5. Save General Settings
        prefs['timeout'] = self.timeout_spin.value()
        prefs['deepseek_thinking'] = self.deepseek_thinking.isChecked()
        prefs['auto_apply_on_click'] = self.auto_apply_on_click.isChecked()

class AIVisionAction(InterfaceAction):
    name = 'MetaManga'
    action_spec = ('漫元', 'images/icon.png', _('Extract metadata from original filename'), 'Ctrl+Shift+I')

    def genesis(self):
        self.batch_queue = []
        self.queue_active = False
        self.queue_db = None
        self.queue_library_id = None
        self.pending_context = {}
        self.library_value_cache = {}
        self.review_each = False
        self.active_book_id = None
        self.batch_results = []
        # -----------------------------------------

        self.signals = WorkerSignals()
        self.signals.review_signal.connect(self._show_review_dialog, type=Qt.ConnectionType.QueuedConnection)
        self.signals.error_signal.connect(self._show_error_dialog, type=Qt.ConnectionType.QueuedConnection)

        self.qaction.triggered.connect(self.identify_book)
        self.menu = QMenu(self.gui)

        self.report_action = self.create_action(
            spec=(_('Last Run Results'), None, _('Show written and skipped books from the last run'), None),
            attr='report_action'
        )
        self.report_action.triggered.connect(self.show_last_results)
        self.menu.addAction(self.report_action)

        self.menu.addSeparator()

        self.config_action = self.create_action(
            spec=(_('Configure AI Vision'), 'images/config.png', _('Settings for AI Vision Metadata'), None),
            attr='config_action'
        )
        self.config_action.triggered.connect(self.show_configuration)
        self.menu.addAction(self.config_action)

        self.qaction.setMenu(self.menu)

        try:
            resources = self.load_resources(['images/icon.png', 'images/config.png'])
            icon_data = resources.get('images/icon.png')
            if icon_data:
                pixmap = QPixmap()
                pixmap.loadFromData(icon_data)
                main_icon = QIcon(pixmap)
                self.qaction.setIcon(main_icon)

            config_data = resources.get('images/config.png')
            if config_data:
                config_pixmap = QPixmap()
                config_pixmap.loadFromData(config_data)
                self.config_action.setIcon(QIcon(config_pixmap))
        except Exception:
            pass

    def start_blind_batch(self):
        # Compatibility for previously bound shortcuts.
        self.identify_book()

    def identify_book(self):
        # Keep legacy installations automatic until the new preference is saved.
        # New installations expose the option unchecked in ConfigWidget.
        auto_apply = prefs.get('auto_apply_on_click', True)
        self.start_analysis(review_each=not bool(auto_apply))

    def identify_books_with_review(self):
        self.start_analysis(review_each=True)

    def start_analysis(self, review_each=False):
        if self.queue_active:
            self._status_message(_("Analysis is already in progress."))
            return
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            self._status_message(_('Please select at least one book.'))
            return

        self.review_each = review_each
        self.batch_results = []
        self.pending_context.clear()
        self.batch_queue = [self.gui.library_view.model().id(row) for row in rows]
        self.queue_db = self.gui.current_db.new_api
        self.queue_library_id = self.queue_db.library_id
        self.library_value_cache = {}
        self.queue_active = True
        self._status_message(_("Queued {0} books for analysis.").format(len(self.batch_queue)))
        self.process_next_in_queue()

    def _status_message(self, message):
        self.gui.status_bar.showMessage(message, 15000)

    def _record_result(self, book_id, status, reason='', metadata=None):
        metadata = metadata or {}
        self.batch_results.append({'book_id': book_id, 'status': status, 'reason': reason,
                                   'seconds': metadata.get('api_duration', ''),
                                   'diagnostics': {key: metadata[key] for key in (
                                       'title', 'original_title', 'translated_title', 'provider_title',
                                       'provider_translated_title', 'title_language_hint', 'translation_status',
                                       'filename_role_status', 'filename_roles', 'title_only', 'warnings') if key in metadata},
                                   'request_metrics': metadata.get('request_metrics', {})})

    def _result_summary(self):
        written = sum(result['status'] == 'written' for result in self.batch_results)
        return _("Analysis finished: {0} written, {1} skipped.").format(written, len(self.batch_results) - written)

    def show_last_results(self):
        report = QMessageBox(self.gui)
        report.setWindowTitle(_('Last Run Results'))
        report.setText(self._result_summary())
        report.setDetailedText('\n'.join(
            "Book {book_id}: {status} {reason}; {seconds}s; {request_metrics}".format(**result)
            + '\n' + json.dumps(result.get('diagnostics', {}), ensure_ascii=False, indent=2)
            for result in self.batch_results
        ))
        report.exec()

    def show_configuration(self):
        # This native Calibre command instantly summons the ConfigWidget
        self.interface_action_base_plugin.do_user_config(self.gui)

    def process_next_in_queue(self):
        """Pops the next book from the queue and starts the AI job."""
        if not hasattr(self, 'batch_queue') or not self.batch_queue:
            self.queue_active = False
            self.pending_context.clear()
            self.active_book_id = None
            self._status_message(self._result_summary())
            return

        db = self.gui.current_db.new_api
        if db is not self.queue_db or db.library_id != self.queue_library_id:
            for remaining_id in self.batch_queue:
                self._record_result(remaining_id, 'skipped', 'library_changed')
            self.batch_queue.clear()
            self.queue_active = False
            self.pending_context.clear()
            self.signals.error_signal.emit(_("Library changed. The remaining analysis queue was cancelled."))
            return

        # Pop the first ID off the front of the list
        book_id = self.batch_queue.pop(0)
        self.active_book_id = book_id
        library_id = getattr(db, 'library_id', None)

        if not db.has_id(book_id):
            self._record_result(book_id, 'skipped', 'book_missing')
            self.signals.error_signal.emit(_("Book ID {0} no longer exists. Skipping.").format(book_id))
            QTimer.singleShot(0, self.process_next_in_queue)
            return

        current_mi = db.get_metadata(book_id)
        source = read_filename_source(db, book_id)
        comments_context = capture_filename_comments(db, book_id, source, current_mi)
        if (source['original_filename_source'] == 'calibre_path_fallback'
                and comments_context['source'] == 'analysis_history'):
            # The prior input can also repair a title already misidentified by
            # an older release. Do not let the new/wrong title override it.
            source = dict(source, original_filename=comments_context['text'],
                          original_filename_source='analysis_history')
        original_filename = source['original_filename']
        parsed = parse_filename(original_filename)
        context = {
            'library_id': library_id,
            'snapshot': snapshot_metadata(db, book_id),
            'original_filename': original_filename,
            **source,
            'parsed_filename': parsed.as_dict(),
            'existing_title': current_mi.title,
            'comments_context': comments_context,
            'send_cover_image': False,
        }
        self.pending_context[book_id] = context

        # Fetch the cover path
        rel_path = db.field_for('path', book_id)
        if rel_path:
            lib_path = self.gui.current_db.library_path
            cover_path = os.path.join(lib_path, rel_path.replace('/', os.sep), 'cover.jpg')
        else:
            cover_path = None

        # Launch the background thread
        from calibre.gui2.threaded_jobs import ThreadedJob
        job = ThreadedJob(
            'identifying_book', 
            _('Analyzing filename for book ID: {0}').format(book_id),
            self.run_api_request, 
            (book_id, cover_path, "", context), # Passing "" since api_key_ignored is no longer used
            {}, 
            Dispatcher(self.job_finished)
        )
        self.gui.job_manager.run_threaded_job(job)

    def run_api_request(self, book_id, cover_path, api_key_ignored, context=None, **kwargs):
        import time
        start_time = time.time() # --- Start the clock ---

        provider = prefs.get('ai_provider', 'Google Gemini')
        local_url = prefs.get('local_url', 'http://localhost:11434').rstrip('/')
        
        # --- Master Variable Router ---
        if provider == 'Google Gemini':
            api_key = prefs.get('api_key_google', prefs.get('api_key', ''))
            model_name = prefs.get('model_google', prefs.get('model_name', 'gemini-2.5-pro'))
            prompt = prefs.get('prompt_google', DEFAULT_PROMPT)
        elif provider == 'OpenAI':
            api_key = prefs.get('api_key_openai', '')
            model_name = prefs.get('model_openai', 'gpt-4o')
            prompt = prefs.get('prompt_openai', DEFAULT_PROMPT)
        elif provider == 'DeepSeek':
            api_key = prefs.get('api_key_deepseek', '')
            model_name = prefs.get('model_deepseek', 'deepseek-flash')
            prompt = prefs.get('prompt_deepseek', prefs.get('prompt_openai', DEFAULT_PROMPT))
        elif provider == 'Anthropic':
            api_key = prefs.get('api_key_anthropic', '')
            model_name = prefs.get('model_anthropic', 'claude-sonnet-4-6')
            prompt = prefs.get('prompt_anthropic', DEFAULT_PROMPT)
        elif provider == 'OpenRouter':
            api_key = prefs.get('api_key_openrouter', '')
            model_name = prefs.get('model_openrouter', 'openrouter/auto')
            prompt = prefs.get('prompt_openrouter', DEFAULT_PROMPT)
        else:
            api_key = ""
            model_name = prefs.get('model_local', 'llava')
            prompt = prefs.get('prompt_local', DEFAULT_PROMPT)
            
        if not prompt:
            prompt = DEFAULT_PROMPT
        if context:
            prompt = build_context_prompt(prompt, context)
        # -----------------------------------

        # --- DYNAMIC ROUTING & PAYLOAD BUILDER ---
        headers = {'Content-Type': 'application/json'}

        if provider == 'Google Gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            parts = [{"text": prompt}]
            payload = {
                "contents": [{
                    "parts": parts
                }]
            }

        elif provider in ['OpenAI', 'DeepSeek', 'OpenRouter', 'Local (Ollama/LM Studio)']:
            if provider in ['OpenAI', 'DeepSeek']:
                url = "https://api.deepseek.com/v1/chat/completions" if provider == 'DeepSeek' else "https://api.openai.com/v1/chat/completions"
                headers['Authorization'] = f'Bearer {api_key}'
            elif provider == 'OpenRouter':
                url = "https://openrouter.ai/api/v1/chat/completions" # Fixed endpoint
                headers['Authorization'] = f'Bearer {api_key}'
                headers['HTTP-Referer'] = "https://www.mobileread.com/forums/showthread.php?t=372744"
                headers['X-Title'] = "Calibre 漫元 MetaManga Plugin"
            else:
                url = f"{local_url}/v1/chat/completions"

            message_content = [{"type": "text", "text": prompt}]
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                # This explicitly tells OpenAI/OpenRouter/Ollama to format their output as JSON
                "response_format": {"type": "json_object"} 
            }
            if provider == 'DeepSeek':
                thinking_enabled = bool(prefs.get('deepseek_thinking', False))
                payload['thinking'] = {'type': 'enabled' if thinking_enabled else 'disabled'}
                payload['max_tokens'] = 8192 if thinking_enabled else 2048

        elif provider == 'Anthropic':
            url = "https://api.anthropic.com/v1/messages"
            headers['x-api-key'] = api_key
            headers['anthropic-version'] = '2023-06-01'

            anthropic_content = [{"type": "text", "text": prompt}]
            payload = {
                "model": model_name,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": anthropic_content
                    }
                ]
            }
        else:
             return {"error_msg": _("Unknown AI Provider selected.")}

        import urllib.error
        import time
        
        # Fetch the user-defined timeout, defaulting to 300 if not found
        timeout_val = int(prefs.get('timeout', 300))
        
        try:
            data = json.dumps(payload).encode('utf-8')
            # --- Pass the dynamic 'headers' variable instead of a hardcoded dictionary ---
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            # -----------------------------------------------------------------------------

            max_retries = 3
            base_delay = 2
            res_json = None
            request_timings = []
            retry_wait_seconds = 0
            response_body = b''

            for attempt in range(max_retries):
                attempt_start = time.time()
                try:
                    # Pass the dynamic timeout variable to the request
                    with urllib.request.urlopen(req, timeout=timeout_val) as response:
                        headers_received = time.time()
                        response_body = response.read()
                        body_received = time.time()
                        res_json = json.loads(response_body.decode('utf-8'))
                    request_timings.append({'attempt': attempt + 1,
                                            'headers_seconds': round(headers_received - attempt_start, 3),
                                            'body_seconds': round(body_received - headers_received, 3)})
                    
                    # If the call succeeds, break out of the retry loop immediately!
                    break 

                except urllib.error.HTTPError as http_err:
                    request_timings.append({'attempt': attempt + 1, 'http_status': http_err.code,
                                            'request_seconds': round(time.time() - attempt_start, 3)})
                    # Check specifically for Google 503s or generic 429 Rate Limits
                    if http_err.code in [429, 503] and attempt < max_retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
                        retry_wait_seconds += sleep_time
                        time.sleep(sleep_time)
                        continue # Loop around and try the request again
                    else:
                        # Out of retries, OR it's a non-retriable error (like 401 Unauthorized)
                        error_body = http_err.read().decode('utf-8')
                        try:
                            # Attempt to parse the JSON error response
                            error_json = json.loads(error_body)
                            
                            # Google, OpenAI, and Anthropic all conveniently use this exact nested structure!
                            clean_msg = error_json.get('error', {}).get('message', error_body)
                            
                            # --- Dynamically inject the provider name ---
                            return {"error_msg": _("{0} API Error ({1}): {2}").format(provider, http_err.code, clean_msg)}
                            # --------------------------------------------
                            
                        except json.JSONDecodeError:
                            # Fallback just in case the server sends a plain HTML error page
                            return {"error_msg": _("{0} API Error (HTTP {1}): {2}").format(provider, http_err.code, error_body)}

                except TimeoutError:
                    return {"error_msg": _("The AI took too long to analyze the filename. Please try again.")}
                except urllib.error.URLError as url_err:
                    return {"error_msg": _("Network connection failed: {0}").format(url_err.reason)}
                except Exception as e:
                    return {"error_msg": _("An unexpected error occurred: {0}").format(str(e))}

            # Failsafe: if the loop finishes and we somehow don't have res_json
            if not res_json:
                return {"error_msg": _("API Error: {0} server was unavailable after multiple retries.").format(provider)}
            
            # --- UNIFIED RESPONSE PARSER ---
            raw_text = ""
            
            if provider == 'Google Gemini':
                candidate = res_json.get('candidates', [{}])[0]
                if candidate.get('finishReason') == 'SAFETY':
                    return {"error_msg": _("The AI blocked this filename request due to its safety filters.")}
                parts = candidate.get('content', {}).get('parts', [])
                if parts:
                    raw_text = parts[0].get('text', '')

            elif provider in ['OpenAI', 'DeepSeek', 'OpenRouter', 'Local (Ollama/LM Studio)']:
                choices = res_json.get('choices', [])
                if choices:
                    raw_text = choices[0].get('message', {}).get('content', '')

            elif provider == 'Anthropic':
                content_blocks = res_json.get('content', [])
                if content_blocks:
                    raw_text = content_blocks[0].get('text', '')

            if not raw_text:
                return {"error_msg": _("The AI returned an empty response for the filename request.")}
                
            try:
                metadata = extract_metadata_json(raw_text)
            except ValueError as json_error:
                return {"error_msg": _("Data Parsing Error: {0}\nRaw Output: {1}...").format(str(json_error), raw_text[:150])}

            try:
                metadata = normalize_result(
                    metadata,
                    (context or {}).get('original_filename', ''),
                    parse_filename((context or {}).get('original_filename', '')),
                    allowed_tags=set((context or {}).get('allowed_tags', []) or []),
                    existing_title=(context or {}).get('existing_title', ''),
                    filename_source=(context or {}).get('original_filename_source', 'custom_column'),
                    comments_context=(context or {}).get('comments_context'),
                )
            except (TypeError, ValueError) as schema_error:
                return {"error_msg": _("AI result failed validation: {0}").format(schema_error)}

            # Inject dynamic provider, model, and duration
            elapsed = time.time() - start_time
            metadata['ai_provider'] = provider
            metadata['ai_model_used'] = model_name
            metadata['api_duration'] = round(elapsed, 1)
            usage = res_json.get('usage', {}) or {}
            metadata['request_metrics'] = {
                'request_attempts': attempt + 1, 'retry_wait_seconds': retry_wait_seconds,
                'attempt_timings': request_timings, 'response_characters': len(raw_text),
                'response_bytes': len(response_body),
                'output_tokens': usage.get('completion_tokens', usage.get('output_tokens',
                                    (res_json.get('usageMetadata', {}) or {}).get('candidatesTokenCount'))),
                'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                'deepseek_thinking': payload.get('thinking', {}).get('type') if provider == 'DeepSeek' else None,
            }
            if ((metadata.get('translation_status') == 'needs_translation'
                 or (metadata.get('title_language_hint') in {'ja', 'ko', 'en'}
                     and metadata.get('filename_role_status') == 'uncertain'))
                    and metadata.get('filename_role_status') != 'invalid'
                    and not (context or {}).get('translation_repair_source')):
                repair_context = dict(context or {}, translation_repair_source=(
                    metadata.get('filename_roles', {}).get('title_text') or metadata['original_title']))
                repaired = AIVisionAction.run_api_request(self, book_id, cover_path, api_key_ignored, repair_context)
                metadata['request_metrics']['translation_repair_attempts'] = 1
                if isinstance(repaired, tuple):
                    repaired_metadata = repaired[1]
                    previous = metadata['request_metrics']
                    metrics = repaired_metadata['request_metrics']
                    for key in ('request_attempts', 'retry_wait_seconds', 'response_characters', 'response_bytes'):
                        metrics[key] = metrics.get(key, 0) + previous.get(key, 0)
                    if metrics.get('output_tokens') is not None and previous.get('output_tokens') is not None:
                        metrics['output_tokens'] += previous['output_tokens']
                    else:
                        metrics['output_tokens'] = None
                    if metrics.get('reasoning_tokens') is not None and previous.get('reasoning_tokens') is not None:
                        metrics['reasoning_tokens'] += previous['reasoning_tokens']
                    else:
                        metrics['reasoning_tokens'] = None
                    metrics['attempt_timings'] = previous['attempt_timings'] + metrics['attempt_timings']
                    metrics['translation_repair_attempts'] = 1
                    repaired_metadata['api_duration'] = round(time.time() - start_time, 1)
                    return (book_id, repaired_metadata, cover_path, context)
                metadata['warnings'].append('Translation correction failed: ' + str(repaired.get('error_msg', 'unknown error')))
                metadata['api_duration'] = round(time.time() - start_time, 1)

            # --- ROMAN NUMERAL CONVERTER ---
            import re
            def convert_roman_to_arabic(val):
                if not val or not isinstance(val, str): return val
                val = val.strip().upper()
                # Check if the string is strictly a valid Roman numeral
                if not re.match(r'^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$', val) or val == '':
                    return val 
                
                roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
                res = 0
                for i in range(len(val)):
                    if i > 0 and roman_map[val[i]] > roman_map[val[i - 1]]:
                        res += roman_map[val[i]] - 2 * roman_map[val[i - 1]]
                    else:
                        res += roman_map[val[i]]
                return str(res)
                
            # Safely apply the converter to both fields
            if 'volume' in metadata:
                metadata['volume'] = convert_roman_to_arabic(str(metadata['volume']))
            if 'issue_number' in metadata:
                metadata['issue_number'] = convert_roman_to_arabic(str(metadata['issue_number']))
            # -------------------------------
            
            # --- Return the cover_path along with the ID and metadata ---
            return (book_id, metadata, cover_path, context)
            # ------------------------------------------------------------

        except Exception as e:
            return {"error_msg": _("Data Parsing Error: {0}").format(str(e))}

    def job_finished(self, job):
        if job.failed:
            reason = str(getattr(job, 'exception', '') or _('The AI job failed.'))
            self._record_result(self.active_book_id, 'skipped', reason)
            if self.review_each:
                self.gui.job_exception(job, dialog_title=_("AI Vision Failed"))
            else:
                self._show_error_dialog(reason)
            self.pending_context.pop(self.active_book_id, None)
            self.process_next_in_queue()
            return

        result = job.result

        if isinstance(result, dict) and 'error_msg' in result:
            self._record_result(self.active_book_id, 'skipped', result['error_msg'])
            self.signals.error_signal.emit(result["error_msg"])
            self.pending_context.pop(self.active_book_id, None)
            self.process_next_in_queue()
            return
        try:
            book_id, metadata, cover_path, context = job.result
            self.pending_context[book_id] = context or self.pending_context.get(book_id, {})
            if self.review_each:
                self.signals.review_signal.emit(book_id, metadata, cover_path)
                return
            approved_data = prepare_automatic_update(metadata)
            if approved_data:
                self.apply_metadata(book_id, approved_data)
            else:
                reason = ('filename_roles_' + metadata['filename_role_status']
                          if metadata.get('filename_role_status') in {'invalid', 'uncertain'} else
                          'Japanese title was not translated' if metadata.get('translation_status') == 'needs_translation'
                          else 'no_supported_title')
                self._record_result(book_id, 'skipped', reason, metadata)
        except Exception as error:
            self._record_result(self.active_book_id, 'skipped', str(error))
            self.signals.error_signal.emit(str(error))
        self.pending_context.pop(self.active_book_id, None)
        self.process_next_in_queue()

    def _show_review_dialog(self, book_id, metadata, cover_path):
        try:
            if self.gui.current_db.new_api is not self.queue_db or self.gui.current_db.new_api.library_id != self.queue_library_id:
                self._record_result(book_id, 'skipped', 'library_changed', metadata)
                self.batch_queue.clear()
                self.signals.error_signal.emit(_("Library changed. This analysis result was discarded."))
                return
            from calibre_plugins.ai_vision_metadata.ui import MetadataReviewDialog
            from calibre.gui2 import error_dialog

            # A review also edits the current calibre record. Keep AI suggestions
            # when present and fill only missing suggestions from existing fields.
            current_mi = self.queue_db.get_metadata(book_id)
            metadata = dict(metadata or {})
            existing_values = {
                'title': getattr(current_mi, 'title', '') or '',
                'creators': list(getattr(current_mi, 'authors', None) or []),
                'series': getattr(current_mi, 'series', '') or '',
                'tags': list(getattr(current_mi, 'tags', None) or []),
                'languages': list(getattr(current_mi, 'languages', None) or []),
                'publisher': getattr(current_mi, 'publisher', '') or '',
                'comments': getattr(current_mi, 'comments', '') or '',
                'ids': ', '.join(f'{k}:{v}' for k, v in (getattr(current_mi, 'identifiers', None) or {}).items()),
            }
            series_index = getattr(current_mi, 'series_index', None)
            if series_index not in (None, ''):
                existing_values['volume'] = str(series_index).rstrip('0').rstrip('.') if isinstance(series_index, float) else str(series_index)
            pubdate = getattr(current_mi, 'pubdate', None)
            pubdate_text = pubdate.strftime('%Y-%m-%d') if hasattr(pubdate, 'strftime') else str(pubdate or '')[:10]
            if pubdate_text and not pubdate_text.startswith(('0001-', '0101-')):
                existing_values['existing_pubdate'] = pubdate_text
            for key, value in existing_values.items():
                if not metadata.get(key) and value:
                    metadata[key] = value
            metadata['existing_metadata_mode'] = True
            metadata['comments_write_allowed'] = True
            def library_values(field):
                cache_key = (self.queue_library_id, field)
                if cache_key in self.library_value_cache:
                    return list(self.library_value_cache[cache_key])
                values = set()
                try:
                    raw_values = self.queue_db.all_field_for(field)
                    values.update(str(value).strip() for value in (raw_values or []) if str(value).strip())
                except (AttributeError, TypeError, ValueError):
                    pass
                try:
                    if not values:
                        categories = self.queue_db.get_categories()
                        category = (categories or {}).get(field, (categories or {}).get('#' + field, []))
                        for item in category:
                            value = getattr(item, 'name', item)
                            if isinstance(value, (tuple, list)):
                                value = value[0] if value else ''
                            if str(value).strip():
                                values.add(str(value).strip())
                except (AttributeError, TypeError, ValueError):
                    pass
                # Some Calibre releases expose neither helper for the new API.
                # Scan native metadata as a final, version-independent fallback.
                try:
                    for candidate_id in self.queue_db.all_book_ids():
                        current = self.queue_db.get_metadata(candidate_id)
                        for value in (getattr(current, field, None) or []):
                            if str(value).strip():
                                values.add(str(value).strip())
                except (AttributeError, TypeError, ValueError):
                    pass
                result = sorted(values, key=str.casefold)
                self.library_value_cache[cache_key] = result
                return list(result)
            metadata['tag_options'] = library_values('tags')
            metadata['language_options'] = library_values('languages')
            
            # Pass the cover_path into the Dialog
            d = MetadataReviewDialog(self.gui, metadata, cover_path)
            result = d.exec()
            
            approved_data = d.get_approved_data() if result == d.DialogCode.Accepted else None
            if approved_data is not None:
                approved_data['_analysis_record'] = metadata
            
            d.setParent(None)
            d.deleteLater()
            
            if approved_data:
                self.apply_metadata(book_id, approved_data)
            else:
                self._record_result(book_id, 'skipped', 'review_cancelled', metadata)
                
        except Exception as e:
            self._record_result(book_id, 'skipped', str(e), metadata)
            from calibre.gui2 import error_dialog
            error_dialog(self.gui, _('UI Error'), _('Could not launch review: {0}').format(str(e)), show=True)
            
        finally:
            self.pending_context.pop(book_id, None)
            # --- Trigger the next book in the queue when the window closes ---
            self.process_next_in_queue()
            # -----------------------------------------------------------------

    def _show_error_dialog(self, error_msg):
        """Safely displays error messages on the main GUI thread."""
        if not self.review_each:
            print('AI Filename Metadata:', error_msg)
            self._status_message(error_msg)
            return
        from calibre.gui2 import error_dialog
        error_dialog(self.gui, _("AI Vision Error"), error_msg, show=True)

    def apply_metadata(self, book_id, approved_data):
        db = self.gui.current_db.new_api
        context = self.pending_context.get(book_id, {})
        if db is not self.queue_db or not context:
            self._record_result(book_id, 'skipped', 'analysis_context_or_library_changed', approved_data.get('_analysis_record'))
            self.signals.error_signal.emit(_("The analysis context or library changed. Metadata was not written."))
            return False
        result = apply_metadata_safely(
            db, book_id, approved_data,
            snapshot=context.get('snapshot'),
            expected_library_id=context.get('library_id'),
        )
        if result.get('status') == 'conflict':
            self._record_result(book_id, 'skipped', result.get('reason', 'conflict'), approved_data.get('_analysis_record'))
            self.signals.error_signal.emit(_("Metadata was not written safely: {0}").format(result.get('reason', 'conflict')))
            return False
        self._record_result(book_id, result.get('status', 'unchanged'), metadata=approved_data.get('_analysis_record'))
        if result.get('status') == 'written':
            self.gui.library_view.model().refresh_ids([book_id])
            return True
        return False
