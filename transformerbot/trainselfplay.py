import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions.categorical import Categorical
from transformerbot.model import JassTransformer
from transformerbot.env import JassEnv
import numpy as np
import os

def compute_gae(rewards, values, gamma=0.99, lam=0.95):
    advantages = []
    gae = 0
    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * values[t+1] - values[t]
        gae = delta + gamma * lam * gae
        advantages.insert(0, gae)
    return advantages

class PPOTrainer:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
        self.model = JassTransformer().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=3e-4, weight_decay=1e-4)
        
        # Try to load existing weights
        weights_path = os.path.join(os.path.dirname(__file__), "jass_transformer.pt")
        self.model.load_weights(weights_path)
        
        self.gamma = 0.99
        self.lam = 0.95
        self.clip_ratio = 0.2
        self.ppo_epochs = 4
        
        # Self-play pool
        self.opponent_pool = []
        
    def collect_trajectories(self, num_games=100):
        self.model.eval()
        
        # Play against previous models 20% of the time if available
        use_pool = len(self.opponent_pool) > 0 and np.random.rand() < 0.2
        if use_pool:
            opponent_model = np.random.choice(self.opponent_pool)
            opponent_model.eval()
        else:
            opponent_model = self.model
            
        # Only collect trajectories from opponent players (Team 1) when they play using the active model (on-policy)
        players_to_collect = [0, 2] if use_pool else [0, 1, 2, 3]
        trajectories = []
        
        for _ in range(num_games):
            env = JassEnv()
            state = env.reset()
            done = False
            
            player_transitions = {i: {"states": [], "actions": [], "rewards": [], "values": [], "log_probs": []} for i in range(4)}
            
            while not done:
                current_p = state["player_id"]
                
                # Active model plays for Team 0 (0,2), opponent for Team 1 (1,3)
                active_agent = self.model if current_p % 2 == 0 else opponent_model
                
                c = state["cards"].to(self.device)
                p = state["players"].to(self.device)
                t_idx = state["tricks"].to(self.device)
                turn = state["turns"].to(self.device)
                m = state["modes"].to(self.device)
                s = state["scores"].to(self.device)
                mask = state["legal_mask"].to(self.device)
                
                with torch.no_grad():
                    logits, value = active_agent(c, p, t_idx, turn, m, s, mask)
                    dist = Categorical(logits=logits[0])
                    action = dist.sample()
                    log_prob = dist.log_prob(action)
                    
                if current_p in players_to_collect:
                    player_transitions[current_p]["states"].append(state)
                    player_transitions[current_p]["actions"].append(action.item())
                    player_transitions[current_p]["values"].append(value.item())
                    player_transitions[current_p]["log_probs"].append(log_prob.item())
                    
                next_state, rewards, done, _ = env.step(action.item())
                rewards = [r / 100.0 for r in rewards]
                
                # Distribute rewards
                if len(env.current_trick) == 0:
                    for i in range(4):
                        player_transitions[i]["rewards"].append(rewards[i])
                        
                state = next_state
                
            # Process trajectories for selected players
            for i in players_to_collect:
                vals = player_transitions[i]["values"] + [0]
                rews = player_transitions[i]["rewards"]
                if len(rews) < len(vals)-1:
                    rews.extend([0] * (len(vals) - 1 - len(rews))) # PAD
                    
                adv = compute_gae(rews, vals, self.gamma, self.lam)
                returns = [a + v for a, v in zip(adv, vals[:-1])]
                
                for step in range(len(player_transitions[i]["states"])):
                    trajectories.append({
                        "state": player_transitions[i]["states"][step],
                        "action": player_transitions[i]["actions"][step],
                        "log_prob": player_transitions[i]["log_probs"][step],
                        "value": player_transitions[i]["values"][step],
                        "return": returns[step],
                        "advantage": adv[step]
                    })
                    
        return trajectories
        
    def update(self, trajectories):
        self.model.train()
        
        states = [t["state"] for t in trajectories]
        actions = torch.tensor([t["action"] for t in trajectories], dtype=torch.long).to(self.device)
        old_log_probs = torch.tensor([t["log_prob"] for t in trajectories], dtype=torch.float32).to(self.device)
        returns = torch.tensor([t["return"] for t in trajectories], dtype=torch.float32).to(self.device)
        advantages = torch.tensor([t["advantage"] for t in trajectories], dtype=torch.float32).to(self.device)
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # Compute explained variance of value predictions before update
        values_np = np.array([t["value"] for t in trajectories])
        returns_np = np.array([t["return"] for t in trajectories])
        var_y = np.var(returns_np)
        explained_var = 1.0 - np.var(returns_np - values_np) / (var_y + 1e-8) if var_y > 1e-8 else 0.0
        
        # Group by sequence length to avoid padding issues
        from collections import defaultdict
        grouped = defaultdict(list)
        for idx in range(len(trajectories)):
            seq_len = states[idx]["cards"].size(1)
            grouped[seq_len].append(idx)
            
        policy_losses = []
        value_losses = []
        entropies = []
        
        for _ in range(self.ppo_epochs):
            # Shuffle keys for stochasticity
            seq_lengths = list(grouped.keys())
            np.random.shuffle(seq_lengths)
            
            for seq_len in seq_lengths:
                indices = grouped[seq_len]
                np.random.shuffle(indices)
                
                # Mini-batching within sequence length groups
                batch_size = 64
                for i in range(0, len(indices), batch_size):
                    batch_idx = indices[i:i+batch_size]
                    
                    b_c = torch.cat([states[idx]["cards"] for idx in batch_idx], dim=0).to(self.device)
                    b_p = torch.cat([states[idx]["players"] for idx in batch_idx], dim=0).to(self.device)
                    b_t_idx = torch.cat([states[idx]["tricks"] for idx in batch_idx], dim=0).to(self.device)
                    b_turn = torch.cat([states[idx]["turns"] for idx in batch_idx], dim=0).to(self.device)
                    b_m = torch.cat([states[idx]["modes"] for idx in batch_idx], dim=0).to(self.device)
                    b_s = torch.cat([states[idx]["scores"] for idx in batch_idx], dim=0).to(self.device)
                    b_mask = torch.cat([states[idx]["legal_mask"] for idx in batch_idx], dim=0).to(self.device)
                    
                    logits, value = self.model(b_c, b_p, b_t_idx, b_turn, b_m, b_s, b_mask)
                    
                    dist = Categorical(logits=logits)
                    b_actions = actions[batch_idx]
                    new_log_prob = dist.log_prob(b_actions)
                    entropy = dist.entropy().mean()
                    
                    b_old_log_probs = old_log_probs[batch_idx]
                    b_adv = advantages[batch_idx]
                    b_returns = returns[batch_idx]
                    
                    ratio = torch.exp(new_log_prob - b_old_log_probs)
                    surr1 = ratio * b_adv
                    surr2 = torch.clamp(ratio, 1.0 - self.clip_ratio, 1.0 + self.clip_ratio) * b_adv
                    
                    policy_loss = -torch.min(surr1, surr2).mean()
                    value_loss = 0.5 * (b_returns - value.squeeze(-1)).pow(2).mean()
                    
                    # Standard value loss weight of 0.5, and entropy coefficient of 0.05
                    loss = policy_loss + 0.5 * value_loss - 0.05 * entropy
                    
                    self.optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=0.5)
                    self.optimizer.step()
                    
                    policy_losses.append(policy_loss.item())
                    value_losses.append(value_loss.item())
                    entropies.append(entropy.item())
                    
        return np.mean(policy_losses), np.mean(value_losses), np.mean(entropies), explained_var
                
    def train(self, iterations=1000):
        print(f"Starting PPO Self-Play Training on {self.device}...")
        for it in range(iterations):
            trajectories = self.collect_trajectories(num_games=250) # Adjust batch size based on RAM
            if not trajectories:
                continue
                
            p_loss, v_loss, ent, exp_var = self.update(trajectories)
            
            avg_return = np.mean([t["return"] for t in trajectories])
            print(f"Iteration {it+1}/{iterations} | Trajectories: {len(trajectories)} | Avg Return: {avg_return:.2f} | Policy Loss: {p_loss:.4f} | Value Loss: {v_loss:.4f} | Entropy: {ent:.4f} | Exp Var: {exp_var:.4f}")
            
            if (it + 1) % 50 == 0:
                save_path = os.path.join(os.path.dirname(__file__), f"jass_transformer_v{it+1}.pt")
                torch.save(self.model.state_dict(), save_path)
                
                # Save the active model as latest
                torch.save(self.model.state_dict(), os.path.join(os.path.dirname(__file__), "jass_transformer.pt"))
                print(f"Saved checkpoint: {save_path}")
                
                old_model = JassTransformer().to(self.device)
                old_model.load_state_dict(self.model.state_dict())
                self.opponent_pool.append(old_model)
                if len(self.opponent_pool) > 5:
                    self.opponent_pool.pop(0)

if __name__ == "__main__":
    trainer = PPOTrainer()
    trainer.train(iterations=500)
