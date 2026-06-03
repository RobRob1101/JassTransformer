import os
import google.generativeai as genai
from jassbot import JassBot, main_func
from dotenv import load_dotenv

# Load variables from .env file at startup
load_dotenv()

class TransformerBot(JassBot):
    def __init__(self, name="TransformerBot", team_index=1, session_name=None, session_type="TOURNAMENT"):
        super().__init__(name=name, team_index=team_index, session_name=session_name, session_type=session_type)
        
        # Configure Gemini API key
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        else:
            print(f"[{self.name}] WARNING: GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set.")
            
        # Load a pretrained Gemini Flash model (defaulting to gemini-1.5-flash)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        print(f"[{self.name}] Loading pretrained Gemini model: {model_name}...")
        self.model = genai.GenerativeModel(model_name)

    def choose_trumpf(self):
        # Stub for now
        pass

    def choose_card(self, cards_on_table, valid_cards, available_cards):
        # Stub for now
        pass

if __name__ == "__main__":
    main_func(TransformerBot)



        