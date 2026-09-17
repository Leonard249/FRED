from mlx_lm import load, generate

# model_name = 
# reasoning model -> mlx-community/Qwen3-8B-4bit-DWQ-053125
# VLM -> mlx-community/Qwen3-VL-4B-Instruct-5bit
# coding model -> mlx-community/Qwen2.5-Coder-3B-Instruct-8bit
model_name = input("Please give a model path from mlx: ")

model, tokenizer = load(model_name)

prompt = "Write a story about Einstein"

messages = [{"role": "user", "content": prompt}]
prompt = tokenizer.apply_chat_template(
    messages, add_generation_prompt=True,
)

text = generate(model, tokenizer, prompt=prompt, verbose=True)