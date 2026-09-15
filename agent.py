"""
AGENT.PY — Point d'entrée principal de JIBI (compatible AgentCore v3.1)

- GUI dans le thread principal
- Appels agent non bloquants gérés par la GUI (thread)
- Boucle background optionnelle (auto-analyse) dans un thread séparé
"""

import os
import sys
import threading
import argparse
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

PROJET_DIR = Path(__file__).resolve().parent
os.environ["JIBI_PROJET_DIR"] = str(PROJET_DIR)

if str(PROJET_DIR) not in sys.path:
    sys.path.insert(0, str(PROJET_DIR))

# ---------------- Imports ----------------
try:
    from core.agent_core import AgentCore
    AGENT_CORE_DISPONIBLE = True
except Exception as e:
    AGENT_CORE_DISPONIBLE = False
    print(f"⚠️ AgentCore indisponible : {e}")

    class AgentCore:
        def __init__(self, config=None):
            self.config = config or {}
        def traiter_message(self, message, context=None):
            return {"texte": f"Echo: {message}", "confidence": 0.5}

try:
    from gui import JibiGUI
    GUI_DISPONIBLE = True
except Exception as e:
    GUI_DISPONIBLE = False
    print(f"⚠️ GUI indisponible : {e}")

try:
    from self_improvement.gestionnaire import analyser_jibi
    AUTO_AMELIORATION_DISPONIBLE = True
except Exception:
    AUTO_AMELIORATION_DISPONIBLE = False
    def analyser_jibi(**kwargs):
        return {"score_sante": 100, "niveau_sante": "Excellent", "nombre_erreurs": 0}


class JibiApplication:
    def __init__(self, mode: str = "gui", theme: str = "moderne"):
        self.mode = mode
        self.theme = theme

        self.agent: Optional[AgentCore] = None
        self.gui: Optional[JibiGUI] = None

        self.running = False
        self.agent_thread: Optional[threading.Thread] = None

        print("\n" + "=" * 70)
        print("🤖 JIBI — Assistant IA")
        print("=" * 70)
        print(f"📁 Répertoire projet : {PROJET_DIR}")
        print(f"🎯 Mode : {mode}")
        print(f"🎨 Thème : {theme}")
        print("=" * 70 + "\n")

    def initialiser_agent(self) -> bool:
        if not AGENT_CORE_DISPONIBLE:
            print("❌ AgentCore non disponible")
            return False
        try:
            print("🔧 Initialisation AgentCore...")
            # Config simple (dict) : AgentCore v3.1 l'accepte
            config = {
                "auto_analysis_active": True,
                "auto_preparation_active": True,
                "auto_application_blockee": True,
            }
            self.agent = AgentCore(config=config)
            print("✅ AgentCore initialisé")
            return True
        except Exception as e:
            print(f"❌ Erreur init agent : {e}")
            return False

    def initialiser_gui(self) -> bool:
        if not GUI_DISPONIBLE:
            print("❌ GUI non disponible")
            return False
        try:
            print("🎨 Initialisation GUI...")
            # FIX (incompatibilité) : gui.py gère son propre AgentCore en
            # interne (thread de fond, file de réponses, annulation...) et
            # n'a jamais lu les attributs agent_traiter_message /
            # agent_analyser_sante — ce câblage ne faisait donc rien, et
            # l'agent initialisé ci-dessus (avec sa config) restait orphelin
            # pendant qu'une SECONDE instance d'AgentCore était créée en
            # silence dans la GUI. On injecte directement l'agent déjà
            # initialisé pour qu'il n'y en ait qu'un seul.
            self.gui = JibiGUI(
                agent=self.agent,
                theme_name=self.theme,
                titre="🤖 JIBI — Assistant IA",
                geometry="1200x760"
            )
            print("✅ GUI initialisée")
            return True
        except Exception as e:
            print(f"❌ Erreur init GUI : {e}")
            return False

    def envoyer_message_agent(self, message: str, context: dict = None) -> dict:
        if not self.agent:
            return {"texte": "Agent non disponible", "confidence": 0.0, "erreur": True}
        try:
            rep = self.agent.traiter_message(message, context)
            return rep.to_dict() if hasattr(rep, "to_dict") else rep
        except Exception as e:
            return {"texte": f"Erreur agent : {e}", "confidence": 0.0, "erreur": True}

    def agent_analyser_sante(self) -> dict:
        if AUTO_AMELIORATION_DISPONIBLE:
            return analyser_jibi(depuis_heures=24)
        return {"score_sante": 95, "niveau_sante": "Excellent", "message": "Analyse indisponible"}

    def lancer_mode_gui(self):
        print("\n🚀 Lancement GUI...\n")

        # 1) agent
        self.initialiser_agent()

        # 2) GUI
        if not self.initialiser_gui():
            print("❌ Impossible de lancer la GUI")
            return

        # 3) maintenant seulement : running + thread background
        self.running = True
        self.agent_thread = threading.Thread(
            target=self._agent_background_loop,
            daemon=True,
            name="AgentBackground"
        )
        self.agent_thread.start()

        print("✅ JIBI prêt.")
        self.gui.lancer()

    def _agent_background_loop(self):
        """Auto-analyse périodique (optionnel)."""
        derniere_analyse = time.time()
        intervalle_analyse = 1800  # 30 min

        while self.running:
            try:
                if AUTO_AMELIORATION_DISPONIBLE and (time.time() - derniere_analyse > intervalle_analyse):
                    print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] Auto-analyse...")
                    resultat = analyser_jibi(depuis_heures=1)
                    score = resultat.get("score_sante", 100)
                    print(f"   Score santé : {score}/100")
                    derniere_analyse = time.time()
                time.sleep(10)
            except Exception as e:
                print(f"⚠️ Boucle background : {e}")
                time.sleep(30)

    def lancer_mode_cli(self):
        print("\n🚀 Mode CLI...\n")
        if not self.initialiser_agent():
            return
        self.running = True
        while self.running:
            try:
                user_input = input("\n🤖 JIBI > ").strip()
                if user_input.lower() in ("exit", "quit", "q"):
                    self.running = False
                    break
                rep = self.agent.traiter_message(user_input)
                # CORRIGÉ : le AgentCore de repli (quand core.agent_core est
                # indisponible) renvoie un dict, pas un objet avec .texte —
                # sans ce garde-fou on affichait le dict brut au lieu du texte.
                if hasattr(rep, "texte"):
                    txt = rep.texte
                elif isinstance(rep, dict):
                    txt = rep.get("texte", str(rep))
                else:
                    txt = str(rep)
                print("\n" + txt)
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print("❌", e)

    def lancer_mode_agent_seul(self):
        print("\n🚀 Mode Agent seul...\n")
        if not self.initialiser_agent():
            return
        self.running = True
        self._agent_background_loop()

    def arreter(self):
        self.running = False
        if self.agent_thread and self.agent_thread.is_alive():
            self.agent_thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description="JIBI")
    parser.add_argument("--cli", action="store_true")
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--theme", type=str, default="moderne", choices=["moderne", "clair"])
    args = parser.parse_args()

    if args.no_gui:
        mode = "agent_seul"
    elif args.cli:
        mode = "cli"
    else:
        mode = "gui"

    app = JibiApplication(mode=mode, theme=args.theme)
    try:
        if mode == "gui":
            app.lancer_mode_gui()
        elif mode == "cli":
            app.lancer_mode_cli()
        else:
            app.lancer_mode_agent_seul()
    finally:
        app.arreter()


if __name__ == "__main__":
    main()