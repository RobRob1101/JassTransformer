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
        self.trick_scores = []
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[{self.name}] Initializing JassTransformer on {self.device}...")
        self.model = JassTransformer().to(self.device)
        
        # Try to load weights if they exist
        weights_path = os.path.join(os.path.dirname(__file__), "jass_transformer.pt")
        self.model.load_weights(weights_path)
        self.model.eval()

    def _get_card_value(self, card):
        num = card["number"]
        color = card["color"]
        if self.mode == "OBEABE":
            vals = {8:8, 14:11, 10:10, 13:4, 12:3, 11:2}
            return vals.get(num, 0)
        elif self.mode == "UNDEUFE":
            vals = {8:8, 6:11, 10:10, 13:4, 12:3, 11:2}
            return vals.get(num, 0)
        elif self.mode == "TRUMPF":
            if color == self.trump_color:
                vals = {11:20, 9:14, 14:11, 10:10, 13:4, 12:3}
                return vals.get(num, 0)
            else:
                vals = {14:11, 10:10, 13:4, 12:3, 11:2}
                return vals.get(num, 0)
        return 0

    def on_message(self, ws, message_str):
        try:
            message = json.loads(message_str)
            msg_type = message.get("type")
            data = message.get("data")
        except Exception:
            super().on_message(ws, message_str)
            return

        if msg_type == "DEAL_CARDS":
            self.trick_scores = []
            
        super().on_message(ws, message_str)
        
        if msg_type == "BROADCAST_STICH":
            winner_seat = data.get("seatId")
            played_cards = data.get("playedCards", [])
            
            # Compute trick points
            trick_points = sum(self._get_card_value(pc) for pc in played_cards)
            if len(self.played_cards_history) == 9:
                trick_points += 5
                
            # Which team won the trick?
            winner_team = winner_seat % 2
            
            # Store the trick score: [team_0_points, team_1_points]
            score_entry = [0, 0]
            score_entry[winner_team] = trick_points
            self.trick_scores.append(score_entry)

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
        scores_seq = []

        # Prepend hand cards
        for card in self.hand_cards:
            cards_seq.append(get_card_id(card))
            players_seq.append(0) # relative player id for self is always 0
            tricks_seq.append(9)  # Special trick index 9 for hand cards
            turns_seq.append(4)   # Special turn index 4 for hand cards
            scores_seq.append(0)
        
        # historical tricks
        for trick_idx, trick_cards in enumerate(self.played_cards_history):
            for turn_idx, card_info in enumerate(trick_cards):
                card, player = card_info
                cards_seq.append(get_card_id(card))
                players_seq.append(player) # Player ID not fully tracked in base JassBot
                tricks_seq.append(trick_idx)
                turns_seq.append(turn_idx)
                scores_seq.append(0)
            
            # Add trick completion token
            cards_seq.append(37)
            players_seq.append(0)
            tricks_seq.append(trick_idx)
            turns_seq.append(4)
            my_team = self.team_index
            opp_team = 1 - my_team
            if trick_idx < len(self.trick_scores):
                score_diff = self.trick_scores[trick_idx][my_team] - self.trick_scores[trick_idx][opp_team]
            else:
                score_diff = 0
            scores_seq.append(score_diff)
        
        # current trick
        trick_idx = len(self.played_cards_history)
        for turn_idx, card in enumerate(cards_on_table):
            cards_seq.append(get_card_id(card))
            rel_player = (turn_idx - len(cards_on_table)) % 4
            players_seq.append(rel_player)
            tricks_seq.append(trick_idx)
            turns_seq.append(turn_idx)
            scores_seq.append(0)
            
        # Add a dummy token for the CURRENT action we have to take
        cards_seq.append(37) # 37 is hidden
        players_seq.append(0) # Bot is always 0
        tricks_seq.append(trick_idx)
        turns_seq.append(len(cards_on_table))
        scores_seq.append(0)

        # Convert to tensors
        cards_t = torch.tensor([cards_seq], dtype=torch.long).to(self.device)
        players_t = torch.tensor([players_seq], dtype=torch.long).to(self.device)
        tricks_t = torch.tensor([tricks_seq], dtype=torch.long).to(self.device)
        turns_t = torch.tensor([turns_seq], dtype=torch.long).to(self.device)
        scores_t = torch.tensor([scores_seq], dtype=torch.long).to(self.device)
        
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
            logits, value = self.model(cards_t, players_t, tricks_t, turns_t, modes_t, scores_t, legal_mask)
            
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
