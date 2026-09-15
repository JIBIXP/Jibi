from pathlib import Path


class DocumentParser:

    SUPPORTED_FORMATS = {
        ".pdf": "pdf",
        ".docx": "word",
        ".txt": "text",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".bmp": "image",
        ".webp": "image",
        ".tiff": "image",
    }


    @classmethod
    def get_file_type(cls, file_path):
        """Retourne le type du fichier."""

        extension = Path(
            file_path
        ).suffix.lower()

        return cls.SUPPORTED_FORMATS.get(
            extension,
            "unknown"
        )


    @classmethod
    def is_supported(cls, file_path):
        """Vérifie si le format est supporté."""

        return (
            cls.get_file_type(file_path)
            != "unknown"
        )


    @classmethod
    def get_extension(cls, file_path):
        """Retourne l'extension normalisée."""

        return Path(
            file_path
        ).suffix.lower()