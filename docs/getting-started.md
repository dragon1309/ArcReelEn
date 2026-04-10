# Getting Started

This guide walks through the full ArcReel flow, from setup to a finished short video.

## What You Will Do

1. Prepare your API keys.
2. Start ArcReel with Docker.
3. Configure the assistant and media providers.
4. Turn a text source into storyboards, assets, and video clips.
5. Export or iterate on the result.

## Time And Cost Expectations

- Initial setup: about 10 to 20 minutes.
- A short one-minute project: often around 30 minutes end to end, depending on provider speed.
- Costs depend on your chosen providers and models. ArcReel supports Gemini, Volcengine Ark, Grok, OpenAI, and custom OpenAI-compatible or Google-compatible providers.

Typical cost levers:

- Character reference images usually cost more than quick storyboard images.
- Video generation is the most expensive step.
- Fast or lite video models are usually much cheaper for iteration.

## Prerequisites

Before you begin, make sure you have:

- Docker and Docker Compose
- At least one image or video provider API key
- An Anthropic-compatible API key for the built-in assistant
- A machine that can run Docker on Linux, macOS, or Windows with WSL

Recommended minimums:

- 2 GB RAM or more
- Stable internet access to your configured AI providers

## Step 1: Collect API Keys

### Media Providers

ArcReel only needs one configured media provider to get started.

- Gemini: [Google AI Studio](https://aistudio.google.com/apikey)
- Volcengine Ark: [Volcengine Console](https://console.volcengine.com/ark)
- Grok: [xAI Console](https://console.x.ai/)
- OpenAI: [OpenAI Platform](https://platform.openai.com/)

You can also add custom providers after deployment if they support OpenAI-compatible or Google-compatible APIs.

### Assistant Provider

ArcReel’s built-in assistant uses Anthropic-compatible models for project guidance, script work, and agent workflows.

- Official Anthropic API: [Anthropic Console](https://console.anthropic.com/)
- Compatible proxy or gateway: configure the custom base URL and model in Settings after startup

Keep all API keys private. Do not commit them to Git or share them publicly.

## Step 2: Install Docker If Needed

On Ubuntu or Debian:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

After reloading your shell, verify the installation:

```bash
docker --version
docker compose version
```

## Step 3: Start ArcReel

### Option A: Default Deploy With SQLite

This is the simplest option for local use and evaluation.

```bash
git clone https://github.com/ArcReel/ArcReel.git
cd ArcReel/deploy
cp .env.example .env
docker compose up -d
```

### Option B: Production Deploy With PostgreSQL

Use this for a more production-oriented setup.

```bash
git clone https://github.com/ArcReel/ArcReel.git
cd ArcReel/deploy/production
cp .env.example .env
docker compose up -d
```

For the production stack, make sure you set `POSTGRES_PASSWORD` in `.env` before startup.

Once the containers are ready, open:

```text
http://<your-server-ip>:1241
```

## Step 4: First Login And Configuration

1. Sign in with the default username `admin`.
2. Use the password from `AUTH_PASSWORD` in your `.env` file.
3. Open `Settings`.
4. Configure your Anthropic-compatible assistant credentials.
5. Configure at least one media provider credential.
6. Pick default text, image, and video backends if needed.

Most configuration can be changed in the UI without editing files manually.

## Step 5: Create Your First Project

In the project list:

1. Click `New Project`.
2. Enter a project title.
3. Upload a source text file such as `.txt`.
4. Open the project workspace.

## Step 6: Run The Main Creative Workflow

ArcReel is designed to move step by step through a structured media pipeline.

### Generate The Script

Use the assistant to analyze your source text and build a scene or segment structure.

Check:

- whether the story beats make sense
- whether characters and clues were extracted correctly
- whether the pacing matches your target format

### Generate Character References

Generate character reference images early so later scenes stay visually consistent.

Check:

- whether each character matches the source description
- whether clothing, age, and mood are correct

### Generate Clue References

Generate important props, objects, or location references.

Check:

- whether recurring items look right
- whether key objects are recognizable enough for later shots

### Generate Storyboard Images

Generate storyboard or scene images for each segment.

Check:

- composition
- atmosphere
- continuity
- character consistency

### Generate Video Clips

Use storyboard images or prompts to generate short clips. ArcReel queues these jobs asynchronously and tracks their progress in the UI.

Check:

- motion quality
- character consistency
- timing
- whether any clip needs a targeted re-run

### Review Or Assemble The Final Video

After the clips are ready, use ArcReel’s export and editing flow to assemble or refine the final result.

## Iteration Tips

- Review outputs at each stage before generating the next stage.
- Start with a small number of scenes to validate style and cost.
- Use faster video models while iterating.
- Keep strong character references so later generations stay consistent.
- Use version history to roll back assets when a regeneration is worse than the previous one.

## Import And Export

ArcReel can package a project for backup or transfer.

- Export: create a project archive with assets and metadata
- Import: restore a project from an archive

If you plan to continue editing in Jianying, see [docs/jianying-export-guide.md](jianying-export-guide.md).

## Troubleshooting

### Docker Will Not Start

Check:

```bash
systemctl status docker
ss -tlnp | grep 1241
docker compose logs
```

Run the last command from the same deploy directory you started.

### Provider Calls Fail

Check:

- the API key value in Settings
- whether your provider account has billing or quota enabled
- whether your server can reach the provider endpoint
- whether the selected model is supported by that provider account

### Character Consistency Is Weak

Try this order:

1. Regenerate the character reference first.
2. Confirm the prompt clearly describes stable visual traits.
3. Regenerate only the affected storyboard or clip after the reference is fixed.

### Video Generation Feels Slow

That is normal for many providers. Speed depends on:

- provider load
- clip duration
- chosen model tier
- your queue size and RPM settings

## Next Steps

- Read the main [README.md](../README.md) for deployment and architecture notes.
- Open the Jianying guide if you want to continue editing in Jianying.
- File issues at [GitHub Issues](https://github.com/ArcReel/ArcReel/issues) if you hit bugs.

If ArcReel is useful to you, starring the repository helps a lot.
