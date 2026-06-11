import json
import random
import sys
import os
import websocket
import torch

from jassbot import JassBot, main_func
from transformerbot.model import JassTransformer

# translate cards to a unique index
def get_card_id(card):
    colors = ["SPADES", "HEARTS", "DIAMONDS", "CLUBS"]
    try:
        color_idx = colors.index(card["color"])
        return color_idx * 9 + (card["number"] - 6)
    except Exception:
        return 36 # Padding/Unknown

# translate jass modes to a unique index
def get_mode_id(mode, color):
    if mode == "OBEABE": return 0
    if mode == "UNDEUFE": return 1
    if mode == "SCHIEBE": return 2
    if mode == "TRUMPF":
        colors = ["SPADES", "HEARTS", "DIAMONDS", "CLUBS"]
        try:
            return 3 + colors.index(color)
        except Exception:
            return 3
    return 0

class TransformerBot(JassBot):
    def __init__(self, name="TransformerBot", team_index=1, session_name=None, session_type="TOURNAMENT"):
        super().__init__(name=name, team_index=team_index, session_name=session_name, session_type=session_type)
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[{self.name}] Initializing JassTransformer on {self.device}...")
        self.model = JassTransformer().to(self.device)
        
        # Try to load weights if they exist
        weights_path = os.path.join(os.path.dirname(__file__), "jass_transformer.pt")
        self.model.load_weights(weights_path)
        self.model.eval()

    # choose trumpf (random for now)
    def choose_trumpf(self):
        modes = ["OBEABE", "UNDEUFE", "TRUMPF", "SCHIEBE"]
        chosen_mode = random.choice(modes)
        color = None
        if chosen_mode == "TRUMPF":
            color = random.choice(["CLUBS", "DIAMONDS", "HEARTS", "SPADES"])
        return chosen_mode, color


    def choose_card(self, cards_on_table, valid_cards, available_cards):
        if not valid_cards:
            if available_cards:
                return random.choice(available_cards)
            elif self.hand_cards:
                return random.choice(self.hand_cards)
            else:
                return {"number": 14, "color": "DIAMONDS"}


        print(f"[{self.name}] Choosing card. Table: {cards_on_table}, Valid: {valid_cards} (from {self.hand_cards})")

        # Construct sequence
        cards_seq = []
        players_seq = []
        tricks_seq = []
        turns_seq = []
        
        # historical tricks
        for trick_idx, trick_cards in enumerate(self.played_cards_history):
            for turn_idx, card in enumerate(trick_cards):
                cards_seq.append(get_card_id(card))
                players_seq.append(0) # Player ID not fully tracked in base JassBot
                tricks_seq.append(trick_idx)
                turns_seq.append(turn_idx)
        
        # current trick
        trick_idx = len(self.played_cards_history)
        for turn_idx, card in enumerate(cards_on_table):
            cards_seq.append(get_card_id(card))
            players_seq.append(0)
            tricks_seq.append(trick_idx)
            turns_seq.append(turn_idx)
            
        # Add a dummy token for the CURRENT action we have to take
        cards_seq.append(37) # 37 is hidden
        players_seq.append(0)
        tricks_seq.append(trick_idx)
        turns_seq.append(len(cards_on_table))

        # Convert to tensors
        cards_t = torch.tensor([cards_seq], dtype=torch.long).to(self.device)
        players_t = torch.tensor([players_seq], dtype=torch.long).to(self.device)
        tricks_t = torch.tensor([tricks_seq], dtype=torch.long).to(self.device)
        turns_t = torch.tensor([turns_seq], dtype=torch.long).to(self.device)
        
        mode_id = get_mode_id(self.mode, self.trump_color)
        modes_t = torch.tensor([[mode_id] * len(cards_seq)], dtype=torch.long).to(self.device)
        
        # Legal mask
        legal_mask = torch.zeros((1, 36), dtype=torch.float32).to(self.device)
        for c in valid_cards:
            cid = get_card_id(c)
            if cid < 36:
                legal_mask[0, cid] = 1.0
                
        # Forward pass
        with torch.no_grad():
            logits, value = self.model(cards_t, players_t, tricks_t, turns_t, modes_t, legal_mask)
            
        # Select best valid action
        best_card_id = torch.argmax(logits[0]).item()
        
        # Find the card in valid_cards
        for c in valid_cards:
            if get_card_id(c) == best_card_id:
                return c


        print(f"[{self.name}] Fallback to random choice from valid cards: {valid_cards}")

        # Fallback if something goes wrong
        return random.choice(valid_cards)


if __name__ == "__main__":
    main_func(TransformerBot)
