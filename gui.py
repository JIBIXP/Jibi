import json
import subprocess
import random
import math
import sys
import queue

from PyQt5.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    QTimer,
    QSize,
    QPointF,
    QUrl
)

from PyQt5.QtGui import (
    QFont,
    QColor,
    QPainter,
    QRadialGradient,
    QTextCursor
)

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QTextBrowser,
    QLineEdit,
    QFrame,
    QGraphicsDropShadowEffect
)

from PyQt5.QtMultimedia import (
    QMediaPlayer,
    QMediaContent
)

import qtawesome as qta
from qt_material import apply_stylesheet

from agent import ask_agent_stream
from voix import generer_audio_client
from logging_jibi import log_event, log_error


# ============================================================
# ONDE AUDIO
# ============================================================

class WaveWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.setMinimumHeight(120)

        self.nb_barres = 56
        self.niveaux = [0.04] * self.nb_barres

        self.niveau_courant = 0
        self.active = False

        self.couleur_fond = QColor("#081018")
        self.couleur_a = QColor("#22d3ee")
        self.couleur_b = QColor("#38bdf8")

        self.timer = QTimer()
        self.timer.timeout.connect(self.avancer)
        self.timer.start(45)

    def set_level(self, level):
        self.niveau_courant = max(0, min(1, float(level)))

    def set_active(self, active):
        self.active = active
        if not active:
            self.niveau_courant = 0

    def avancer(self):
        if self.active:
            cible = 0.15 + self.niveau_courant * 1.6
        else:
            cible = 0.04

        bruit = random.uniform(0.75, 1.25)
        nouvelle_valeur = max(0.03, min(1.0, cible * bruit))

        self.niveaux.pop(0)
        self.niveaux.append(nouvelle_valeur)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        largeur = self.width()
        hauteur = self.height()

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.couleur_fond)
        painter.drawRoundedRect(0, 0, largeur, hauteur, 18, 18)

        marge = 18
        zone_largeur = largeur - marge * 2

        nb = len(self.niveaux)
        espace = 3

        largeur_barre = max(2.0, (zone_largeur - espace * (nb - 1)) / nb)

        centre_y = hauteur / 2
        hauteur_max = hauteur - 28

        x = marge

        for i, niveau in enumerate(self.niveaux):
            h_barre = max(3.0, niveau * hauteur_max)

            couleur = self.couleur_a if i % 2 == 0 else self.couleur_b
            painter.setBrush(couleur)

            rayon = largeur_barre / 2

            painter.drawRoundedRect(
                int(x),
                int(centre_y - h_barre / 2),
                int(largeur_barre),
                int(h_barre),
                rayon,
                rayon
            )

            x += largeur_barre + espace


# ============================================================
# ORBE JIBI
# ============================================================

class OrbeWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.setMinimumSize(220, 220)

        self.niveau = 0.0
        self.actif = False
        self.phase = 0.0

        self.timer = QTimer()
        self.timer.timeout.connect(self._animer)
        self.timer.start(30)

    def set_level(self, level):
        self.niveau = max(0.0, min(1.0, float(level)))

    def set_active(self, actif):
        self.actif = actif
        if not actif:
            self.niveau = 0.0

    def _animer(self):
        self.phase += 0.08
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        largeur = self.width()
        hauteur = self.height()

        cx = largeur / 2
        cy = hauteur / 2

        base = min(largeur, hauteur) * 0.24

        respiration = 1 + 0.08 * math.sin(self.phase)

        rayon = base * respiration

        if self.actif:
            rayon += base * self.niveau * 0.9

        # Halo extérieur
        halo = QRadialGradient(QPointF(cx, cy), rayon * 2.4)
        halo.setColorAt(0.0, QColor(34, 211, 238, 130))
        halo.setColorAt(0.55, QColor(34, 211, 238, 40))
        halo.setColorAt(1.0, QColor(34, 211, 238, 0))

        painter.setBrush(halo)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), rayon * 2.4, rayon * 2.4)

        # Noyau
        noyau = QRadialGradient(QPointF(cx, cy), rayon)
        noyau.setColorAt(0.0, QColor(6, 10, 15))
        noyau.setColorAt(0.65, QColor(10, 18, 26))
        noyau.setColorAt(1.0, QColor(34, 211, 238, 220))

        painter.setBrush(noyau)
        painter.drawEllipse(QPointF(cx, cy), rayon, rayon)


# ============================================================
# OVERLAY VOCAL
# ============================================================

