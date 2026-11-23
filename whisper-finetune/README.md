# Fine-tuning Whisper on Russian speech

Machine learning final project. The **whole workflow is in one notebook**: `whisper_finetune.ipynb` (already executed; `whisper_finetune.html` is the same page without Jupyter). A short written report is in `../Report_Whisper_Finetune.docx`.

## 1. Problem and motivation

Lessons are recorded and turned into text with Whisper, and the lessons we care about are Russian. Question: does fine-tuning the small Whisper-base network (74 M parameters) on Russian speech lower its word error rate (WER)? WER = (substitutions + deletions + insertions) / words in the reference, after lower-casing and removing punctuation (`BasicTextNormalizer`, diacritics kept so that "й" and "ё" stay distinct). Character error rate (CER) is reported as well. Every number has a 95% bootstrap interval over utterances.

A second, small question uses a classical (non-neural) model: can simple features of a transcript tell when it is unreliable and needs a human look?

## 2. Data

| | |
| :-- | :-- |
| Dataset | **FLEURS**, Russian part `ru_ru` (Conneau et al., 2022; Google) |
| Source | Hugging Face `google/fleurs`, public, no login, licence CC BY 4.0 |
| Content | Read speech of native speakers, one Wikipedia-style sentence per recording, 16 kHz. Real recordings, no synthetic data |
| Size | train 2,562 utterances (8.05 h); dev 356 (1.08 h); test 775 (2.50 h) |
| Features / target | audio file and `raw_transcription` (with case and punctuation, which is what Whisper writes); speaker gender |
| Subsets used | train 1,500 (4.7 h), validation 300, test 500: random draws with seed 42 to keep the work feasible on a laptop |

Limitations: read speech in a quiet setting, not classroom conversation; one text domain (encyclopedic sentences); gender is the only speaker information (52% female, 48% male; no age or accent labels); no personal data beyond the recordings, which are published under the licence.

### Exploratory analysis: what was seen and what it changed
Figures and numbers: section 2 of the notebook.
- **Utterances are 3 to 37 seconds** (median 10.6 s) with about 18 words; 3 recordings are over 30 s, the length of Whisper's window. Decision: recordings over 30 s are dropped.
- **No missing values.** About 19% of the sentences contain digits and 8% contain Latin letters (brand names). Decision: error rates are also reported separately for these cases.
- **Speaking rate is steady** (about 1.7 words per second), so duration is a good proxy for length.
- **Splits are disjoint in speakers** by design of FLEURS. Decision: the official splits are used as they are, no random re-splitting.
- **Gender is balanced enough** to check for a gap between voices.

## 3. Reproduce everything

