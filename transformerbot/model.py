import torch
import torch.nn as nn
import torch.nn.functional as F

class JassTransformer(nn.Module):
    def __init__(self, embed_dim=128, n_heads=4, n_layers=2):
        super().__init__()
        self.embed_dim = embed_dim
        
        # 1. Embedding Layers
        self.card_embed = nn.Embedding(38, embed_dim)   # 36 cards + padding + hidden
        self.player_embed = nn.Embedding(5, embed_dim) # 4 players + padding
        self.trick_embed = nn.Embedding(11, embed_dim) # 9 tricks + hand cards + padding
        self.turn_embed = nn.Embedding(6, embed_dim)   # 4 turns + hand cards + padding
        self.mode_embed = nn.Embedding(7, embed_dim)   # game modes

        self.score_embed = nn.Linear(1, embed_dim, bias=False) # game modes
        


        # 2. Transformer Backbone
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim, 
            nhead=n_heads, 
            dim_feedforward=embed_dim * 4, 
            batch_first=True,
            dropout=0.1
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        
        # 3. Dual Heads
        self.policy_head = nn.Linear(embed_dim, 36)  # Mapping to 36 potential card choices
        self.value_head = nn.Linear(embed_dim, 1)    # State valuation for RL critic
        
    def forward(self, cards, players, tricks, turns, modes, scores, legal_mask):
        # Shape of inputs: (Batch, Seq_Len)
        seq_len = cards.size(1)
        
        # Combine embeddings
        x = (self.card_embed(cards) + 
             self.player_embed(players) + 
             self.trick_embed(tricks) + 
             self.turn_embed(turns) +
             self.mode_embed(modes) +
             self.score_embed(scores.unsqueeze(-1).float() / 100.0)) # Shape: (Batch, Seq_Len, Embed_Dim)
        
        # Pass through transformer using bidirectional attention over all known history/hand cards
        features = self.transformer(x)
        
        # Extract the final token (the current state representation)
        last_token_feature = features[:, -1, :] # Shape: (Batch, Embed_Dim)
        
        # Compute raw heads
        raw_logits = self.policy_head(last_token_feature)
        value = self.value_head(last_token_feature)
        
        # Apply Action Masking: Force illegal moves to a large negative value to avoid NaN in entropy
        masked_logits = raw_logits.masked_fill(legal_mask == 0, -1e9)
        
        return masked_logits, value

    def load_weights(self, path):
        try:
            self.load_state_dict(torch.load(path, map_location=torch.device('cpu')))
            print(f"Successfully loaded weights from {path}")
        except FileNotFoundError:
            print(f"Warning: No weights found at {path}. Initializing with random weights.")
        except Exception as e:
            print(f"Error loading weights: {e}")
