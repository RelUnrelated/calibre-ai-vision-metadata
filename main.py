# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
import base64
import json
import urllib.request
import datetime
import os
import typing
from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                     QComboBox, QPushButton, QMessageBox, QIcon, QPixmap, 
                     pyqtSignal, Qt, QObject, QSpinBox, QMenu, QTextEdit)

from calibre.gui2 import error_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob
from calibre_plugins.ai_vision_metadata.config import prefs

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

class WorkerSignals(QObject):
    review_signal = pyqtSignal(object, object, object)
    error_signal = pyqtSignal(str)  

DEFAULT_PROMPT = (
    "Analyze this publication cover. Your PRIMARY task is to read and extract information "
    "visibly printed on THIS specific cover. "
    "If the specific issue number, exact publication date, or current editor/publisher is not "
    "printed on the cover, use your Google Search tool to find the official publication details "
    "for this exact issue. Do NOT substitute data from older or different issues. "
    "Return ONLY a JSON object with the following keys. "
    "Format requirements: "
    "'series' (string: the base name of the publication), "
    "'volume' (string: the volume number ONLY, converted to standard Arabic numerals, e.g., '48' instead of 'XLVIII'), "
    "'issue_number' (string: the absolute issue number ONLY, converted to standard Arabic numerals. Do not include the volume.), "
    "'title' (string: format strictly as '[Publication Name], [Date], Volume [Vol], Issue [Num]'), "
    "'creators' (list of strings: the main artists or authors. If this is a magazine, you MUST use Google Search to find the current Editor-in-Chief or Managing Editor for this date and list them here), "
    "'pub_year' (integer: the specific year of this issue), "
    "'pub_month' (integer), 'pub_day' (integer), "
    "'publisher' (string: the publishing company or organization), "
    "'ids' (string: format as 'issn:XXXX-XXXX' or 'isbn:XXXXXXXXXX'), "
    "'format_type' (string: e.g., 'magazine', 'comic', 'newspaper', 'book'), "
    "'comments' (string: A brief, 2-to-3 sentence description or summary of this specific issue based on the cover art, headline teasers, and web search context. Explicitly list the main themes, articles, or stories if they are readily available), "
    "'tags' (list of strings: relevant subjects based on the specific cover art and text), "
    "'languages' (list of strings: the 3-letter ISO 639-2 language codes, e.g., ['eng'], ['rus'], or ['deu'])."
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
        self.providers = ['Google Gemini', 'OpenAI', 'Anthropic', 'OpenRouter', 'Local (Ollama/LM Studio)']
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
        self.key_anthropic.setVisible(False)
        self.key_openrouter.setVisible(False)
        # Hide all model combos first
        self.model_google.setVisible(False)
        self.model_openai.setVisible(False)
        self.model_anthropic.setVisible(False)
        self.model_openrouter.setVisible(False)
        self.model_local.setVisible(False)        
        # Hide all prompt editing areas first
        self.prompt_google.setVisible(False)
        self.prompt_openai.setVisible(False)
        self.prompt_anthropic.setVisible(False)
        self.prompt_openrouter.setVisible(False)
        self.prompt_local.setVisible(False)
        
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
                            
            elif provider == 'OpenAI':
                url = "https://api.openai.com/v1/models"
                req = urllib.request.Request(url, headers={'Authorization': f'Bearer {api_key}'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                for model in data.get('data', []):
                    model_id = model.get('id', '')
                    if 'gpt-4o' in model_id or 'gpt-4-turbo' in model_id:
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
            elif provider == 'Anthropic':
                self.prompt_anthropic.setPlainText(DEFAULT_PROMPT)
            elif provider == 'Local (Ollama/LM Studio)':
                self.prompt_local.setPlainText(DEFAULT_PROMPT)

    def save_settings(self):
        # 1. Save the active provider
        prefs['ai_provider'] = self.provider_combo.currentText()
        
        # 2. Save API Keys & URLs
        prefs['api_key_google'] = self.key_google.text().strip()
        prefs['api_key_openai'] = self.key_openai.text().strip()
        prefs['api_key_anthropic'] = self.key_anthropic.text().strip()
        prefs['api_key_openrouter'] = self.key_openrouter.text().strip()
        prefs['local_url'] = self.url_input.text().strip()
        
        # 3. Save Models
        prefs['model_google'] = self.model_google.currentText().strip()
        prefs['model_openai'] = self.model_openai.currentText().strip()
        prefs['model_anthropic'] = self.model_anthropic.currentText().strip()
        prefs['model_openrouter'] = self.model_openrouter.currentText().strip()
        prefs['model_local'] = self.model_local.currentText().strip()
        
        # 4. Save Custom Prompts
        prefs['prompt_google'] = self.prompt_google.toPlainText().strip()
        prefs['prompt_openai'] = self.prompt_openai.toPlainText().strip()
        prefs['prompt_anthropic'] = self.prompt_anthropic.toPlainText().strip()
        prefs['prompt_openrouter'] = self.prompt_openrouter.toPlainText().strip()
        prefs['prompt_local'] = self.prompt_local.toPlainText().strip()
        
        # 5. Save General Settings
        prefs['timeout'] = self.timeout_spin.value()

class AIVisionAction(InterfaceAction):
    name = 'AI Vision Metadata' # DO NOT TRANSLATE
    action_spec = ('AI Vision Metadata', 'images/icon.png', _('Identify book via AI Vision'), 'Ctrl+Shift+I')

    def genesis(self):
        self.signals = WorkerSignals()
        self.signals.review_signal.connect(self._show_review_dialog, type=Qt.ConnectionType.QueuedConnection)
        
        # --- Wire up the error signal using a QueuedConnection ---
        self.signals.error_signal.connect(self._show_error_dialog, type=Qt.ConnectionType.QueuedConnection)
        # --------------------------------------------------------------

        # 1. The Main Action (This still catches the direct toolbar click)
        self.qaction.triggered.connect(self.identify_book)
        
        # --- Dropdown Menu for Configuration & Context Menu ---
        self.menu = QMenu(self.gui)
        
        # 2. Add the primary action INTO the menu for right-click users
        self.run_action = self.create_action(
            spec=(_('Identify Cover'), 'images/icon.png', _('Run AI Vision Metadata on selected book'), None),
            attr='run_action'
        )

        self.run_action.triggered.connect(self.identify_book)
        self.menu.addAction(self.run_action)
        
        # Add a visual separator line
        self.menu.addSeparator()
        
        # 3. Add the configuration sub-action
        self.config_action = self.create_action(
            spec=('Configure AI Vision', 'images/config.png', 'Settings for AI Vision Metadata', None),
            attr='config_action'
        )
        self.config_action.triggered.connect(self.show_configuration)
        self.menu.addAction(self.config_action)
        
        self.qaction.setMenu(self.menu)
        # ------------------------------------------------------
        
        try:
            # Ask the resource manager to extract both images from the zip
            resources = self.load_resources(['images/icon.png', 'images/config.png'])
            
            # 1. Apply the main icon to the toolbar button and the "Identify Cover" menu item
            icon_data = resources.get('images/icon.png')
            if icon_data:
                pixmap = QPixmap()
                pixmap.loadFromData(icon_data)
                main_icon = QIcon(pixmap)
                self.qaction.setIcon(main_icon)
                self.run_action.setIcon(main_icon)
                
            # 2. Apply the custom config icon to the settings menu item
            config_data = resources.get('images/config.png')
            if config_data:
                config_pixmap = QPixmap()
                config_pixmap.loadFromData(config_data)
                self.config_action.setIcon(QIcon(config_pixmap))
                
        except Exception as e:
            # Fails silently if the images aren't found, falling back to default text/icons
            pass

    def show_configuration(self):
        # This native Calibre command instantly summons the ConfigWidget
        self.interface_action_base_plugin.do_user_config(self.gui)

    def identify_book(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            from calibre.gui2 import error_dialog
            return error_dialog(self.gui, _('No Selection'), _('Please select at least one book.'), show=True)

        # Build the queue of Book IDs from the highlighted rows
        self.batch_queue = [self.gui.library_view.model().id(row) for row in rows]
        
        # Start the assembly line
        self.process_next_in_queue()

    def process_next_in_queue(self):
        """Pops the next book from the queue and starts the AI job."""
        if not hasattr(self, 'batch_queue') or not self.batch_queue:
            # The queue is empty, the batch is done!
            return

        # Pop the first ID off the front of the list
        book_id = self.batch_queue.pop(0)
        db = self.gui.current_db.new_api

        # Fetch the cover path
        rel_path = db.field_for('path', book_id)
        if rel_path:
            lib_path = self.gui.current_db.library_path
            cover_path = os.path.join(lib_path, rel_path.replace('/', os.sep), 'cover.jpg')
        else:
            cover_path = None

        if not cover_path or not os.path.exists(cover_path):
            # If there's no cover, show an error for this book and immediately grab the next one!
            self.signals.error_signal.emit(_("Book ID {0} has no cover image to process. Skipping to next.").format(book_id))
            self.process_next_in_queue()
            return

        # Launch the background thread
        from calibre.gui2.threaded_jobs import ThreadedJob
        job = ThreadedJob(
            'identifying_book', 
            _('Analyzing cover for book ID: {0}').format(book_id),  
            self.run_api_request, 
            (book_id, cover_path, ""), # Passing "" since api_key_ignored is no longer used
            {}, 
            self.job_finished
        )
        self.gui.job_manager.run_threaded_job(job)

    def run_api_request(self, book_id, cover_path, api_key_ignored, **kwargs):
        import time
        start_time = time.time() # --- Start the clock ---

        from qt.core import QImage, QByteArray, QBuffer, Qt
        
        # 1. Load the image into memory using Qt
        img = QImage(cover_path)
        
        # 2. Check if the image is massive. If so, scale it down to a max of 2000px
        max_size = 2000
        if img.width() > max_size or img.height() > max_size:
            img = img.scaled(max_size, max_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
        # 3. Save the optimized image to a temporary memory buffer as a JPEG
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        # 85% quality is visually indistinguishable and perfect for AI OCR
        img.save(buffer, "JPEG", quality=85) 
        
        # 4. Encode the lightweight memory buffer to Base64
        img_data = base64.b64encode(byte_array.data()).decode('utf-8')

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
        # -----------------------------------

        # --- DYNAMIC ROUTING & PAYLOAD BUILDER ---
        headers = {'Content-Type': 'application/json'}

        if provider == 'Google Gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_data}}
                    ]
                }],
                "tools": [{"googleSearch": {}}]
            }

        elif provider in ['OpenAI', 'OpenRouter', 'Local (Ollama/LM Studio)']:
            if provider == 'OpenAI':
                url = "https://api.openai.com/v1/chat/completions"
                headers['Authorization'] = f'Bearer {api_key}'
            elif provider == 'OpenRouter':
                url = "https://openrouter.ai/api/v1/chat/completions" # Fixed endpoint
                headers['Authorization'] = f'Bearer {api_key}'
                headers['HTTP-Referer'] = "https://www.mobileread.com/forums/showthread.php?t=372744"
                headers['X-Title'] = "Calibre AI Vision Metadata Plugin"
            else:
                url = f"{local_url}/v1/chat/completions"

            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}}
                        ]
                    }
                ],
                # This explicitly tells OpenAI/OpenRouter/Ollama to format their output as JSON
                "response_format": {"type": "json_object"} 
            }

        elif provider == 'Anthropic':
            url = "https://api.anthropic.com/v1/messages"
            headers['x-api-key'] = api_key
            headers['anthropic-version'] = '2023-06-01'

            payload = {
                "model": model_name,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img_data
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
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

            for attempt in range(max_retries):
                try:
                    # Pass the dynamic timeout variable to the request
                    with urllib.request.urlopen(req, timeout=timeout_val) as response:
                        res_json = json.loads(response.read().decode('utf-8'))
                    
                    # If the call succeeds, break out of the retry loop immediately!
                    break 

                except urllib.error.HTTPError as http_err:
                    # Check specifically for Google 503s or generic 429 Rate Limits
                    if http_err.code in [429, 503] and attempt < max_retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
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
                    return {"error_msg": _("The AI took too long to analyze the cover and search the web. Please try again.")}
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
                    return {"error_msg": _("The AI blocked this cover due to its safety filters.")}
                parts = candidate.get('content', {}).get('parts', [])
                if parts:
                    raw_text = parts[0].get('text', '')

            elif provider in ['OpenAI', 'OpenRouter', 'Local (Ollama/LM Studio)']:
                choices = res_json.get('choices', [])
                if choices:
                    raw_text = choices[0].get('message', {}).get('content', '')

            elif provider == 'Anthropic':
                content_blocks = res_json.get('content', [])
                if content_blocks:
                    raw_text = content_blocks[0].get('text', '')

            if not raw_text:
                return {"error_msg": _("The AI returned an empty response. The model may have failed to process the image.")}
                
            # --- SURGICAL JSON EXTRACTION ---
            def extract_json_dict(text_payload):
                # 1. Strip markdown code blocks if the AI used them
                if "```json" in text_payload:
                    text_payload = text_payload.split("```json")[1].split("```")[0]
                elif "```" in text_payload:
                    text_payload = text_payload.split("```")[1].split("```")[0]
                    
                # 2. Find the absolute first and last curly braces
                start_idx = text_payload.find('{')
                end_idx = text_payload.rfind('}')
                
                if start_idx != -1 and end_idx != -1:
                    clean_text = text_payload[start_idx:end_idx+1]
                    try:
                        parsed_data = json.loads(clean_text)
                        # Ensure it returned a dictionary, not a parsed string
                        if isinstance(parsed_data, dict):
                            return parsed_data
                    except json.JSONDecodeError:
                        pass
                # Return empty dictionary if all extraction fails
                return {}

            metadata = extract_json_dict(raw_text)
            
            if not metadata:
                return {"error_msg": _("Data Parsing Error: Could not extract valid JSON from AI output.\nRaw Output: {0}...").format(raw_text[:150])}

            # Inject dynamic provider, model, and duration
            elapsed = time.time() - start_time
            metadata['ai_provider'] = provider
            metadata['ai_model_used'] = model_name
            metadata['api_duration'] = round(elapsed, 1)

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
            
            try:
                # 1. Ensure we have a valid year first
                pub_year_raw = metadata.get('pub_year')
                if not pub_year_raw or not str(pub_year_raw).strip().isdigit():
                    raise ValueError
                pub_year = int(pub_year_raw)
                
                # 2. Safely parse month and day (If AI gives "00" or empty, assume the 1st)
                pm = metadata.get('pub_month')
                pub_month = int(pm) if pm and str(pm).isdigit() and int(pm) > 0 else 1
                
                pd = metadata.get('pub_day')
                pub_day = int(pd) if pd and str(pd).isdigit() and int(pd) > 0 else 1

                # 3. Calculate Julian and Weekly values safely
                dt = datetime.date(pub_year, pub_month, pub_day)
                yday = dt.timetuple().tm_yday
                metadata['day_of_year'] = str(yday)
                
                week_num = (yday - 1) // 7 + 1
                metadata['week_of_year'] = f"{pub_year}.{str(week_num).zfill(2)}"
                
            except Exception:
                # If date parsing fails completely, do NOT inject a fake "1"
                pass 
                
            # --- Return the cover_path along with the ID and metadata ---
            return (book_id, metadata, cover_path)
            # ------------------------------------------------------------

        except Exception as e:
            return {"error_msg": _("Data Parsing Error: {0}").format(str(e))}

    def job_finished(self, job):
        if job.failed:
            return self.gui.job_exception(job, dialog_title=_("AI Vision Failed"))
            
        result = job.result
        
        if "error_msg" in result:
            self.signals.error_signal.emit(result["error_msg"])
            return
        else:
            book_id, metadata, cover_path = job.result
            self.signals.review_signal.emit(book_id, metadata, cover_path)
            
    def _show_review_dialog(self, book_id, metadata, cover_path):
        try:
            from calibre_plugins.ai_vision_metadata.ui import MetadataReviewDialog
            from calibre.gui2 import error_dialog
            
            # Pass the cover_path into the Dialog
            d = MetadataReviewDialog(self.gui, metadata, cover_path)
            result = d.exec_()
            
            approved_data = d.get_approved_data() if result == d.Accepted else None
            
            d.setParent(None)
            d.deleteLater()
            
            if approved_data:
                self.apply_metadata(book_id, approved_data)
                
        except Exception as e:
            from calibre.gui2 import error_dialog
            error_dialog(self.gui, _('UI Error'), _('Could not launch review: {0}').format(str(e)), show=True)
            
        finally:
            # --- Trigger the next book in the queue when the window closes ---
            self.process_next_in_queue()
            # -----------------------------------------------------------------

    def _show_error_dialog(self, error_msg):
        """Safely displays error messages on the main GUI thread."""
        from calibre.gui2 import error_dialog
        error_dialog(self.gui, _("AI Vision Error"), error_msg, show=True)

    def apply_metadata(self, book_id, approved_data):
        db = self.gui.current_db.new_api
        mi = db.get_metadata(book_id)
        
        # 1. Set Languages First (Crucial for the title_sort algorithm)
        if 'languages' in approved_data:
            # Calibre expects lowercase 3-letter codes
            langs = [l.strip().lower() for l in approved_data['languages'].split(',') if l.strip()]
            if langs:
                mi.languages = langs

        # 2. Set Title and Title Sort (Passing the language we just extracted)
        if 'title' in approved_data: 
            mi.title = approved_data['title']
            from calibre.ebooks.metadata import title_sort
            # Safely grab the primary language code to feed the sort routine
            lang_code = mi.languages[0] if mi.languages else None
            mi.title_sort = title_sort(mi.title, lang=lang_code)
            
        if 'authors' in approved_data:
            authors = [a.strip() for a in approved_data['authors'].split(',') if a.strip()]
            if authors: 
                mi.authors = authors
                
                # Import the standalone function from Calibre's metadata tools
                from calibre.ebooks.metadata import authors_to_sort_string
                mi.author_sort = authors_to_sort_string(mi.authors)
                
        if 'series' in approved_data: 
            mi.series = approved_data['series']
        if 'series_index' in approved_data:
            try: mi.series_index = float(approved_data['series_index'])
            except ValueError: pass

        if 'publisher' in approved_data:
            mi.publisher = approved_data['publisher']
            
        if 'pubdate' in approved_data:
            try:
                import datetime
                mi.pubdate = datetime.datetime.strptime(approved_data['pubdate'], "%Y-%m-%d")
            except ValueError:
                pass

        if 'tags' in approved_data:
            # Convert the comma-separated string from the UI into a clean list
            new_tags = [t.strip() for t in approved_data['tags'].split(',') if t.strip()]
            
            # Fetch existing tags from Calibre (returns None if empty)
            existing_tags = mi.tags if mi.tags else []
            
            # Append new tags only if they don't already exist in the book's metadata
            for tag in new_tags:
                if tag not in existing_tags:
                    existing_tags.append(tag)
                    
            mi.tags = existing_tags

        # --- 2. Identifiers (Merge Dictionaries) ---
        if 'identifiers' in approved_data:
            new_ids_str = approved_data['identifiers']
            
            # Calibre stores identifiers as a dictionary (e.g., {'isbn': '1234', 'issn': '5678'})
            existing_ids = mi.identifiers if mi.identifiers else {}
            
            # Parse the AI's comma-separated string and inject it into the dictionary
            for pair in new_ids_str.split(','):
                if ':' in pair:
                    key, val = pair.split(':', 1)
                    # This updates existing keys or adds new ones without destroying the rest
                    existing_ids[key.strip().lower()] = val.strip()
            
            mi.identifiers = existing_ids

        # --- 3. Comments (Append Text) ---
        if 'comments' in approved_data:
            new_comments = approved_data['comments']
            existing_comments = mi.comments if mi.comments else ""
            
            # If there is already text in the comments field, add a line break first
            if existing_comments.strip():
                # Using HTML breaks so it renders cleanly in Calibre's book details pane
                mi.comments = f"{existing_comments}<br><br><b>AI Summary:</b><br>{new_comments}"
            else:
                mi.comments = new_comments
                
        # --- 4. Pass the metadata to Calibre's new_api cache ---
        db.set_metadata(book_id, mi)
        
        # --- 5. Force the UI to redraw ---
        self.gui.library_view.model().refresh_ids([book_id])