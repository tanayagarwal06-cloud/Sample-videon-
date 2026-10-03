# Rolex history video (5:36, 1080p)

Final render: https://d2ol7oe51mr4n9.cloudfront.net/user_3JzmjTsdGKQPbIPQq5Hs3dLxR7C/ccfa06fe-89e4-4b0e-bda9-c704141ae5c1.mp4

- `narration.json`: the 10 voiceover segments (Higgsfield `seed_audio`, voice "Cillian")
- `storyboard.py`: 46 scene prompts (Seedream 4.5, flat 2D cartoon style) and on-screen date callouts
- `shots.json`, `assets.tsv`: the shot list and generated asset IDs used by the renderer
- `render.py`: assembles the 1080p/24 fps master in the Higgsfield sandbox. Stills get pan/zoom moves,
  the 9 Seedance 2.0 Mini clips (720p) are upscaled, and narration drives the shot timing.
