# Bodhan `indic-translate`: wrong-language and chat-style output (2026-10-31)

Found during the corpus test. Both responses were HTTP 200 with `finish_reason: "stop"`, so nothing on our side
flagged them; the app stored them as finished translations. Full request and response for each are in the request
cache (paths below).

## 1. Asked for Tamil, got English

| | |
| :--- | :--- |
| Endpoint | `POST https://api.bodhan.ai/v1/chat/completions`, `model: indic-translate` |
| `target_language` | `ta` (Tamil) |
| Source | Bengali paragraph, 418 characters (Bengali Wikipedia, *Taj Mahal*, page 2, last paragraph) |
| Response id | `20261031_4e88f11d-25ab-46b6-a871-42ca52b444ce` (`created` 1793455974, 2026-10-31 ~19:42 IST) |
| Fingerprint | `vllm-0.27.1-9be2c277` |
| Cache file | `data/live/cache/api.bodhan.ai/indic-translate/2b853b60dfd409ee698c91a20fc4867a28c365b3f542bd65d0629ec77d38b752.json` |

Request text (start): `চাহার বাগ ভারতে প্রথম করেছিলেন প্রথম মুঘল সম্রাট বাবর, যা পারস্যের বাগানের মতো করে নকশা করা হয়েছিল। …`

Response: a correct **English** translation, no Tamil at all:
`The first Mughal emperor Babur built the Charbagh in India, which was designed like a Persian garden. …`

The other 19 sections of the same document, sent to the same target in the same job, came back in Tamil.

## 2. Asked for Sanskrit, got a chatbot answer

| | |
| :--- | :--- |
| `target_language` | `sa` (Sanskrit) |
| Source | English figure caption, 597 characters (Mamba paper, Figure 1) |
| Response id | `20261031_4cedf4bf-d400-407d-8585-4e602c0c805b` (`created` 1793450841, ~18:17 IST) |
| Fingerprint | `vllm-0.27.1-9be2c277` |
| Cache file | `data/live/cache/api.bodhan.ai/indic-translate/513c0c9ec9f97a98212a0701f1d78707a794ac0a99267bb250e442d9a48db71a.json` |

Response: the Sanskrit wrapped in English commentary, 1443 characters for a 597-character source:
"Here's a translation of the provided English text into Sanskrit, aiming for accuracy, naturalness, and
appropriate restructuring:", the translation in `**bold**`, then "**Notes on the Translation Choices:**" with four
English bullet points and a closing sentence. The other 18 sections of that document were clean.

## For the report

- Neither case is reproducible on demand from our side yet (each was one section among many in a job); the
  response ids above should identify them in Bodhan's logs.
- On our side (not done yet): check each translation's script against the target (`core.in_script_ratio`) and
  retry or mark it failed, and reject answers far longer than the source or starting "Here's/Here is …". Today a
  wrong-language result is labelled as the target language, so a later prompt edit sees no language change and
  Claude writes the translation itself, bypassing Bodhan.
