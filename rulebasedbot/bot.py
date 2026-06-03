import sys
import os
import random

from jassbot import JassBot, main_func

class RuleBasedBot(JassBot):
    def __init__(self, name="RuleBasedBot", team_index=1, session_name=None, session_type="TOURNAMENT"):
        super().__init__(name=name, team_index=team_index, session_name=session_name, session_type=session_type)

    def _get_card_value(self, card, mode, trump_color):
        number = card["number"]
        color = card["color"]
        
        if mode == "TRUMPF" and color == trump_color:
            if number == 11: return 20 # Jack/Bauer
            if number == 9: return 14 # Nell
            if number == 14: return 11 # Ace
            if number == 10: return 10
            if number == 13: return 4 # King
            if number == 12: return 3 # Queen
            return 0
        else: # OBEABE or non-trump suit
            if number == 14: return 11 # Ace
            if number == 10: return 10
            if number == 13: return 4 # King
            if number == 12: return 3 # Queen
            if number == 11: return 2 # Jack
            return 0

    def _get_trick_winner_index(self, table_cards, mode, trump_color):
        if not table_cards: return -1
        
        lead_color = table_cards[0]["color"]
        winner_idx = 0
        highest_val = -1
        
        trump_order = [6, 7, 8, 10, 12, 13, 14, 9, 11]
        obeabe_order = [6, 7, 8, 9, 10, 11, 12, 13, 14]
        undeufe_order = [14, 13, 12, 11, 10, 9, 8, 7, 6]

        for i, card in enumerate(table_cards):
            color = card["color"]
            num = card["number"]
            
            val = -1
            if mode == "TRUMPF":
                if color == trump_color:
                    val = 100 + trump_order.index(num)
                elif color == lead_color:
                    val = obeabe_order.index(num)
            elif mode == "OBEABE":
                if color == lead_color:
                    val = obeabe_order.index(num)
            elif mode == "UNDEUFE":
                if color == lead_color:
                    val = undeufe_order.index(num)
                    
            if val > highest_val:
                highest_val = val
                winner_idx = i
                
        return winner_idx

    def choose_trumpf(self):
        suits = {"CLUBS": [], "DIAMONDS": [], "HEARTS": [], "SPADES": []}
        for c in self.hand_cards:
            suits[c["color"]].append(c["number"])
            
        # Check for Bauer (11) + Nell (9) or Bauer + 3 others
        best_suit = None
        max_strength = -1
        
        for suit, cards in suits.items():
            strength = 0
            has_bauer = 11 in cards
            has_nell = 9 in cards
            
            if has_bauer and has_nell:
                strength += 50
            elif has_bauer and len(cards) >= 4:
                strength += 40
            
            strength += len(cards) * 10 # Base strength on length
            
            if strength > max_strength:
                max_strength = strength
                best_suit = suit
                
        # If hand is generally strong with Aces/Kings, maybe OBEABE
        high_cards = sum(1 for c in self.hand_cards if c["number"] in [13, 14])
        if high_cards >= 4 and max_strength < 40:
            return "OBEABE", None
            
        if max_strength < 30:
            return "SCHIEBE", None
            
        return "TRUMPF", best_suit

    def choose_card(self, cards_on_table, valid_cards, available_cards):
        if not valid_cards:
            valid_cards = available_cards if available_cards else self.hand_cards
            if not valid_cards:
                return {"number": 14, "color": "DIAMONDS"}

        # If we are leading
        if not cards_on_table:
            # Try to lead an Ace of a non-trump suit (if TRUMPF mode)
            if self.mode == "TRUMPF":
                non_trump_aces = [c for c in valid_cards if c["number"] == 14 and c["color"] != self.trump_color]
                if non_trump_aces:
                    return non_trump_aces[0]
            
            # Otherwise, play a card from our longest non-trump suit
            suits = {}
            for c in valid_cards:
                if self.mode == "TRUMPF" and c["color"] == self.trump_color:
                    continue
                suits[c["color"]] = suits.get(c["color"], 0) + 1
            
            if suits:
                longest_suit = max(suits.items(), key=lambda x: x[1])[0]
                suit_cards = [c for c in valid_cards if c["color"] == longest_suit]
                # Play the highest card from the longest suit
                return max(suit_cards, key=lambda c: c["number"])
            
            # Fallback: play randomly
            return random.choice(valid_cards)
            
        # If we are following
        winner_idx = self._get_trick_winner_index(cards_on_table, self.mode, self.trump_color)
        
        # In a 4-player game, if it's our turn, we are index len(cards_on_table).
        # Our partner played at index len(cards_on_table) - 2
        partner_idx = len(cards_on_table) - 2
        is_partner_winning = (winner_idx == partner_idx)
        
        # Sort valid cards by point value (ascending)
        valid_cards_sorted = sorted(valid_cards, key=lambda c: self._get_card_value(c, self.mode, self.trump_color))
        
        if is_partner_winning:
            # Schmier (give points) if safe
            # For simplicity, just play a high point card if we have one, else throw low
            return valid_cards_sorted[-1]
        else:
            # Opponent is winning, try to win the trick
            # Find cards that can beat the current winner
            winning_cards = []
            current_winner_card = cards_on_table[winner_idx]
            # Dummy logic to see if we can win: test playing each card and check if we become the winner
            for c in valid_cards:
                test_table = cards_on_table + [c]
                if self._get_trick_winner_index(test_table, self.mode, self.trump_color) == len(cards_on_table):
                    winning_cards.append(c)
                    
            if winning_cards:
                # Play the lowest value card that still wins the trick
                winning_cards_sorted = sorted(winning_cards, key=lambda c: self._get_card_value(c, self.mode, self.trump_color))
                return winning_cards_sorted[0]
            else:
                # Throw the lowest value card (trash)
                return valid_cards_sorted[0]

if __name__ == "__main__":
    main_func(RuleBasedBot)


