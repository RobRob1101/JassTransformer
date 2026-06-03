import json
import random
import sys
import os
import websocket

from jassbot import JassBot, main_func

class RandomBot(JassBot):
    def __init__(self, name="PythonRandomBot", team_index=1, session_name=None, session_type="TOURNAMENT"):
        super().__init__(name=name, team_index=team_index, session_name=session_name, session_type=session_type)

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
                # Fallback card in case we have no card info
                return {"number": 14, "color": "DIAMONDS"}
        else:
            return random.choice(valid_cards)


if __name__ == "__main__":
    main_func(RandomBot)





