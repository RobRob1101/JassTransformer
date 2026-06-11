import os
from google import genai
from jassbot import JassBot, main_func
from dotenv import load_dotenv

from pydantic import BaseModel

try:
    from transformerbot1.prompt import rules_prompt, trumpf_prompt
except ImportError:
    from prompt import rules_prompt, trumpf_prompt


# Load variables from .env file at startup
load_dotenv()


COLOR_TO_CHAR = {
    "DIAMONDS": "D",
    "HEARTS": "H",
    "SPADES": "S",
    "CLUBS": "C"
}
CHAR_TO_COLOR = {v: k for k, v in COLOR_TO_CHAR.items()}

NUMBER_TO_CHAR = {
    14: "A",
    13: "K",
    12: "Q",
    11: "J",
    10: "10",
    9: "9",
    8: "8",
    7: "7",
    6: "6"
}
CHAR_TO_NUMBER = {v: k for k, v in NUMBER_TO_CHAR.items()}

# Helper functions for formatting cards
def format_card(card):
    if not card:
        return "None"
    color_char = COLOR_TO_CHAR.get(card.get("color"))
    number_char = NUMBER_TO_CHAR.get(card.get("number"))
    if color_char and number_char:
        return f"{color_char}{number_char}"
    return "None"

def format_cards_list(cards):
    if not cards:
        return "None"
    return ", ".join(format_card(c) for c in cards)

def string_to_card(card_str):
    if not card_str:
        return None
    card_str = card_str.strip().upper()
    if len(card_str) < 2:
        return None
    color_char = card_str[0]
    number_char = card_str[1:]
    color = CHAR_TO_COLOR.get(color_char)
    number = CHAR_TO_NUMBER.get(number_char)
    if color and number is not None:
        return {"color": color, "number": number}
    return None

def format_trump_suit(mode, trump_color):
    if mode == "OBEABE":
        return "4 (Top-Down, Obe-Abe)"
    elif mode == "UNDEUFE":
        return "5 (Bottom-Up, Une-Ufe)"
    elif mode == "TRUMPF":
        color_char_map = {
            "DIAMONDS": "0 (Diamonds)",
            "HEARTS": "1 (Hearts)",
            "SPADES": "2 (Spades)",
            "CLUBS": "3 (Clubs)"
        }
        return color_char_map.get(trump_color, "Unknown")
    return "Unknown"

# Pydantic schemas for structured outputs (omitting reasoning to save tokens)
class TrumpfChoice(BaseModel):
    trump: int  # 0, 1, 2, 3, 4, 5, 10

class CardChoice(BaseModel):
    card: str  # e.g., "SA", "H10", etc.

class TransformerBot(JassBot):
    def __init__(self, name="TransformerBot", team_index=1, session_name=None, session_type="TOURNAMENT"):
        super().__init__(name=name, team_index=team_index, session_name=session_name, session_type=session_type)
        
        # Configure Gemini client
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print(f"[{self.name}] WARNING: GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set.")
            
        # Load a pretrained Gemini Flash model (defaulting to gemini-1.5-flash)
        self.model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        print(f"[{self.name}] Loading pretrained Gemini model: {self.model_name}...")
        self.client = genai.Client(api_key=api_key) if api_key else genai.Client()


    def choose_trumpf(self):
        prompt = trumpf_prompt.format(
            AVAILABLE_CARDS=format_cards_list(self.hand_cards)
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": TrumpfChoice,
                }
            )
            choice = response.parsed
            print(f"[{self.name}] LLM Decision for Trumpf: {choice.trump}")
            
            # Map PDF encoding to websocket mode/color
            TRUMPF_MAP = {
                0: ("TRUMPF", "DIAMONDS"),
                1: ("TRUMPF", "HEARTS"),
                2: ("TRUMPF", "SPADES"),
                3: ("TRUMPF", "CLUBS"),
                4: ("OBEABE", None),
                5: ("UNDEUFE", None),
                10: ("SCHIEBE", None)
            }
            mode, color = TRUMPF_MAP.get(choice.trump, ("SCHIEBE", None))
            return mode, color
        except Exception as e:
            print(f"[{self.name}] Error in LLM choose_trumpf: {e}. Falling back to rule-based choice.")
            # Simple fallback
            suits = {"CLUBS": 0, "DIAMONDS": 0, "HEARTS": 0, "SPADES": 0}
            for c in self.hand_cards:
                suits[c["color"]] = suits.get(c["color"], 0) + 1
            best_suit = max(suits.items(), key=lambda x: x[1])[0]
            if suits[best_suit] >= 4:
                return "TRUMPF", best_suit
            return "SCHIEBE", None

    def choose_card(self, cards_on_table, valid_cards, available_cards):
        if not valid_cards:
            valid_cards = available_cards if available_cards else self.hand_cards
            if not valid_cards:
                return {"number": 14, "color": "DIAMONDS"}

        # Format placeholders for rules_prompt
        trump_suit_str = format_trump_suit(self.mode, self.trump_color)
        
        cards_on_table_str = format_cards_list(cards_on_table)
        valid_cards_str = format_cards_list(valid_cards)
        available_cards_str = format_cards_list(available_cards)
        
        prompt = rules_prompt.format(
            TRUMP_SUIT=trump_suit_str,
            CARDS_ON_TABLE=cards_on_table_str,
            VALID_CARDS=valid_cards_str,
            AVAILABLE_CARDS=available_cards_str
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": CardChoice,
                }
            )
            choice = response.parsed
            print(f"[{self.name}] LLM Decision for Card: {choice.card}")
            
            # Parse the selection back to a card dictionary
            chosen_card = string_to_card(choice.card)
            if chosen_card:
                for c in valid_cards:
                    if c.get("color") == chosen_card["color"] and c.get("number") == chosen_card["number"]:
                        return c
            
            # Fallback if parsing failed or selected card is invalid
            print(f"[{self.name}] LLM chose '{choice.card}' which is not a valid move. Falling back to first valid card.")
            return valid_cards[0]
        except Exception as e:
            print(f"[{self.name}] Error in LLM choose_card: {e}. Falling back to first valid card.")
            return valid_cards[0]

if __name__ == "__main__":
    main_func(TransformerBot)



        