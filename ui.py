# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
from qt.core import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, 
                     QLineEdit, QComboBox, QCheckBox, QPushButton, QDialogButtonBox, 
                     QTextEdit, QPixmap, Qt, QStyledItemDelegate, QPalette)

import typing

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

class DropdownDescriptionDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # 1. Let Qt draw the standard item (handles the blue selection background and the main text)
        super().paint(painter, option, index)

        # 2. Check if we secretly attached a description to this item using the UserRole
        description = index.data(Qt.ItemDataRole.UserRole)
        if description:
            painter.save()
            
            # Use the system's muted placeholder color (usually a nice gray)
            color = option.palette.color(QPalette.ColorRole.PlaceholderText)
            painter.setPen(color)

            # Draw the description right-aligned with a 5px margin so it doesn't hug the scrollbar
            rect = option.rect
            rect.adjust(0, 0, -5, 0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, description)
            
            painter.restore()

class MetadataReviewDialog(QDialog):
    def __init__(self, parent, metadata, cover_path):
        super().__init__(parent)
        self.setWindowTitle(_("Review AI Metadata"))
        self.setMinimumWidth(900)
        
        self.layout = QVBoxLayout(self)
        self.metadata = metadata
        self.results = {}
        
        # --- Centered Model Header ---
        model_name = metadata.get('ai_model_used', _('Unknown Model'))
        provider_name = metadata.get('ai_provider', _('AI'))
        duration = metadata.get('api_duration', 0.0)
        
        # Build a dynamic string with the provider, model, and formatted elapsed time
        header_text = _("<center><b>{0} : {1}</b><br><span style='color: gray; font-size: 10px;'><i>(Processed in {2} seconds)</i></span></center>").format(provider_name, model_name, duration)
        
        self.header_label = QLabel(header_text)
        self.layout.addWidget(self.header_label)
        
        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.layout.addWidget(self.line)
        # ----------------------------------
        
        # --- Side-by-Side Layout Container ---
        self.middle_layout = QHBoxLayout()
        
        # 1. Left Side: The Cover Image
        self.cover_label = QLabel()
        if cover_path:
            import os
            if os.path.exists(cover_path):
                pixmap = QPixmap(cover_path)
                if not pixmap.isNull():
                    # Scale the image height to match the form, keeping it looking sharp
                    scaled_pixmap = pixmap.scaledToHeight(450, Qt.TransformationMode.SmoothTransformation)
                    self.cover_label.setPixmap(scaled_pixmap)
        
        # Pin the image to the top left so it doesn't float weirdly
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.middle_layout.addWidget(self.cover_label)
        
        # 2. Right Side: The Form
        self.form_layout = QVBoxLayout()
        self.row_counter = 0
        
        # --- HELPER FUNCTIONS (Zebra Striped Rows) ---
        def create_row_container():
            row_frame = QFrame()
            row_frame.setObjectName("formRow")
            if self.row_counter % 2 != 0:
                row_frame.setStyleSheet("QFrame#formRow { background-color: rgba(128, 128, 128, 64); border-radius: 4px; }")
            self.row_counter += 1
            
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(5, 5, 5, 5)
            return row_frame, row_layout

        def add_field(key, label_text, value, mode):
            row_frame, row_layout = create_row_container()
            
            # Injecting a muted, italicized sub-label
            rich_label = f"{label_text}<br><span style='color: gray; font-size: 10px;'><i>({mode})</i></span>"
            label = QLabel(rich_label)
            label.setFixedWidth(130)
            row_layout.addWidget(label)
            
            edit = QLineEdit(str(value) if value else "")
            row_layout.addWidget(edit, 1) 
            
            chk = QCheckBox()
            has_data = bool(str(value).strip() if value else False)
            chk.setChecked(has_data)
            row_layout.addWidget(chk)
            
            self.form_layout.addWidget(row_frame)
            self.results[key] = {'checkbox': chk, 'widget': edit}

        def add_indented_combo_field(key, label_text, options, mode):
            row_frame, row_layout = create_row_container()
            
            spacer = QLabel()
            spacer.setFixedWidth(130)
            row_layout.addWidget(spacer)
            row_layout.addStretch(1)
            
            rich_label = f"{label_text} <span style='color: gray; font-size: 10px;'><i>({mode})</i></span>"
            label = QLabel(rich_label)
            row_layout.addWidget(label)
            
            combo = QComboBox()
            combo.setEditable(True)
            combo.setMinimumWidth(150) # Made slightly wider to fit the descriptions
            
            # --- NEW: Attach our custom painter to the drop-down list ---
            combo.setItemDelegate(DropdownDescriptionDelegate(combo))
            
            unique_opts = []
            for opt in options:
                # Check if the option is a tuple (Value, Description) or just a standard string
                val = opt[0] if isinstance(opt, tuple) else opt
                desc = opt[1] if isinstance(opt, tuple) else ""
                
                if val and val not in unique_opts:
                    unique_opts.append(val)
                    combo.addItem(val)
                    
                    # --- NEW: Secretly store the description in the item's UserRole memory ---
                    if desc:
                        combo.setItemData(combo.count() - 1, desc, Qt.ItemDataRole.UserRole)
            
            chk = QCheckBox()
            chk.setChecked(bool(unique_opts))
            row_layout.addWidget(combo)
            row_layout.addWidget(chk)
            
            self.form_layout.addWidget(row_frame)
            self.results[key] = {'checkbox': chk, 'widget': combo}

        def add_text_area(key, label_text, value, mode):
            row_frame, row_layout = create_row_container()
            
            rich_label = f"{label_text}<br><span style='color: gray; font-size: 10px;'><i>({mode})</i></span>"
            label = QLabel(rich_label)
            label.setFixedWidth(130)
            row_layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignTop)
            
            edit = QTextEdit()
            edit.setPlainText(str(value) if value else "")
            edit.setMaximumHeight(80) 
            row_layout.addWidget(edit, 1)
            
            chk = QCheckBox(self)
            has_data = bool(str(value).strip() if value else False)
            chk.setChecked(has_data)
            row_layout.addWidget(chk, alignment=Qt.AlignmentFlag.AlignTop)
            
            self.form_layout.addWidget(row_frame)
            self.results[key] = {'checkbox': chk, 'widget': edit}

        # --- BUILD THE FORM ---
        add_field("title", _("Title"), metadata.get('title', ''), _("Replaces"))
        
        raw_creators = metadata.get('creators')
        if not raw_creators:
            rogue_editor = metadata.get('editor')
            rogue_author = metadata.get('author')
            if rogue_editor: raw_creators = [rogue_editor]
            elif rogue_author: raw_creators = [rogue_author]
            else: raw_creators = []
        
        creators_str = ", ".join(raw_creators) if isinstance(raw_creators, list) else str(raw_creators)
        add_field("authors", _("Creators"), creators_str, _("Replaces"))

        series_val = str(metadata.get('series', '')).strip()
        vol = str(metadata.get('volume', '')).strip()
        iss = str(metadata.get('issue_number', '')).strip()
        
        # Build the raw list of possibilities as Tuples (Value, Description)
        index_options = []
        if vol and iss and vol.isdigit() and iss.isdigit():
            index_options.append( (f"{vol}.{iss.zfill(2)}", "") )
            
        if iss: index_options.append( (iss, "") )
        if vol: index_options.append( (vol, "") )
        if metadata.get('day_of_year'):
            index_options.append( (str(metadata.get('day_of_year')), _("(Julian Date)")) )
        if metadata.get('week_of_year'):
            index_options.append( (str(metadata.get('week_of_year')), _("(Week №)")) )
            
        # Strict Decimal and Float Filter
        filtered_index_options = []
        for opt in index_options:
            val = opt[0] # The numeric value we need to test
            try:
                float(val)
                if '.' in val:
                    if len(val.split('.')[-1]) <= 2:
                        filtered_index_options.append(opt)
                else:
                    filtered_index_options.append(opt)
            except ValueError:
                pass
            
        add_indented_combo_field('series', _('Series:'), [series_val], _("Replaces"))
        add_indented_combo_field('series_index', _('Series Index:'), filtered_index_options, _("Replaces"))

        tags_str = ", ".join(metadata.get('tags', [])) if isinstance(metadata.get('tags', []), list) else str(metadata.get('tags', ''))
        add_field("tags", _("Tags"), tags_str, _("Merges"))

        langs_str = ", ".join(metadata.get('languages', ['eng'])) if isinstance(metadata.get('languages', ['eng']), list) else str(metadata.get('languages', 'eng'))
        add_field("languages", _("Languages"), langs_str, _("Replaces"))

        add_field("publisher", _("Publisher"), metadata.get('publisher', ''), _("Replaces"))

        year_raw = metadata.get('pub_year')
        if year_raw and str(year_raw).strip().isdigit():
            year = str(year_raw).strip()
            month_raw = metadata.get('pub_month')
            month = str(month_raw).strip().zfill(2) if month_raw and str(month_raw).strip().isdigit() else "01"
            day_raw = metadata.get('pub_day')
            day = str(day_raw).strip().zfill(2) if day_raw and str(day_raw).strip().isdigit() else "01"
            pub_date = f"{year}-{month}-{day}"
        else:
            pub_date = ""
            
        add_field("pubdate", _("Published"), pub_date, _("Replaces"))
        add_field("identifiers", _("Identifiers"), metadata.get('ids', ''), _("Merges")) # IDs use the merge logic!
        add_text_area("comments", _("Comments"), metadata.get('comments', ''), _("Appends")) # Comments stack via HTML break

        self.form_layout.addStretch(1)

        # Add the completed form to the right side of the middle layout
        self.middle_layout.addLayout(self.form_layout)
        
        # Add the entire middle layout to the main window
        self.layout.addLayout(self.middle_layout)

        # --- AI Disclaimer & Buttons (Spans the full width at the bottom) ---
        disclaimer_text = _(
            "<i><b>Note:</b> The metadata above was generated by an AI model and may contain errors or inaccuracies. "
            "Please review each field carefully. Use the checkboxes to strictly control whether "
            "this new data should overwrite or be appended to your existing Calibre library data.</i>"
        )
        self.disclaimer_label = QLabel(disclaimer_text)
        self.disclaimer_label.setWordWrap(True)
        font = self.disclaimer_label.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        self.disclaimer_label.setFont(font)
        self.disclaimer_label.setContentsMargins(0, 10, 0, 10) 
        self.layout.addWidget(self.disclaimer_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def get_approved_data(self):
        approved = {}
        for key, data in self.results.items():
            chk = data['checkbox']
            widget = data['widget']
            
            if chk.isChecked():
                if isinstance(widget, QComboBox):
                    approved[key] = widget.currentText().strip()
                elif isinstance(widget, QTextEdit):
                    approved[key] = widget.toPlainText().strip()
                else:
                    approved[key] = widget.text().strip()
        return approved