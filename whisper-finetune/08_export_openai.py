"""Step 7. Export the fine-tuned Whisper to the format of the `openai-whisper` package, so that it can be used like any standard Whisper model.

The fine-tuning was done on the Hugging Face implementation; the weights are the same numbers under other names, so they are
renamed and saved as one .pt file. The export is then checked: both implementations must give the same transcripts."""
import json

import torch
import whisper
from transformers import WhisperForConditionalGeneration

from common import device, load_split, processor, transcribe
from config import MODELS, RESULTS

hf = WhisperForConditionalGeneration.from_pretrained(MODELS / "whisper-base-ru")
c = hf.config
dims = dict(n_mels=c.num_mel_bins, n_vocab=c.vocab_size, n_audio_ctx=c.max_source_positions, n_audio_state=c.d_model, n_audio_head=c.encoder_attention_heads,
            n_audio_layer=c.encoder_layers, n_text_ctx=c.max_target_positions, n_text_state=c.d_model, n_text_head=c.decoder_attention_heads, n_text_layer=c.decoder_layers)
RENAME = [("model.encoder.layers", "encoder.blocks"), ("model.decoder.layers", "decoder.blocks"), ("encoder_attn_layer_norm", "cross_attn_ln"), ("encoder_attn.k_proj", "cross_attn.key"),
          ("encoder_attn.q_proj", "cross_attn.query"), ("encoder_attn.v_proj", "cross_attn.value"), ("encoder_attn.out_proj", "cross_attn.out"), ("self_attn_layer_norm", "attn_ln"),
          ("self_attn.k_proj", "attn.key"), ("self_attn.q_proj", "attn.query"), ("self_attn.v_proj", "attn.value"), ("self_attn.out_proj", "attn.out"), ("final_layer_norm", "mlp_ln"),
          ("fc1", "mlp.0"), ("fc2", "mlp.2"), ("model.encoder.layer_norm", "encoder.ln_post"), ("model.decoder.layer_norm", "decoder.ln"),
          ("model.encoder.embed_positions.weight", "encoder.positional_embedding"), ("model.decoder.embed_positions.weight", "decoder.positional_embedding"),
          ("model.decoder.embed_tokens", "decoder.token_embedding"), ("model.encoder.conv", "encoder.conv")]
state = {}
for k, v in hf.state_dict().items():
    if k.startswith("proj_out"):
        continue                                  # tied with the token embedding
    for a, b in RENAME:
        k = k.replace(a, b)
    state[k] = v.clone()
out = MODELS / "whisper-base-ru.pt"
torch.save({"dims": dims, "model_state_dict": state}, out)
print("saved", out, f"{out.stat().st_size / 1e6:.0f} MB")

# ---- check 1: numbers. Same input, same tokens: the decoder outputs of both implementations must agree to float precision.
from common import NORM, features
test = load_split("test").head(12)
proc, dev = processor(), device()
ow = whisper.load_model(str(out), device="cpu")
paths = test.path.tolist()[:2]
feats = features(proc, paths).cpu()
ids = torch.tensor([proc.tokenizer(t).input_ids[:40] for t in test.text.tolist()[:2]])
with torch.no_grad():
    lg_hf = hf.cpu().eval()(input_features=feats, decoder_input_ids=ids[:, :-1]).logits
    lg_ow = ow.logits(ids[:, :-1], ow.embed_audio(feats))
max_diff = float((lg_hf - lg_ow).abs().max())

# ---- check 2: text. The model was fine-tuned WITHOUT timestamp tokens, so the comparison uses the same mode in both implementations.
hf.to(dev)
a = transcribe(hf, proc, test.path.tolist(), dev=dev)
b = [ow.transcribe(p, language="ru", fp16=False, condition_on_previous_text=False, without_timestamps=True, temperature=0.0)["text"].strip() for p in test.path]
same = sum(NORM(x).strip() == NORM(y).strip() for x, y in zip(a, b))
rep = {"max_abs_difference_of_logits": max_diff, "checked_utterances": len(a), "identical_transcripts_after_normalisation": same,
       "note": "openai-whisper decodes with timestamp tokens by default; this check switches them off to match the fine-tuning",
       "examples": [{"huggingface": x, "openai_whisper": y} for x, y in list(zip(a, b))[:3]]}
(RESULTS / "export_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1)); print(json.dumps(rep, ensure_ascii=False, indent=1)[:1200])