class DialogueOverlay(QWidget):

    def __init__(self, parent):
        super().__init__(parent)

        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setContentsMargins(0, 25, 0, 35)

        ligne_fermer = QHBoxLayout()
        ligne_fermer.setContentsMargins(0, 0, 20, 0)
        ligne_fermer.addStretch()

        self.bouton_fermer = QPushButton()
        self.bouton_fermer.setIcon(qta.icon("fa5s.times", color="#94a3b8"))
        self.bouton_fermer.setIconSize(QSize(16, 16))
        self.bouton_fermer.setFixedSize(40, 40)
        self.bouton_fermer.setFlat(True)

        ligne_fermer.addWidget(self.bouton_fermer)
        self.layout_principal.addLayout(ligne_fermer)

        self.orbe = OrbeWidget()
        self.layout_principal.addWidget(self.orbe, 1)

    def ajouter_barres(self, widget_barres):
        conteneur = QHBoxLayout()
        conteneur.setContentsMargins(80, 0, 80, 0)
        conteneur.addWidget(widget_barres)
        self.layout_principal.addLayout(conteneur)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(3, 7, 12, 245))


# ============================================================
# MICRO
# ============================================================

class ListeningWorker(QThread):

    level = pyqtSignal(float)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def run(self):
        try:
            processus = subprocess.Popen(
                [sys.executable, "ecoute_process.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )

            for ligne in processus.stdout:
                ligne = ligne.strip()

                if not ligne:
                    continue

                try:
                    data = json.loads(ligne)
                except json.JSONDecodeError:
                    continue

                if "level" in data:
                    self.level.emit(float(data["level"]))
                elif "texte" in data:
                    self.finished.emit(data.get("texte", ""), data.get("langue", ""))
                    break

            processus.wait()

        except Exception as e:
            self.error.emit(str(e))


# ============================================================
# VEILLE (MOT D'ACTIVATION)
# ============================================================

class WakeWordWorker(QThread):
    """
    Lance ecoute_process.py en mode --veille : le sous-processus écoute
    en boucle jusqu'à détecter le mot d'activation, puis remonte la
    commande qui suit. Contrairement à ListeningWorker, ce processus
    peut tourner longtemps (indéfiniment) : arreter() permet de le
    couper proprement, notamment juste avant que JIBI se mette à
    parler, pour qu'il n'entende jamais sa propre voix.
    """

    level = pyqtSignal(float)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.processus = None

    def run(self):
        try:
            self.processus = subprocess.Popen(
                [sys.executable, "ecoute_process.py", "--veille"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )

            for ligne in self.processus.stdout:
                ligne = ligne.strip()

                if not ligne:
                    continue

                try:
                    data = json.loads(ligne)
                except json.JSONDecodeError:
                    continue

                if "level" in data:
                    self.level.emit(float(data["level"]))
                elif "texte" in data:
                    self.finished.emit(data.get("texte", ""), data.get("langue", ""))
                    break

            self.processus.wait()

        except Exception as e:
            self.error.emit(str(e))

    def arreter(self):
        """Coupe le sous-processus de veille immédiatement (mic muet)."""

        if self.processus and self.processus.poll() is None:
            try:
                self.processus.terminate()
            except Exception:
                pass


# ============================================================
# AGENT
# ============================================================

class AgentWorker(QThread):

    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, texte):
        super().__init__()
        self.texte = texte

    def run(self):
        try:
            def on_chunk(chunk):
                self.chunk_received.emit(chunk)

            reponse = ask_agent_stream(self.texte, on_chunk)
            self.finished.emit(reponse)

        except Exception as e:
            self.error.emit(str(e))


# ============================================================
# VOIX — SYNTHÈSE EN STREAMING
# ============================================================

class VoiceWorker(QThread):

    phrase_pret = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, langue):
        super().__init__()
        self.langue = langue
        self.file_phrases = queue.Queue()
        self.generation_terminee = False
        self.arret = False

    def ajouter_phrase(self, phrase):
        phrase = phrase.strip()
        if phrase:
            self.file_phrases.put(phrase)

    def terminer(self):
        self.generation_terminee = True

    def stop_worker(self):
        self.arret = True
        self.file_phrases.put(None)

    def run(self):
        try:
            while not self.arret:
                try:
                    phrase = self.file_phrases.get(timeout=0.1)
                except queue.Empty:
                    if self.generation_terminee and self.file_phrases.empty():
                        break
                    continue

                if phrase is None:
                    break

                chemin = generer_audio_client(phrase, self.langue)

                if chemin:
                    self.phrase_pret.emit(chemin)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


# ============================================================
# FENÊTRE PRINCIPALE
# ============================================================

class AgentWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("JIBI — Assistant IA")
        self.resize(1400, 850)
        self.setMinimumSize(1050, 700)

        # Workers
        self.listening_worker = None
        self.agent_worker = None
        self.voice_worker = None
        self.wake_worker = None

        self.speaking_timer = None
        self.mode_dialogue = False
        self.veille_active = False

        # Audio
        self.lecteur_audio = QMediaPlayer()
        self.lecteur_audio.mediaStatusChanged.connect(self.audio_status_changed)

        # Réponse
        self.current_response = ""

        # Streaming vocal
        self.buffer_vocal = ""
        self.langue_vocale = "fr"

        # File audio
        self.file_audio = []
        self.generation_vocale_finie = False
        self.lecture_en_cours = False

        self.setup_ui()

    # ========================================================
    # FERMETURE
    # ========================================================

    def closeEvent(self, event):
        if self.listening_worker and self.listening_worker.isRunning():
            self.listening_worker.wait(3000)

        if self.wake_worker and self.wake_worker.isRunning():
            self.wake_worker.arreter()
            self.wake_worker.wait(3000)

        if self.agent_worker and self.agent_worker.isRunning():
            self.agent_worker.wait(3000)

        if self.voice_worker:
            if self.voice_worker.isRunning():
                self.voice_worker.stop_worker()
                self.voice_worker.wait(3000)

        if self.lecteur_audio.state() == QMediaPlayer.PlayingState:
            self.lecteur_audio.stop()

        super().closeEvent(event)

    # ========================================================
    # REDIMENSIONNEMENT
    # ========================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "overlay") and self.centralWidget():
            self.overlay.setGeometry(self.centralWidget().rect())

    # ========================================================
    # OMBRE
    # ========================================================

    def appliquer_ombre(self, widget, flou=25, decalage_y=6, opacite=180, couleur=(0, 0, 0)):
        ombre = QGraphicsDropShadowEffect()
        ombre.setBlurRadius(flou)
        ombre.setOffset(0, decalage_y)
        ombre.setColor(QColor(couleur[0], couleur[1], couleur[2], opacite))
        widget.setGraphicsEffect(ombre)

    # ========================================================
    # INTERFACE
    # ========================================================

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        self.overlay = DialogueOverlay(central)
        self.overlay.bouton_fermer.clicked.connect(self.fermer_overlay)
        self.overlay.hide()

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ====================================================
        # SIDEBAR
        # ====================================================

        sidebar = QFrame()
        sidebar.setFixedWidth(245)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #080d13;
                border-right: 1px solid #17212b;
            }
        """)

        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 25, 22, 22)
        side.setSpacing(12)

        logo = QLabel("JIBI")
        logo.setFont(QFont("Arial", 30, QFont.Bold))
        logo.setStyleSheet("""
            color: #22d3ee;
            letter-spacing: 3px;
        """)
        side.addWidget(logo)

        desc = QLabel("ASSISTANT PERSONNEL IA")
        desc.setStyleSheet("""
            color: #64748b;
            font-size: 10px;
            letter-spacing: 1px;
        """)
        side.addWidget(desc)

        side.addSpacing(25)

        new_button = QPushButton("  Nouvelle conversation")
        new_button.setIcon(qta.icon("fa5s.plus", color="#22d3ee"))
        new_button.setMinimumHeight(42)
        new_button.setStyleSheet("""
            QPushButton {
                background: #102a38;
                color: #dff8ff;
                border: 1px solid #155e75;
                border-radius: 10px;
                padding: 9px 12px;
                font-weight: bold;
                text-align: left;
            }

            QPushButton:hover {
                background: #164e63;
                border: 1px solid #22d3ee;
            }

            QPushButton:pressed {
                background: #0e7490;
            }
        """)
        new_button.clicked.connect(self.clear_chat)
        side.addWidget(new_button)

        side.addSpacing(10)

        separateur = QFrame()
        separateur.setFrameShape(QFrame.HLine)
        separateur.setStyleSheet("color: #17212b;")
        side.addWidget(separateur)

        side.addStretch()

        status = QLabel("SYSTÈME")
        status.setStyleSheet("""
            color: #475569;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        side.addWidget(status)

        self.system_status = QLabel("● Prêt")
        self.system_status.setStyleSheet("""
            color: #22c55e;
            font-weight: bold;
        """)
        side.addWidget(self.system_status)

        side.addSpacing(8)

        self.status_label = QLabel("Prêt à converser")
        self.status_label.setStyleSheet("""
            color: #94a3b8;
            font-size: 12px;
        """)
        self.status_label.setWordWrap(True)
        side.addWidget(self.status_label)

        layout.addWidget(sidebar)

        # ====================================================
        # CENTRE
        # ====================================================

        center = QFrame()
        center.setStyleSheet("""
            QFrame {
                background: #0d151e;
            }
        """)

        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(32, 24, 32, 22)
        center_layout.setSpacing(14)

        # En-tête
        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("Conversation")
        title.setFont(QFont("Arial", 21, QFont.Bold))
        title.setStyleSheet("color: #e2f8ff;")
        title_box.addWidget(title)

        subtitle = QLabel("JIBI est prêt à vous écouter")
        subtitle.setStyleSheet("""
            color: #64748b;
            font-size: 11px;
        """)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        badge = QLabel("●  LOCAL AI")
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("""
            QLabel {
                background: #0b2632;
                color: #22d3ee;
                border: 1px solid #155e75;
                border-radius: 12px;
                padding: 7px 12px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        header.addWidget(badge)

        center_layout.addLayout(header)

        # ====================================================
        # CHAT
        # ====================================================

        self.chat = QTextBrowser()
        self.chat.setReadOnly(True)
        self.chat.setStyleSheet("""
            QTextBrowser {
                background: #091119;
                color: #dbeafe;
                border: 1px solid #1b3444;
                border-radius: 16px;
                padding: 18px;
                font-size: 14px;
                font-family: "Segoe UI", Arial;
            }

            QTextBrowser:focus {
                border: 1px solid #155e75;
            }

            QScrollBar:vertical {
                background: #091119;
                width: 8px;
                border-radius: 4px;
                margin: 4px;
            }

            QScrollBar::handle:vertical {
                background: #155e75;
                border-radius: 4px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background: #22d3ee;
            }
        """)
        self.appliquer_ombre(self.chat, flou=35, decalage_y=8, opacite=130)
        center_layout.addWidget(self.chat, 1)

        # ====================================================
        # STREAMING
        # ====================================================

        self.streaming_message = QTextEdit()
        self.streaming_message.setReadOnly(True)
        self.streaming_message.setMaximumHeight(145)
        self.streaming_message.setVisible(False)
        self.streaming_message.setStyleSheet("""
            QTextEdit {
                background: #0b1821;
                color: #dbeafe;
                border: 1px solid #155e75;
                border-radius: 14px;
                padding: 14px;
                font-size: 14px;
                font-family: "Segoe UI", Arial;
            }
        """)
        center_layout.addWidget(self.streaming_message)

        # ====================================================
        # MICRO
        # ====================================================

        mic_layout = QHBoxLayout()
        mic_layout.addStretch()

        # Création de la barre audio
        self.wave = WaveWidget()

        # Bouton dialogue
        self.dialogue_button = QPushButton()
        self.dialogue_button.setCheckable(True)
        self.dialogue_button.setIcon(qta.icon("fa5s.comments", color="#dbeafe"))
        self.dialogue_button.setIconSize(QSize(17, 17))
        self.dialogue_button.setFixedSize(46, 46)
        self.dialogue_button.setToolTip("Activer le mode dialogue continu")
        self.dialogue_button.setStyleSheet("""
            QPushButton {
                background: #172738;
                border: 1px solid #28506a;
                border-radius: 12px;
            }

            QPushButton:hover {
                background: #1e3a4c;
                border: 1px solid #22d3ee;
            }

            QPushButton:checked {
                background: #22d3ee;
                border: 1px solid #67e8f9;
            }
        """)
        self.dialogue_button.toggled.connect(self.toggle_dialogue)
        mic_layout.addWidget(self.dialogue_button)

        mic_layout.addSpacing(10)

        # Bouton veille (mot d'activation)
        self.veille_button = QPushButton()
        self.veille_button.setCheckable(True)
        self.veille_button.setIcon(qta.icon("fa5s.satellite-dish", color="#dbeafe"))
        self.veille_button.setIconSize(QSize(17, 17))
        self.veille_button.setFixedSize(46, 46)
        self.veille_button.setToolTip("Veille : dis \"Jibi\" pour m'activer sans les mains")
        self.veille_button.setStyleSheet("""
            QPushButton {
                background: #172738;
                border: 1px solid #28506a;
                border-radius: 12px;
            }

            QPushButton:hover {
                background: #1e3a4c;
                border: 1px solid #22d3ee;
            }

            QPushButton:checked {
                background: #22d3ee;
                border: 1px solid #67e8f9;
            }
        """)
        self.veille_button.toggled.connect(self.toggle_veille)
        mic_layout.addWidget(self.veille_button)

        mic_layout.addSpacing(14)

        # Micro
        self.mic_button = QPushButton()
        self.mic_button.setIcon(qta.icon("fa5s.microphone", color="#ffffff"))
        self.mic_button.setIconSize(QSize(23, 23))
        self.mic_button.setFixedSize(64, 64)
        self.mic_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0e7490, stop:1 #22d3ee
                );
                border: none;
                border-radius: 32px;
                color: white;
            }

            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0891b2, stop:1 #67e8f9
                );
            }

            QPushButton:pressed {
                background: #0e7490;
            }

            QPushButton:disabled {
                background: #334155;
            }
        """)
        self.appliquer_ombre(
            self.mic_button, flou=28, decalage_y=7, opacite=190, couleur=(34, 211, 238)
        )
        self.mic_button.clicked.connect(self.start_listening)
        mic_layout.addWidget(self.mic_button)

        mic_layout.addStretch()
        center_layout.addLayout(mic_layout)

        # ====================================================
        # BARRE AUDIO
        # ====================================================

        center_layout.addWidget(self.wave)

        # ====================================================
        # CHAMP TEXTE
        # ====================================================

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Écris un message à JIBI...")
        self.input.setMinimumHeight(46)
        self.input.setStyleSheet("""
            QLineEdit {
                background: #111d29;
                color: #dbeafe;
                border: 1px solid #1e3a4c;
                border-radius: 12px;
                padding: 10px 14px;
                font-size: 14px;
            }

            QLineEdit:focus {
                border: 1px solid #22d3ee;
                background: #102532;
            }

            QLineEdit::placeholder {
                color: #64748b;
            }
        """)
        self.input.returnPressed.connect(self.send_text)
        input_layout.addWidget(self.input)

        self.send_button = QPushButton("Envoyer")
        self.send_button.setIcon(qta.icon("fa5s.paper-plane", color="#ffffff"))
        self.send_button.setMinimumHeight(46)
        self.send_button.setMinimumWidth(115)
        self.send_button.setStyleSheet("""
            QPushButton {
                background: #0e7490;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 10px 20px;
                font-weight: bold;
            }

            QPushButton:hover {
                background: #22d3ee;
                color: #001018;
            }

            QPushButton:pressed {
                background: #0891b2;
            }

            QPushButton:disabled {
                background: #334155;
                color: #64748b;
            }
        """)
        self.send_button.clicked.connect(self.send_text)
        input_layout.addWidget(self.send_button)

        center_layout.addLayout(input_layout)
        layout.addWidget(center, 1)

        self.add_message(
            "JIBI",
            "Bonjour 👋 Je suis JIBI, ton assistant IA. Comment puis-je t'aider ?"
        )

    # ========================================================
    # MESSAGE
    # ========================================================

    def add_message(self, auteur, message, is_typing=False):
        est_utilisateur = auteur == "Vous"

        alignement = "right" if est_utilisateur else "left"
        couleur_fond = "#0f4c5c" if est_utilisateur else "#162230"
        couleur_nom = "#7dd3fc" if est_utilisateur else "#22d3ee"

        message_html = (
            message
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

        if is_typing:
            message_html += " <span style='color:#22d3ee;'>▌</span>"

        html = f"""
        <table width="100%" cellspacing="0" cellpadding="0" style="margin:10px 0;">
            <tr>
                <td align="{alignement}" style="padding:0 12px;">
                    <table cellspacing="0" cellpadding="14" style="
                           background-color:{couleur_fond};
                           border-radius:16px;
                           border:1px solid #20384a;">
                        <tr>
                            <td>
                                <b style="color:{couleur_nom}; font-size:11px;">{auteur}</b>
                                <br>
                                <span style="color:#e2e8f0; font-size:14px; line-height:1.5;">{message_html}</span>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """

        self.chat.insertHtml(html)

        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.chat.setTextCursor(cursor)

    # ========================================================
    # ENVOI TEXTE
    # ========================================================

    def send_text(self):
        texte = self.input.text().strip()
        if not texte:
            return

        self.input.clear()
        self.add_message("Vous", texte)
        self.start_agent(texte)

    # ========================================================
    # VISUEL VOCAL
    # ========================================================

    def activer_visuel_vocal(self):
        self.overlay.setGeometry(self.centralWidget().rect())
        self.wave.set_active(True)
        self.overlay.orbe.set_active(True)
        self.overlay.raise_()
        self.overlay.show()

    def desactiver_visuel_vocal(self):
        self.wave.set_active(False)
        self.overlay.orbe.set_active(False)
        self.overlay.hide()

    def set_niveau_vocal(self, niveau):
        self.wave.set_level(niveau)
        self.overlay.orbe.set_level(niveau)

    def fermer_overlay(self):
        if self.mode_dialogue:
            self.dialogue_button.setChecked(False)
        self.desactiver_visuel_vocal()

    # ========================================================
    # LANCEMENT AGENT
    # ========================================================

    def start_agent(self, texte):

        if self.agent_worker and self.agent_worker.isRunning():
            self.status_label.setText("⏳ Patiente, je réponds déjà...")
            return

        # Empêche d'écraser un voice_worker encore actif (génération ou
        # lecture audio en cours) — c'est ce qui causait le blocage après
        # la première réponse : le thread précédent était détruit
        # brutalement avant d'avoir fini de jouer l'audio, ce qui
        # bloquait ensuite silencieusement toute nouvelle question.
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.stop_worker()
            self.voice_worker.wait(2000)

        # Coupe la veille (mot d'activation) AVANT de parler : sans ça,
        # le sous-processus de veille continuerait d'écouter le micro
        # pendant que JIBI répond, et risquerait de capter sa propre
        # voix (potentiellement le mot d'activation lui-même dans la
        # réponse) puis de se redéclencher tout seul en boucle.
        if self.wake_worker and self.wake_worker.isRunning():
            self.wake_worker.arreter()
            self.wake_worker.wait(2000)

        self.status_label.setText("🧠 Je réfléchis...")
        self.system_status.setText("● Génération")
        self.system_status.setStyleSheet("color:#f59e0b;")

        self.input.setEnabled(False)
        self.send_button.setEnabled(False)
        self.mic_button.setEnabled(False)

        self.streaming_message.setVisible(True)
        self.streaming_message.setPlainText("")

        self.current_response = ""
        self.buffer_vocal = ""
        self.langue_vocale = "fr"

        self.file_audio = []
        self.generation_vocale_finie = False
        self.lecture_en_cours = False

        # Worker vocal AVANT Ollama
        self.voice_worker = VoiceWorker(self.langue_vocale)
        self.voice_worker.phrase_pret.connect(self.phrase_audio_prete)
        self.voice_worker.finished.connect(self.generation_vocale_terminee)
        self.voice_worker.error.connect(self.voice_error)
        self.voice_worker.start()

        # Worker agent
        self.agent_worker = AgentWorker(texte)
        self.agent_worker.chunk_received.connect(self.on_agent_chunk)
        self.agent_worker.finished.connect(self.agent_finished)
        self.agent_worker.error.connect(self.agent_error)
        self.agent_worker.start()

    # ========================================================
    # CHUNKS OLLAMA
    # ========================================================

    def on_agent_chunk(self, chunk):
        self.current_response += chunk
        self.update_last_message(self.current_response)

        self.buffer_vocal += chunk

        while True:
            position = -1

            for symbole in [".", "!", "?", "。", "！", "？"]:
                p = self.buffer_vocal.find(symbole)
                if p != -1:
                    if position == -1 or p < position:
                        position = p

            if position == -1:
                break

            phrase = self.buffer_vocal[:position + 1].strip()
            self.buffer_vocal = self.buffer_vocal[position + 1:]

            if not phrase:
                continue

            self.langue_vocale = self.detecter_langue(phrase)
            self.voice_worker.langue = self.langue_vocale
            self.voice_worker.ajouter_phrase(phrase)

            if self.status_label.text() == "🧠 Je réfléchis...":
                self.status_label.setText("🔊 JIBI parle...")
                self.system_status.setText("● Réponse")
                self.system_status.setStyleSheet("color:#22d3ee;")

                self.activer_visuel_vocal()

                if not self.speaking_timer:
                    self.speaking_timer = QTimer()
                    self.speaking_timer.timeout.connect(
                        lambda: self.set_niveau_vocal(random.uniform(0.3, 0.9))
                    )

                self.speaking_timer.start(120)

    # ========================================================
    # AFFICHAGE STREAMING
    # ========================================================

    def update_last_message(self, texte):
        self.streaming_message.setVisible(True)
        self.streaming_message.setPlainText(texte + " ▌")

        cursor = self.streaming_message.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.streaming_message.setTextCursor(cursor)

    # ========================================================
    # FIN AGENT
    # ========================================================

    def agent_finished(self, reponse):
        self.input.setEnabled(True)
        self.send_button.setEnabled(True)

        self.streaming_message.setVisible(False)
        self.add_message("JIBI", reponse)

        reste = self.buffer_vocal.strip()

        if reste and self.voice_worker:
            self.voice_worker.langue = self.detecter_langue(reste)
            self.voice_worker.ajouter_phrase(reste)

        self.buffer_vocal = ""

        if self.voice_worker:
            self.voice_worker.terminer()

        if not self.file_audio and not self.lecture_en_cours:
            self.status_label.setText("🔊 JIBI parle...")

    # ========================================================
    # DETECTION LANGUE
    # ========================================================

    def detecter_langue(self, texte):
        texte_nettoye = texte.strip()

        # langdetect est peu fiable sous ~15 caractères ou peu de mots
        # (ce qui arrive souvent : "D'accord.", "Oui bien sûr.", "5 minutes.")
        # — il classe régulièrement ces phrases courtes comme anglaises
        # par erreur, ce qui faisait changer la voix Kokoro en plein
        # milieu d'une réponse française. En dessous de ce seuil, on
        # part directement sur le français plutôt que de risquer une
        # mauvaise détection.
        if len(texte_nettoye) < 15 or len(texte_nettoye.split()) < 4:
            return "fr"

        try:
            from langdetect import detect
            langue = detect(texte_nettoye)
            return "en" if langue == "en" else "fr"

        except Exception:
            texte_min = texte_nettoye.lower()

            mots_anglais = [
                "the", "you", "what", "how", "hello", "your", "with", "this"
            ]

            score = sum(
                1 for mot in mots_anglais if f" {mot} " in f" {texte_min} "
            )

            return "en" if score >= 2 else "fr"

    # ========================================================
    # AUDIO PRET
    # ========================================================

    def phrase_audio_prete(self, chemin):
        if not chemin:
            return

        self.file_audio.append(chemin)

        if not self.lecture_en_cours:
            self._jouer_phrase_suivante()

    # ========================================================
    # GENERATION AUDIO TERMINEE
    # ========================================================

    def generation_vocale_terminee(self):
        self.generation_vocale_finie = True

        if not self.file_audio and not self.lecture_en_cours:
            self.voice_finished()

    # ========================================================
    # LECTURE PHRASE SUIVANTE
    # ========================================================

    def _jouer_phrase_suivante(self):
        if not self.file_audio:
            self.lecture_en_cours = False

            if self.generation_vocale_finie:
                self.voice_finished()

            return

        self.lecture_en_cours = True

        chemin = self.file_audio.pop(0)

        self.lecteur_audio.setMedia(QMediaContent(QUrl.fromLocalFile(chemin)))
        self.lecteur_audio.play()

    # ========================================================
    # FIN AUDIO
    # ========================================================

    def audio_status_changed(self, statut):
        if statut == QMediaPlayer.EndOfMedia:
            self._jouer_phrase_suivante()

    # ========================================================
    # MODE DIALOGUE
    # ========================================================

    def toggle_dialogue(self, actif):
        self.mode_dialogue = actif

        if actif:
            # Dialogue continu et veille par mot d'activation utilisent
            # tous les deux le micro en continu : un seul à la fois pour
            # éviter que deux sous-processus se disputent le périphérique.
            if self.veille_active:
                self.veille_button.setChecked(False)

            self.dialogue_button.setStyleSheet("""
                QPushButton {
                    background: #22d3ee;
                    color: #001018;
                    border: none;
                    border-radius: 12px;
                }
            """)

            self.status_label.setText("Mode dialogue : prêt à écouter")

            if not (self.listening_worker and self.listening_worker.isRunning()):
                self.start_listening()

        else:
            self.dialogue_button.setStyleSheet("""
                QPushButton {
                    background: #172738;
                    border: 1px solid #28506a;
                    border-radius: 12px;
                }

                QPushButton:hover {
                    background: #1e3a4c;
                    border: 1px solid #22d3ee;
                }

                QPushButton:checked {
                    background: #22d3ee;
                }
            """)

            self.status_label.setText("Mode dialogue désactivé")

    # ========================================================
    # VEILLE (MOT D'ACTIVATION)
    # ========================================================

    def toggle_veille(self, actif):
        self.veille_active = actif

        if actif:
            if self.mode_dialogue:
                self.dialogue_button.setChecked(False)

            self.veille_button.setStyleSheet("""
                QPushButton {
                    background: #22d3ee;
                    color: #001018;
                    border: none;
                    border-radius: 12px;
                }
            """)

            self.status_label.setText("En veille : dis \"Jibi\" pour m'activer")

            self.start_veille()

        else:
            if self.wake_worker and self.wake_worker.isRunning():
                self.wake_worker.arreter()

            self.veille_button.setStyleSheet("""
                QPushButton {
                    background: #172738;
                    border: 1px solid #28506a;
                    border-radius: 12px;
                }

                QPushButton:hover {
                    background: #1e3a4c;
                    border: 1px solid #22d3ee;
                }

                QPushButton:checked {
                    background: #22d3ee;
                }
            """)

            self.status_label.setText("Veille désactivée")

    def start_veille(self):

        if not self.veille_active:
            return

        if self.wake_worker and self.wake_worker.isRunning():
            return

        if self.agent_worker and self.agent_worker.isRunning():
            return

        # Même garde qu'ailleurs : ne jamais tenir le micro pendant que
        # JIBI parle encore.
        if (self.voice_worker and self.voice_worker.isRunning()) or self.lecture_en_cours:
            return

        self.wake_worker = WakeWordWorker()
        self.wake_worker.level.connect(self.set_niveau_vocal)
        self.wake_worker.finished.connect(self.veille_finished)
        self.wake_worker.error.connect(self.veille_error)
        self.wake_worker.start()

    def veille_finished(self, texte, langue):
        if not texte:
            # Cycles de veille épuisés sans détection : on relance
            # simplement une nouvelle veille si toujours active.
            if self.veille_active:
                QTimer.singleShot(500, self.start_veille)
            return

        log_event("ui", f"Réveil détecté: {texte[:30]}...")

        self.add_message("Vous", texte)
        self.start_agent(texte)

    def veille_error(self, erreur):
        log_error("ui", f"Wake word error: {erreur}", exc_info=False)

        if self.veille_active:
            self.status_label.setText("Erreur veille — désactivée")
            self.veille_button.setChecked(False)

    # ========================================================
    # ECOUTE
    # ========================================================

    def start_listening(self):

        if self.listening_worker and self.listening_worker.isRunning():
            return

        if self.agent_worker and self.agent_worker.isRunning():
            self.status_label.setText("⏳ Patiente, je réponds déjà...")
            return

        # Même protection ici : évite de démarrer une écoute pendant
        # que JIBI est encore en train de générer/jouer sa réponse vocale
        # (sinon le VoiceWorker en cours serait écrasé silencieusement
        # au prochain start_agent, provoquant le même blocage).
        #
        # On vérifie aussi lecture_en_cours directement : le thread
        # voice_worker peut avoir fini de GÉNÉRER l'audio (isRunning()
        # devient False) alors que la DERNIÈRE phrase est encore en
        # train de JOUER via QMediaPlayer. Sans ce deuxième test, un
        # clic micro dans cette fenêtre lancerait l'écoute pendant que
        # JIBI parle encore, avec le risque qu'il s'entende lui-même.
        if (self.voice_worker and self.voice_worker.isRunning()) or self.lecture_en_cours:
            self.status_label.setText("⏳ Patiente, JIBI parle encore...")
            return

        # Une seule source ne peut tenir le micro à la fois : on coupe
        # la veille avant une écoute manuelle plutôt que de laisser les
        # deux sous-processus se disputer le périphérique audio.
        if self.wake_worker and self.wake_worker.isRunning():
            self.wake_worker.arreter()
            self.wake_worker.wait(2000)

        self.status_label.setText("🎤 J'écoute...")
        self.system_status.setText("● Écoute")
        self.system_status.setStyleSheet("color:#22d3ee;")

        self.mic_button.setEnabled(False)
        self.activer_visuel_vocal()

        self.listening_worker = ListeningWorker()
        self.listening_worker.level.connect(self.set_niveau_vocal)
        self.listening_worker.finished.connect(self.listening_finished)
        self.listening_worker.error.connect(self.listening_error)
        self.listening_worker.start()

    # ========================================================
    # FIN ECOUTE
    # ========================================================

    def listening_finished(self, texte, langue):
        log_event(
            "ui", f"Mic: {texte[:30] if texte else '(silence)'}... ({langue})"
        )

        self.desactiver_visuel_vocal()
        self.mic_button.setEnabled(True)

        if not texte:
            self.status_label.setText("Aucune parole")
            self.system_status.setText("● Prêt")
            self.system_status.setStyleSheet("color:#22c55e;")

            if self.mode_dialogue:
                QTimer.singleShot(600, self.start_listening)

            return

        self.add_message("Vous", texte)
        self.start_agent(texte)

    # ========================================================
    # FIN JIBI PARLE
    # ========================================================

    def voice_finished(self):
        if self.speaking_timer:
            self.speaking_timer.stop()

        self.desactiver_visuel_vocal()

        # Bug pré-existant : mic_button était désactivé dans start_agent
        # mais jamais réactivé ici. Ça n'était pas visible en mode
        # dialogue (le mic reste géré par listening_finished juste
        # après), mais bloquait le micro après une réponse à un
        # message tapé au clavier.
        self.mic_button.setEnabled(True)

        self.status_label.setText("Prêt à converser")
        self.system_status.setText("● Prêt")
        self.system_status.setStyleSheet("color:#22c55e;")

        if self.mode_dialogue:
            QTimer.singleShot(500, self.start_listening)
        elif self.veille_active:
            # Redonne le micro à la veille maintenant que JIBI a fini
            # de parler — c'est le pendant du arrêt fait dans start_agent.
            QTimer.singleShot(500, self.start_veille)

    # ========================================================
    # ERREUR MICRO
    # ========================================================

    def listening_error(self, erreur):
        log_error("ui", f"Microphone error: {erreur}", exc_info=False)

        self.desactiver_visuel_vocal()
        self.mic_button.setEnabled(True)

        self.status_label.setText("Erreur microphone")
        self.system_status.setText("● Erreur")
        self.system_status.setStyleSheet("color:#ef4444;")

        self.add_message("JIBI", f"Erreur microphone : {erreur}")

        if self.mode_dialogue:
            self.dialogue_button.setChecked(False)

    # ========================================================
    # ERREUR AGENT
    # ========================================================

    def agent_error(self, erreur):
        log_error("ui", f"Agent error: {erreur}", exc_info=False)

        self.input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.mic_button.setEnabled(True)

        self.streaming_message.setVisible(False)

        self.status_label.setText("Erreur JIBI")
        self.system_status.setText("● Erreur")
        self.system_status.setStyleSheet("color:#ef4444;")

        self.add_message("JIBI", f"Erreur : {erreur}")

    # ========================================================
    # ERREUR VOIX
    # ========================================================

    def voice_error(self, erreur):
        log_error("ui", f"Voice error: {erreur}", exc_info=False)

        if self.speaking_timer:
            self.speaking_timer.stop()

        self.desactiver_visuel_vocal()

        self.file_audio = []
        self.generation_vocale_finie = True
        self.lecture_en_cours = False

        # Bug : contrairement à agent_error, mic_button n'était jamais
        # réactivé ici. Si la synthèse vocale (Kokoro) échoue une seule
        # fois, le bouton micro restait désactivé pour toujours — un
        # clic dessus ne déclenche alors plus rien du tout (aucun
        # événement n'est émis par un bouton désactivé), symptôme
        # exact de "je clique et rien ne se passe".
        self.mic_button.setEnabled(True)

        self.status_label.setText("Réponse affichée")
        self.system_status.setText("● Prêt")
        self.system_status.setStyleSheet("color:#22c55e;")

    # ========================================================
    # NOUVELLE CONVERSATION
    # ========================================================

    def clear_chat(self):
        self.chat.clear()
        self.add_message("JIBI", "Nouvelle conversation démarrée 👋 C'est reparti !")


# ============================================================
# MAIN
# ============================================================

def main():
    app = QApplication(sys.argv)

    apply_stylesheet(app, theme="dark_cyan.xml")

    window = AgentWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()