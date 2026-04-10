# Jianying Draft Export Guide

ArcReel can export generated video clips as a Jianying desktop draft so you can continue editing in Jianying with the timeline already assembled.

Typical follow-up work in Jianying includes:

- pacing changes
- subtitles
- transitions
- voice-over
- music and sound effects

## Prerequisites

Before exporting, make sure:

- your ArcReel project already has generated video clips for at least one episode
- Jianying Desktop is installed locally
- you know your local Jianying draft directory

Supported desktop versions:

- Jianying 6.0+
- Jianying 5.x

## Step 1: Find Your Jianying Draft Directory

### macOS

```text
/Users/<username>/Movies/JianyingPro/User Data/Projects/com.lveditor.draft
```

### Windows

```text
C:\Users\<username>\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft
```

If you changed the draft directory inside Jianying, use that custom path instead of the default one above.

## Step 2: Start The Export In ArcReel

1. Open the project you want to export.
2. Click `Export` in the top-right corner.
3. Choose `Export as Jianying Draft`.

## Step 3: Fill In The Export Form

You will be asked for:

- `Episode`: choose the episode to export if the project has more than one
- `Jianying version`: choose `6.0+` or `5.x` to match your local installation
- `Draft directory`: paste the Jianying draft path you found earlier

After you confirm, the browser downloads a ZIP archive.

## Step 4: Extract The ZIP Into The Draft Directory

Unzip the downloaded archive directly into the Jianying draft directory.

The result should look like this:

```text
com.lveditor.draft/
├── ...
└── {project_name}_Episode_{N}/
    ├── draft_info.json        # Jianying 6+
    ├── draft_content.json     # Jianying 5.x uses this instead
    ├── draft_meta_info.json
    └── assets/
        ├── segment_S1.mp4
        ├── segment_S2.mp4
        └── ...
```

Make sure the extracted folder is placed directly inside the draft directory, not inside an extra nested folder.

## Step 5: Open The Draft In Jianying

1. Start Jianying Desktop, or restart it if it was already open.
2. Look for the new draft in the draft list.
3. Open it to review the generated timeline.

## What Gets Exported

### Narration Mode

- Video track: all generated video clips in order
- Subtitle track: source narration text is added as subtitles for each clip

### Drama Mode

- Video track: generated clips are ordered by scene
- No subtitle track is added automatically

Drama projects often need more manual subtitle work because dialogue timing is more complex.

## Canvas Size Rules

ArcReel exports the draft using the project aspect ratio:

- `9:16` -> `1080x1920`
- `16:9` -> `1920x1080`

If the project ratio is missing, ArcReel tries to detect it from the first exported video file.

## Troubleshooting

### The Draft Does Not Appear In Jianying

Check the following:

- the ZIP was extracted into the correct Jianying draft directory
- the extracted project folder is directly under that directory
- Jianying was restarted after extraction

### The Version Looks Wrong

The export version must match the installed Jianying version:

- Jianying 6.0 or later -> choose `6.0+`
- Jianying 5.x -> choose `5.x`

If you picked the wrong version, export again with the correct selection.

### Some Video Clips Are Missing

Only successfully generated clips are included in the draft. If a clip failed or was never generated, it will not appear in Jianying. Generate the missing clips in ArcReel and export again.
