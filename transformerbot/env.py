import random
import torch

class JassEnv:
    def __init__(self):
        self.num_players = 4
        self.cards_per_player = 9
        self.reset()
        
    def reset(self):
        # Modes: 0:OBEABE, 1:UNDEUFE, 2:SCHIEBE (skip), 3:SPADES, 4:HEARTS, 5:DIAMONDS, 6:CLUBS
        self.mode = random.choice([0, 1, 3, 4, 5, 6])
        self.trump_color = self.mode - 3 if self.mode >= 3 else None
        
        deck = list(range(36))
        random.shuffle(deck)
        
        self.hands = [deck[i*9:(i+1)*9] for i in range(4)]
        self.current_player = random.randint(0, 3) # Who starts the first trick
        
        self.played_cards_history = [] # list of list of tuples (card, player_id)
        self.current_trick = []
        self.trick_scores = [] 
        self.scores = [0, 0] # Team 0 (players 0,2), Team 1 (players 1,3)
        self.tricks_played = 0
        self.done = False
        
        return self.get_state(self.current_player)
        
    def _card_color(self, card_id):
        return card_id // 9
        
    def _card_number(self, card_id):
        return (card_id % 9) + 6

    def get_legal_actions(self, player_id):
        hand = self.hands[player_id]
        if not self.current_trick:
            return list(hand)
            
        lead_card, _ = self.current_trick[0]
        lead_color = self._card_color(lead_card)
        
        legal = []
        has_lead_color = any(self._card_color(c) == lead_color for c in hand)
        
        for c in hand:
            c_color = self._card_color(c)
            c_num = self._card_number(c)
            
            if has_lead_color:
                is_only_buur = False
                if self.mode >= 3 and lead_color == self.trump_color:
                    trump_cards = [tc for tc in hand if self._card_color(tc) == self.trump_color]
                    if len(trump_cards) == 1 and self._card_number(trump_cards[0]) == 11:
                        is_only_buur = True
                
                is_permitted = (c_color == lead_color) or (self.mode >= 3 and c_color == self.trump_color) or is_only_buur
                if not is_permitted:
                    continue
                    
            if self.mode >= 3 and c_color == self.trump_color:
                if lead_color != self.trump_color:
                    has_other_than_trump = any(self._card_color(tc) != self.trump_color for tc in hand)
                    if has_other_than_trump:
                        trump_order = [6, 7, 8, 10, 12, 13, 14, 9, 11]
                        card_trump_index = trump_order.index(c_num)
                        
                        highest_trump_on_table_val = -1
                        for tc, _ in self.current_trick:
                            if self._card_color(tc) == self.trump_color:
                                highest_trump_on_table_val = max(highest_trump_on_table_val, trump_order.index(self._card_number(tc)))
                                
                        if card_trump_index < highest_trump_on_table_val:
                            continue
            legal.append(c)
        
        if not legal: # Fallback if all filtered out (shouldn't happen but just in case)
            return list(hand)
        return legal

    def get_state(self, player_id):
        # Convert state to tensor sequence matching bot.py
        cards_seq, players_seq, tricks_seq, turns_seq, scores_seq = [], [], [], [], []

        # Prepend hand cards
        for card_id in self.hands[player_id]:
            cards_seq.append(card_id)
            players_seq.append(0) # relative player id for self is always 0
            tricks_seq.append(9)  # Special trick index 9 for hand cards
            turns_seq.append(4)   # Special turn index 4 for hand cards
            scores_seq.append(0)

        for trick_idx, trick_cards in enumerate(self.played_cards_history):
            for turn_idx, card_info in enumerate(trick_cards):
                card, p_id = card_info

                p_id = (p_id - player_id) % 4
                
                cards_seq.append(card)
                players_seq.append(p_id)
                tricks_seq.append(trick_idx)
                turns_seq.append(turn_idx)
                scores_seq.append(0)

            cards_seq.append(37)
            players_seq.append(0)
            tricks_seq.append(trick_idx)
            turns_seq.append(4)  
            my_team = player_id % 2
            opp_team = 1 - my_team
            scores_seq.append(self.trick_scores[trick_idx][my_team] - self.trick_scores[trick_idx][opp_team])   

                
        trick_idx = len(self.played_cards_history)
        for turn_idx, card_info in enumerate(self.current_trick):
            card, p_id = card_info

            p_id = (p_id - player_id) % 4

            cards_seq.append(card)
            players_seq.append(p_id)
            tricks_seq.append(trick_idx)
            turns_seq.append(turn_idx)
            scores_seq.append(0)
            
        # Action token
        cards_seq.append(37)
        players_seq.append(0)
        tricks_seq.append(trick_idx)
        turns_seq.append(len(self.current_trick))
        scores_seq.append(0)
        
        legal_actions = self.get_legal_actions(player_id)
        legal_mask = [1.0 if i in legal_actions else 0.0 for i in range(36)]
        
        return {
            "cards": torch.tensor([cards_seq], dtype=torch.long),
            "players": torch.tensor([players_seq], dtype=torch.long),
            "tricks": torch.tensor([tricks_seq], dtype=torch.long),
            "turns": torch.tensor([turns_seq], dtype=torch.long),
            "scores": torch.tensor([scores_seq], dtype=torch.long),
            "modes": torch.tensor([[self.mode] * len(cards_seq)], dtype=torch.long),
            "legal_mask": torch.tensor([legal_mask], dtype=torch.float32),
            "legal_actions": legal_actions,
            "player_id": player_id
        }

    def _card_value(self, card_id):
        c_num = self._card_number(card_id)
        c_color = self._card_color(card_id)
        
        if self.mode == 0: # OBEABE
            vals = {8:8, 14:11, 10:10, 13:4, 12:3, 11:2}
            return vals.get(c_num, 0)
        elif self.mode == 1: # UNDEUFE
            vals = {8:8, 6:11, 10:10, 13:4, 12:3, 11:2}
            return vals.get(c_num, 0)
        else: # TRUMPF
            if c_color == self.trump_color:
                vals = {11:20, 9:14, 14:11, 10:10, 13:4, 12:3}
                return vals.get(c_num, 0)
            else:
                vals = {14:11, 10:10, 13:4, 12:3, 11:2}
                return vals.get(c_num, 0)

    def _evaluate_trick_winner(self):
        lead_color = self._card_color(self.current_trick[0][0])
        best_card_idx = 0
        
        def card_rank(card_id):
            c_num = self._card_number(card_id)
            c_color = self._card_color(card_id)
            
            if self.mode == 0: # OBEABE
                return c_num if c_color == lead_color else -1
            elif self.mode == 1: # UNDEUFE
                return -c_num if c_color == lead_color else -99
            else: # TRUMPF
                if c_color == self.trump_color:
                    trump_order = {11: 100, 9: 99, 14: 98, 13: 97, 12: 96, 10: 95, 8: 94, 7: 93, 6: 92}
                    return trump_order.get(c_num, 0)
                elif c_color == lead_color:
                    return c_num
                else:
                    return -1

        best_rank = card_rank(self.current_trick[0][0])
        for i in range(1, 4):
            rank = card_rank(self.current_trick[i][0])
            if rank > best_rank:
                best_rank = rank
                best_card_idx = i
                
        return self.current_trick[best_card_idx][1]

    def step(self, action):
        if action not in self.hands[self.current_player]:
            raise ValueError(f"Action {action} not in hand of player {self.current_player}")
            
        self.hands[self.current_player].remove(action)
        
        self.current_trick.append( (action, self.current_player))



        rewards = [0, 0, 0, 0]
        
        if len(self.current_trick) == 4:
            # Trick over
            winner = self._evaluate_trick_winner()
            trick_points = sum(self._card_value(c[0]) for c in self.current_trick)
            
            self.tricks_played += 1
            if self.tricks_played == 9: # Last trick bonus
                trick_points += 5
                
            winning_team = winner % 2
            self.scores[winning_team] += trick_points
            self.trick_scores.append([0, 0])
            self.trick_scores[-1][winning_team] += trick_points
            
            # Step reward: point differential gained
            for i in range(4):
                if i % 2 == winning_team:
                    rewards[i] = trick_points
                else:
                    rewards[i] = -trick_points
                    
            self.played_cards_history.append(self.current_trick)
            self.current_trick = []
            self.current_player = winner
            
            if self.tricks_played == 9:
                self.done = True
                # Terminal reward
                if self.scores[0] > self.scores[1]:
                    rewards[0] += 50
                    rewards[2] += 50
                    rewards[1] -= 50
                    rewards[3] -= 50
                elif self.scores[1] > self.scores[0]:
                    rewards[1] += 50
                    rewards[3] += 50
                    rewards[0] -= 50
                    rewards[2] -= 50
        else:
            self.current_player = (self.current_player + 1) % 4
            
        return self.get_state(self.current_player), rewards, self.done, self.current_player