Open `whisper_finetune.ipynb` (already executed). To run it again:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-whisper.txt     # needs ffmpeg in PATH for the demo
jupyter notebook whisper_finetune.ipynb     # Run All: about 5 minutes
```

The data (about 2 GB) is downloaded by the notebook if it is missing. The fine-tuning itself (about 35 minutes on an Apple GPU "mps") runs only when `RETRAIN = True` in the settings cell; otherwise the saved checkpoint `models/whisper-base-ru` and the log `results/finetune_history.json` are used. For the system, `python 08_export_openai.py` converts the weights to the `openai-whisper` format (`models/whisper-base-ru.pt`).

Seed 42 everywhere. Training on `mps` is not bit-for-bit deterministic, so a rerun can differ in the third decimal. The fine-tuned weights are not committed (290 MB in `models/whisper-base-ru.pt`, plus the Hugging Face copy); the notebook (`RETRAIN = True`) and `08_export_openai.py` recreate them. A 16 GB laptop needs the other heavy programs closed: a first attempt with batch 8 filled the memory and swap and stalled, so the batch is 4 with gradient accumulation of 2 (effective batch 8).

## 4. Preprocessing and evaluation design

- Audio is read at 16 kHz and turned into an 80-band log-Mel spectrogram of a 30-second window by the Whisper feature extractor (nothing learned from data, so nothing can leak).
- The official FLEURS splits have different speakers. A check in section 3 of the notebook stops the run if a sentence or file occurs in two splits (reported: 0 overlaps).
- Validation (300 utterances, from the official dev split) is used for choosing the epoch; the test subset (500, official test split) is used once, for the selected checkpoint.

## 5. Models

| Model | What it is |
| :-- | :-- |
| Constant word | Predicts the most frequent training word for every utterance. The "zero" reference |
| Whisper-base, no training | The pretrained network as released by OpenAI (encoder-decoder Transformer, 6+6 layers, hidden 512, 8 heads, 74 M parameters), language forced to Russian, greedy decoding |
| **Whisper-base, fine-tuned (PyTorch)** | The same network, all weights trained on 1,500 Russian utterances |
| Classical models (section 7) | Majority class, logistic regression and gradient boosting on features of the transcript |

Training: teacher forcing; the decoder gets `<sot><ru><transcribe><notimestamps>` and the transcript, the loss is cross-entropy on the transcript tokens and the end token (not on the language/task tokens); optimizer **AdamW**, learning rate 1e-5, weight decay 0.01 (not on biases and layer norms), 10% linear warm-up then linear decay; **batch 8** (2 micro-batches of 4); up to **4 epochs**, early stopping on validation WER (patience 2); gradient clipping 1.0; activation GELU (inside the Transformer). **Regularization:** SpecAugment (random time and frequency masks, probability 0.05), weight decay, early stopping. Dropout was tried and switched off: in the installed version of Transformers it raised the training loss of the pretrained model from 0.62 to about 11 before any update, so it was not used.

**Hyperparameters.** Only the learning rate 1e-5 was trained. A second run with 3e-5 was planned (grid {1e-5, 3e-5}) and cancelled to save time; this is a known gap of this experiment. The number of epochs was chosen by validation WER (best epoch 2).

## 6. Results of the neural network

| Model | val WER | **test WER** | test CER |
| :-- | :-- | :-- | :-- |
| Constant word | 0.973 | 0.976 | 0.993 |
| Whisper-base, no training | 0.2345 | 0.2476 | 0.0755 |
| Whisper-base, fine-tuned | 0.2332 | **0.2408** | 0.0757 |

95% bootstrap intervals of the test WER: no training 0.234 to 0.262, fine-tuned 0.228 to 0.255. The **paired** difference (no training minus fine-tuned) is 0.0067 WER with the interval -0.0014 to 0.0152, which **includes zero: the improvement is not statistically significant.** Fine-tuning changed 336 of 500 utterances (184 got better, 152 got worse, 164 unchanged), so the changes are real, but they cancel almost completely.

### Interpretation of the results

- **Learning curves** (`results/fig_learning_curves.png` and notebook section 4). The training loss falls from 0.70 to 0.27, the validation loss stops at 0.38 after the second epoch, and validation WER gets worse after epoch 2 (0.2332, 0.2358, 0.2402). That is **overfitting** from the third epoch on, and the early-stopping rule picks epoch 2. There is no underfitting.
- **Why the gain is so small.** Whisper-base was already trained on a very large amount of Russian speech, and the 4.7 hours used here are a small addition; the model has 74 M parameters and the speech is clean read speech like much of what it has seen. The remaining errors are mostly a capacity limit of the small network (rare names, case endings), which more of the same data does not remove. An unexpected finding, reported as it is.
- **Where it helps** (notebook section 7, small groups, read with care): short utterances up to 6 s (n=17) 0.201 to 0.161; sentences with Latin letters (n=26) 0.298 to 0.266; female voices 0.242 to 0.231, male 0.255 to 0.253; sentences with digits do not change (0.295 to 0.292). Utterances over 14 s get slightly worse (0.244 to 0.249).
- **Error analysis** (notebook section 8). The most improved sentences fix word boundaries and common words ("на ездников" to "наездников", "отец Лухи" to "эти слухи"). The worse ones typically change a case ending or a proper name. Names of places and people remain the main source of errors in both models. Repetition loops (a transcript more than twice as long as the reference, e.g. "возвозвозвоз...") appear in 2 of 500 utterances for both models, so fine-tuning did not change that rate.
- **Interpretation of the network** (`results/fig_attention.png`). The cross-attention of the last decoder layer, averaged over heads, forms a clean diagonal: every generated token looks at the stretch of audio where it is spoken, so the decoder follows the speech in time instead of guessing from the language alone.

## 7. A classical model: flagging unreliable transcripts

Notebook section 10. Task: from what is known at inference time (the recording length and the produced transcript) predict whether an utterance has WER 0.30 or more ("needs a human look"). 29% of the validation and 32% of the test utterances are positive. Eleven simple features (duration, words, characters, words per second, average word length, share of long words, share of capitalised words inside a sentence, share of words with digits, Latin letters, repeated bigrams, punctuation per word). Models: majority class (baseline), logistic regression, gradient boosting. They are trained on the validation predictions of the fine-tuned model (300 utterances); settings are chosen by 5-fold cross-validation grouped by sentence; the test predictions (500) are used once.

| Model | test AUC (95% interval) | accuracy | F1 of "unreliable" |
| :-- | :-- | :-- | :-- |
| Majority class | 0.500 | 0.678 | 0.000 |
| Logistic regression (C=1) | **0.655** (0.600 to 0.706) | 0.664 | **0.520** |
| Gradient boosting (depth 3, rate 0.05) | 0.602 (0.549 to 0.666) | 0.640 | 0.458 |

Both classical models rank unreliable transcripts better than chance, but weakly. Gradient boosting looked better in cross-validation (AUC 0.61 against 0.56) and logistic regression won on the test set: with 300 training examples such a choice is noisy. The most useful feature by far is the **share of capitalised words inside a sentence** (names of people and places): shuffling it lowers the test AUC by 0.083, the next feature by 0.020. That agrees with the error analysis: names are what the network gets wrong. Accuracy is below that of the majority class because the classes are unbalanced (68% reliable) and the models are tuned to find the unreliable ones. Files: `results/detector_metrics.json`, `results/fig_detector.png`.

## 8. Limitations and next steps

- The learning-rate search was cut to one value, and only 1,500 of 2,562 training utterances were used.
- The fine-tuning data is read speech of encyclopedic sentences. Real lessons, with a teacher and a student, noise and conversational speech, would be a better target: it needs recordings with careful human transcripts.
- A larger model (small or medium) starts from a lower error and would need more memory than a 16 GB laptop gives; a GPU server or Google Colab would be the natural place.
- Kazakh (also in FLEURS) would show a larger gain, because the pretrained network is much weaker there.
- The detector is trained on 300 examples and has a modest AUC; more data and a feature such as the decoder's own confidence would likely help.

## 9. Demonstration and use of the model

```bash
python predict.py demo/talk_ru.m4a     # one recording with Whisper-base and with the fine-tuned model (cut into 25-second pieces)
```

`demo/talk_ru.m4a` is a synthetic (text-to-speech) Russian recording used only to show how the script works. `08_export_openai.py` renames the weights to the format of the `openai-whisper` package and checks the export: the decoder outputs of both implementations are identical (largest difference 0.0 on the same input), and 10 of 12 test transcripts are identical after normalisation (the two others differ in the decoding mode of the two libraries). The exported file is used like this:

```python
import whisper
model = whisper.load_model("models/whisper-base-ru.pt")
print(model.transcribe("recording.m4a", language="ru")["text"])
```

On a 62-second recording it produced 14 segments with time stamps.

### Checking the model in the system (`../datera-mini`)

The team's lesson-analysis web application was updated so that the fine-tuned model can be tried without any code:

- the page **«Проверка Whisper»** (teacher and administrator cabinets) runs one recording through the original Whisper-base and through the fine-tuned one and shows both texts, the time of each and, when the correct text is known, the WER of each. It offers ten utterances from the test subset (never seen in training) and the upload of your own recording (up to 3 minutes, Russian);
- the block **«Две записи, две модели»** on the same page takes two recordings, lets you choose a different Whisper model for each (tiny to large-v3 and base-ru-finetuned) and shows the two results side by side, with WER if the correct text is pasted and with the words that differ in red otherwise, and with an option to split the transcript into teacher and student turns by voice; a tick box «та же запись» sends one recording through two models;
- in **«Модели и анализ» → «Распознавание речи: Whisper»** the model **base-ru-finetuned** can be chosen for processing whole lessons.

Without the system, section 8 of the notebook shows both transcripts for the utterances where fine-tuning helped most and where it hurt most.

Start it from `datera-mini` with the environment of this folder: `../whisper-finetune/.venv/bin/python -m uvicorn web.server:app --port 8501`, then open http://localhost:8501. One example proves little: on the first test utterance the original model gave WER 27.8% and the fine-tuned one 5.6%, but over 500 test utterances the difference is small and not significant (section 6). It is a small model: larger standard Whisper models stay the better choice for real use; this one is the result of this work, kept for comparison.

## 10. Files

| File | Purpose |
| :-- | :-- |
| `whisper_finetune.ipynb`, `.html` | The whole process in one notebook: data, EDA, splits, baselines, training, curves, results, errors, classical model, demo |
| `config.py`, `common.py` | Seed, paths and the shared decoding/WER code used by `predict.py` and `08_export_openai.py` |
| `08_export_openai.py` | Export of the weights for the system plus an equality check |
| `predict.py`, `demo/` | Command-line demonstration and a demo recording |
| `DEFENSE_QA.md` | Questions and answers for the defence |
| `results/` | Figures, metrics, predictions of every model, training log |

## 11. Sources and AI assistance

- Conneau A. et al. FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech. 2022. Data: https://huggingface.co/datasets/google/fleurs
- Radford A. et al. Robust Speech Recognition via Large-Scale Weak Supervision (Whisper). 2022. https://github.com/openai/whisper
- Park D. et al. SpecAugment. 2019. Loshchilov I., Hutter F. Decoupled Weight Decay Regularization (AdamW). 2019.
- Paszke A. et al. PyTorch. Wolf T. et al. Transformers. Pedregosa F. et al. scikit-learn. Jiwer library for WER.
