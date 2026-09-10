# Dataset sources and access

Only generated synthetic records and short authored examples are included. Third-party data is optional and is neither downloaded automatically nor redistributed. Review current terms on each provider page, obtain any required authorization, and keep an access/license record before placing files under `data/raw/<dataset>/`.

| Source | Intended research use |
|---|---|
| [SentiMix / SemEval-2020 Task 9](https://aclanthology.org/2020.semeval-1.100/) | Hinglish code-mixed sentiment and language identification |
| [IndicSentiment](https://huggingface.co/datasets/ai4bharat/IndicSentiment) | Indian-language sentiment evaluation |
| [GoEmotions](https://github.com/google-research/google-research/tree/master/goemotions) | Fine-grained English text emotions |
| [MELD](https://affective-meld.github.io/) | Dialogue and multimodal emotion experiments |
| [RAVDESS](https://zenodo.org/records/1188976) | Optional acted speech emotion research |
| [CREMA-D](https://github.com/CheyneyComputerScience/CREMA-D) | Speech emotion experiments across speakers |
| [TESS](https://borealisdata.ca/dataset.xhtml?persistentId=doi:10.5683/SP2/E8H2MF) | Optional supplemental speech research |
| [DAIC-WOZ](https://dcapswoz.ict.usc.edu/) | Access-controlled distress-oriented research; never required to run |
| [IndicVoices](https://huggingface.co/datasets/ai4bharat/IndicVoices) | Multilingual Indian speech / ASR robustness |

Source pages were consulted during implementation; automated access to the RAVDESS and TESS pages was unavailable. No license claim is made for those sources. Follow their official access instructions manually. Availability of a dataset does not establish permission for redistribution or clinical use.

Normalize an authorized local CSV:

```sh
python data/preprocess.py data/raw/my_dataset/export.csv data/processed/my_dataset.jsonl --text-column text --label-column label --language hinglish
```

Expected output is JSONL `{text,label,language}`. Provider-specific exports must first be mapped to a CSV with the selected columns. Keep train/test speakers and individuals separate; do not combine emotion, sentiment and future-escalation targets as if they were interchangeable. No external dataset contributes to the reported prototype metrics.

Synthetic trajectories: `python ai/train.py` writes `data/synthetic/longitudinal.csv`. The generator seed is 26094. It includes stable, gradual, sudden, threat, court/investigation, compensation, rehabilitation and intervention-related patterns. Features and future outcomes are simulated, making evaluation generator-dependent.
