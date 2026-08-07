import logging


class Settings:
    def __init__(self):
        self.gemini_base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.murf_base_url = "https://api.murf.ai/v1"
        self.assemblyai_base_url = "https://api.assemblyai.com/v2"

        self.static_dir = "static"
        self.templates_dir = "templates"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


settings = Settings()
