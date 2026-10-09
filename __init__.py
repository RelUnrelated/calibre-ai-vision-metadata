# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
from calibre.customize import InterfaceActionBase

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

try:
    from calibre.utils.localization import _ as _CALIBRE_TRANSLATE
except ImportError:
    _CALIBRE_TRANSLATE = lambda text: text

def _(text: str) -> str:
    return {
        'Extract manga metadata from original filenames without uploading or analyzing cover images.': '从原始文件名提取漫画元数据，不上传或分析封面图片。'
    }.get(text, _CALIBRE_TRANSLATE(text))

class AIVisionMetadataWrapper(InterfaceActionBase):
    name                    = '漫元 (MetaManga)'
    description             = _('Extract manga metadata from original filenames without uploading or analyzing cover images.')
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'RelUnrelated'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    # THIS IS THE MAGIC STRING: 'folder_name.file_name:ClassName'
    actual_plugin           = 'calibre_plugins.ai_vision_metadata.main:AIVisionAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        if self.actual_plugin_:
            from calibre_plugins.ai_vision_metadata.main import ConfigWidget
            return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
