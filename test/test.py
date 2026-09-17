from mlx_lm import load

# Load just the config and tokenizer (very fast, doesn't load heavy weights)
model, tokenizer = load("mlx-community/Qwen3-8B-4bit-DWQ-053125")

# 1. Check the absolute maximum context window
# print("Max Context Window:", model.config.max_position_embeddings)

# 2. Check the chat template it expects
print("\nChat Template:")
print(tokenizer.chat_template)