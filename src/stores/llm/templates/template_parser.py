import os
import importlib.util

class TemplateParser:

    def __init__(self, language: str = None, default_language: str = 'en'):
        self.current_path = os.path.dirname(os.path.abspath(__file__))
        self.default_language = default_language
        self.language = self.default_language

        # Initialize with the validated language directory
        self.set_language(language)

    def set_language(self, language: str):
        """Set the active language directory with fallback to default_language."""
        target_lang = language or self.default_language
        language_path = os.path.join(self.current_path, "locales", target_lang)

        if os.path.exists(language_path):
            self.language = target_lang
        else:
            self.language = self.default_language

    def get(self, group: str, key: str, vars: dict = None):
        """
        Load the specified template and safely substitute provided variables.
        
        Args:
            group (str): File/group name (e.g., 'rag').
            key (str): Template variable name inside the file (e.g., 'system_prompt', 'footer_prompt').
            vars (dict): Dictionary of replacement values for Template placeholders.
        """
        if not group or not key:
            return None

        # Avoid mutable default arguments
        if vars is None:
            vars = {}

        # Locate the template file for the active language
        group_path = os.path.join(self.current_path, "locales", self.language, f"{group}.py")

        # Fallback to the default language if the file is missing
        if not os.path.exists(group_path):
            group_path = os.path.join(self.current_path, "locales", self.default_language, f"{group}.py")

        if not os.path.exists(group_path):
            return None

        # Load the module dynamically from its filesystem path
        spec = importlib.util.spec_from_file_location(f"template_{group}", group_path)
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Retrieve the Template object
        key_attribute = getattr(module, key, None)
        if not key_attribute:
            return None

        # safe_substitute avoids raising a KeyError if a variable is missing
        return key_attribute.safe_substitute(vars)