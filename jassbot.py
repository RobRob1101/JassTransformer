import json
import random
import sys
import websocket

class JassBot:
    def __init__(self, name="PythonJassBot", team_index=1, session_name=None, session_type="TOURNAMENT"):
        self.name = name
        self.team_index = team_index
        self.session_name = session_name
        self.session_type = session_type
        self.hand_cards = []
        self.rejected_cards_this_turn = []
        self.last_cards_on_table = None
        self.mode = "TRUMPF"
        self.trump_color = "SPADES"

    def is_valid_card(self, card, hand_cards, table_cards, mode, color):
        if not table_cards:
            return True
            
        lead_card = table_cards[0]
        lead_color = lead_card.get("color")
        card_color = card.get("color")
        
        has_lead_color = any(c.get("color") == lead_color for c in hand_cards)
        
        if has_lead_color:
            is_only_buur = False # the trumpf color is out, and you only have the buur. Then all other cards are permitted
            if mode == "TRUMPF" and lead_color == color:
                trump_cards = [c for c in hand_cards if c.get("color") == color]
                if len(trump_cards) == 1 and trump_cards[0].get("number") == 11:
                    is_only_buur = True
                    
            is_permitted = (card_color == lead_color) or (mode == "TRUMPF" and card_color == color) or is_only_buur
            if not is_permitted:
                return False
                
        if mode == "TRUMPF" and card_color == color:
            if lead_color != color:
                has_other_than_trump = any(c.get("color") != color for c in hand_cards)
                if has_other_than_trump:
                    trump_order = [6, 7, 8, 10, 12, 13, 14, 9, 11]
                    card_trump_index = trump_order.index(card.get("number"))
                    
                    highest_trump_on_table_val = -1
                    for tc in table_cards:
                        if tc.get("color") == color:
                            highest_trump_on_table_val = max(highest_trump_on_table_val, trump_order.index(tc.get("number")))
                    
                    if card_trump_index < highest_trump_on_table_val:
                        return False
                        
        return True

    def get_valid_cards(self, cards_on_table):
        # Filter out any cards that have been rejected during this turn
        available_cards = [c for c in self.hand_cards if not any(rc["number"] == c["number"] and rc["color"] == c["color"] for rc in self.rejected_cards_this_turn)]

        # Filter to find only locally valid cards
        valid_cards = [c for c in available_cards if self.is_valid_card(c, self.hand_cards, cards_on_table, self.mode, self.trump_color)]
        return valid_cards, available_cards

    def choose_trumpf(self):
        raise NotImplementedError("Subclasses must implement choose_trumpf")

    def choose_card(self, cards_on_table, valid_cards, available_cards):
        raise NotImplementedError("Subclasses must implement choose_card")

    def on_message(self, ws, message_str):
        print(f"[{self.name}] Received: {message_str}")
        try:
            message = json.loads(message_str)
        except Exception as e:
            print(f"[{self.name}] Error parsing JSON: {e}")
            return

        msg_type = message.get("type")
        data = message.get("data")

        if msg_type == "REQUEST_PLAYER_NAME":
            ws.send(json.dumps({
                "type": "CHOOSE_PLAYER_NAME",
                "data": self.name
            }))
            print(f"[{self.name}] Sent player name: {self.name}")

        elif msg_type == "REQUEST_SESSION_CHOICE":
            if self.session_name:
                ws.send(json.dumps({
                    "type": "CHOOSE_SESSION",
                    "data": {
                        "sessionChoice": "JOIN_EXISTING",
                        "sessionName": self.session_name,
                        "sessionType": self.session_type,
                        "asSpectator": False,
                        "advisedPlayerName": None,
                        "chosenTeamIndex": self.team_index
                    }
                }))
                print(f"[{self.name}] Sent session choice: JOIN_EXISTING for session {self.session_name}")
            else:
                ws.send(json.dumps({
                    "type": "CHOOSE_SESSION",
                    "data": {
                        "sessionChoice": "AUTOJOIN",
                        "sessionName": "Java Client Session",
                        "sessionType": self.session_type,
                        "asSpectator": False,
                        "advisedPlayerName": None,
                        "chosenTeamIndex": self.team_index
                    }
                }))
                print(f"[{self.name}] Sent session choice: AUTOJOIN for team {self.team_index}")

        elif msg_type == "DEAL_CARDS":
            self.hand_cards = data
            cards_str = [f"{c.get('color')}_{c.get('number')}" for c in self.hand_cards]
            print(f"[{self.name}] Dealt cards: {cards_str}")

        elif msg_type == "REQUEST_TRUMPF":
            chosen_mode, color = self.choose_trumpf()
            ws.send(json.dumps({
                "type": "CHOOSE_TRUMPF",
                "data": {
                    "mode": chosen_mode,
                    "trumpfColor": color
                }
            }))
            print(f"[{self.name}] Chose Trumpf: {chosen_mode} (Color: {color})")

        elif msg_type == "BROADCAST_TRUMPF":
            if data and data.get("mode") != "SCHIEBE":
                self.mode = data.get("mode")
                self.trump_color = data.get("trumpfColor")
                print(f"[{self.name}] Game mode set to {self.mode} (Trump color: {self.trump_color})")

        elif msg_type == "REQUEST_CARD":
            cards_on_table = data
            if cards_on_table != self.last_cards_on_table:
                self.rejected_cards_this_turn = []
                self.last_cards_on_table = cards_on_table

            valid_cards, available_cards = self.get_valid_cards(cards_on_table)
            card = self.choose_card(cards_on_table, valid_cards, available_cards)
            
            ws.send(json.dumps({
                "type": "CHOOSE_CARD",
                "data": card
            }))
            print(f"[{self.name}] Chose card: {card.get('color')}_{card.get('number')}")

        elif msg_type == "REJECT_CARD":
            rejected_card = data
            self.rejected_cards_this_turn.append(rejected_card)
            cards_str = [f"{c.get('color')}_{c.get('number')}" for c in self.hand_cards]
            print(f"[{self.name}] Card rejected! Hand: {cards_str}")

        elif msg_type == "BROADCAST_STICH":
            stich_data = data
            played_cards = stich_data.get("playedCards", [])
            for pc in played_cards:
                self.hand_cards = [c for c in self.hand_cards if not (c["number"] == pc["number"] and c["color"] == pc["color"])]
            cards_str = [f"{c.get('color')}_{c.get('number')}" for c in self.hand_cards]
            print(f"[{self.name}] Trick completed. Remaining hand: {cards_str}")

    def on_error(self, ws, error):
        import traceback
        traceback.print_exc()
        print(f"[{self.name}] Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[{self.name}] Connection closed")

    def on_open(self, ws):
        print(f"[{self.name}] Connected to jass-server")




def main_func(Bot):
    import argparse
    parser = argparse.ArgumentParser(description="Random Jass Bot in Python")
    parser.add_argument("--url", default="ws://localhost:3000", help="WebSocket URL of jass-server")
    parser.add_argument("--name", default="PythonRandomBot", help="Name of the bot")
    parser.add_argument("--team", type=int, default=1, help="Team index (0 or 1)")
    parser.add_argument("--session", default=None, help="Session name to join")
    parser.add_argument("--session-type", default="TOURNAMENT", help="Session type (TOURNAMENT or SINGLE_GAME)")
    args = parser.parse_args()

    bot = Bot(name=args.name, team_index=args.team, session_name=args.session, session_type=args.session_type)
    
    # Create the websocket, with the behaviour on open, receiving messages, etc.
    ws = websocket.WebSocketApp(
        args.url,
        on_open=bot.on_open,
        on_message=bot.on_message,
        on_error=bot.on_error,
        on_close=bot.on_close
    )
    ws.run_forever()