# Deepfake Detection app

A small, self-contained application that detects AI-generated or manipulated
images and videos (deepfakes, compositing, partial tampering) using the
[BytePlus LLM Application Firewall](https://docs.byteplus.com/en/docs/LLM-Application-Firewall/Detect_deepfakes_with_the_SDK)
deepfake-detection SDK.

Give it an **image or video** — as a direct upload, a local file path, or a
**URL** — and it returns a clear verdict (**Authentic** vs **Manipulated**),
the confidence score, the triggered risk labels, and the raw API response.

> This app is independent of CodeSwarm (the rest of this repo). It shares only
> the `.env` file at the repo root.

## Contents

| Path | What it is |
|------|------------|
| `config.py`   | Loads & validates credentials from env / `.env`; masks secrets. |
| `media.py`    | Loads and validates samples (upload / path / URL); format + size checks. |
| `detector.py` | Wraps the BytePlus `ClientV2.Moderate` SDK call. |
| `results.py`  | Flattens & interprets the response (category `109`, decision `2`). |
| `app.py`      | Flask web UI + JSON API. |
| `cli.py`      | Command-line interface. |
| `templates/`  | The single-page web UI. |

## 1. Install

```bash
pip install -r deepfake_detector/requirements.txt
```

## 2. Configure credentials

Copy the example env file and fill in the **deepfake** section (the app reads
only these keys; the CodeSwarm keys above them are unrelated):

```bash
cp .env.example .env
```

```ini
BYTEPLUS_LLM_FIREWALL_AK=your-access-key-id
BYTEPLUS_LLM_FIREWALL_SK=your-secret-access-key
BYTEPLUS_DEEPFAKE_APPID=app-xxxxxxxx        # asset with Integration=SDK, Scenario=Deepfake
BYTEPLUS_DEEPFAKE_REGION=ap-southeast-1     # or cn-hongkong
# BYTEPLUS_DEEPFAKE_ENDPOINT=              # optional; derived from region if empty
# BYTEPLUS_DEEPFAKE_TIMEOUT=50             # optional
```

**Secrets never leave `.env`.** `.env` is in `.gitignore`, the app masks the
AK/SK anywhere it is displayed (UI banner, `/api/health`, logs, `repr()`), and
credentials are never sent anywhere except to the BytePlus endpoint.

### Prerequisites (one-time, in the BytePlus console)

1. **Asset management → Add asset** → *Integration method:* **SDK integration**,
   *Protection scenario:* **Deepfake detection**. Copy the generated **AppID**.
2. Grant the calling account `AccessKeySelfManageAccess` and
   `LLMShieldProtectSdkAccess` permissions.

## 3. Run the web app

```bash
python -m deepfake_detector.app
# open http://127.0.0.1:5000
```

Environment knobs: `DEEPFAKE_HOST`, `DEEPFAKE_PORT`, `DEEPFAKE_DEBUG=1`.

Upload a file **or** switch to the *From URL* tab, choose the content source
(`user` upload vs `assistant`-generated), and click **Detect**.

### JSON API

```bash
# file upload
curl -F file=@face.png -F role=user http://127.0.0.1:5000/api/detect
# from a URL
curl -F url=https://example.com/clip.mp4 http://127.0.0.1:5000/api/detect
# service/config status (secrets masked)
curl http://127.0.0.1:5000/api/health
```

## 4. Or use the CLI

```bash
python -m deepfake_detector.cli ./photo.png
python -m deepfake_detector.cli https://example.com/clip.mp4 --role assistant
python -m deepfake_detector.cli ./photo.png --json
```

Exit codes: `0` authentic, `3` manipulated, `1` input/API error, `2` config error —
so it composes in scripts and CI gates.

## Supported formats & limits

| Type   | Formats                    | Max size |
|--------|----------------------------|----------|
| Image  | `jpg` `jpeg` `png` `webp`  | 10 MB    |
| Video  | `mp4` `avi`                | 50 MB    |

Samples are base64-encoded and sent to `Moderate` with
`content_type=ContentTypeV2.IMAGE` / `VIDEO`.

## Interpreting the result

| Field | Meaning |
|-------|---------|
| `RiskInfo.Risks[].Category` = `109` | Deepfake risk category. |
| `RiskInfo.Risks[].Label` = `10900000` | Deepfake / manipulated media label. |
| `RiskInfo.Risks[].Prob` | Confidence, 0.0–1.0. |
| `Decision.DecisionType` | `1` = Allow (authentic), `2` = Block (manipulated). |
| `Decision.HitStrategyIDs` | Triggered built-in policy rule IDs. |
| `ContentInfo` | Detected content format. |

The app maps these to `manipulated: true/false`, a verdict string, and a
`probability`. Only the built-in deepfake policy is effective for this scenario.

Detection logs are also visible in the console under **Attack Logs → Deepfake logs**.

## Tests

```bash
python -m pytest tests/test_deepfake_detector.py
```

Tests inject a fake SDK client and build samples from in-memory bytes, so they
run without credentials or network access.
