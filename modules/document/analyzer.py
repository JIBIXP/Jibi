from pathlib import Path

import PyPDF2
from docx import Document
from PIL import Image
import pytesseract


class DocumentAnalyzer:

    @staticmethod
    def analyze_pdf(file_path):
        """Extrait le texte d'un PDF."""

        text = ""

        with open(file_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)

            for page in reader.pages:
                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

        return text.strip()


    @staticmethod
    def analyze_word(file_path):
        """Extrait le texte d'un document Word."""

        doc = Document(file_path)

        paragraphs = [
            paragraph.text
            for paragraph in doc.paragraphs
            if paragraph.text.strip()
        ]

        return "\n".join(paragraphs)


    @staticmethod
    def analyze_image(file_path, language="fra+eng"):
        """Effectue un OCR sur une image."""

        image = Image.open(file_path)

        text = pytesseract.image_to_string(
            image,
            lang=language
        )

        return text.strip()


    @classmethod
    def analyze(cls, file_path):
        """
        Analyse automatiquement un fichier selon son extension.
        """

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Fichier introuvable : {file_path}"
            )

        extension = path.suffix.lower()

        if extension == ".pdf":
            return cls.analyze_pdf(file_path)

        if extension in [".docx"]:
            return cls.analyze_word(file_path)

        if extension in [
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".webp",
            ".tiff"
        ]:
            return cls.analyze_image(file_path)

        raise ValueError(
            f"Format non supporté : {extension}"
        )