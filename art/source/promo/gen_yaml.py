#!/usr/bin/env python3
"""Generate FastH3 yaml configs for the Medieval Ages 9:16 promo shots.
Usage: gen_yaml.py OUTDIR [take1,take2,...]  -> writes OUTDIR/<take>.yaml
Run on the Spark; render with runner.sh (queue = OUTDIR/queue.txt).
WORLD blocks are copied verbatim from art/source/intro/edit/gen_yaml.py so new
shots intercut with the intro footage.
"""
import sys, os

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

WORLD = ("Live-action 35mm film, photorealistic, England in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. The defenders wear blue-and-cream quartered tabards with a white "
         "griffin over mail and plate, kettle helmets and heater shields. The enemy wears red surcoats and carries red banners. "
         "No text, no modern objects.")
WORLD_RED = ("Live-action 35mm film, photorealistic, England in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. The enemy soldiers all wear plain red surcoats with no heraldry over mail, "
         "steel helmets, and carry red banners and heater shields. No text, no modern objects.")
WORLD_CIVIL = ("Live-action 35mm film, photorealistic, a peaceful English village in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. Ordinary villagers in simple wool and linen clothes; no soldiers, no armour, "
         "no banners, no weapons. No text, no modern objects.")
VERT = "Vertical 9:16 portrait composition for a phone screen, tall frame, subject centred. "
GOLD = " Warm golden sunlight, amber haze, rich cinematic colour."
# Promo defenders carry the game's own arms (a pale rampant lion) rather than the intro's griffin;
# at these shot scales the sigil does not read in the reused intro clips either way.
WORLD_LION = ("Live-action 35mm film, photorealistic, England in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. The defenders wear blue-and-white quartered tabards with a pale "
         "rampant lion over mail and plate, kettle helmets and heater shields. The enemy wears red surcoats and carries red banners. "
         "No text, no modern objects.")

# name: (frames, seed, body, world, orientation)  orientation V = 768x1344 portrait, L = 1344x768
TAKES = {
    "v_charge": (141, 7101,
        "[Shot 1] High-speed camera slow motion, low angle at ground level. A line of soldiers in red surcoats and steel helmets "
        "charges straight toward the camera across a muddy field, mud and dust spraying from their boots, spears lowered, tall red "
        "banners rising out of the top of the frame behind them, hard late-morning backlight through the dust. Photoreal, cinematic, "
        "epic. Sound: a deep war cry and pounding feet.", "RED", "V"),
    "v_slam": (141, 7201,
        "[Shot 2] High-speed camera slow motion, tight handheld close-up in a muddy field, thick dust and hard backlight. A man-at-arms "
        "in a blue-and-cream tabard with a white griffin and a kettle helmet slams his heater shield into a charging soldier in a plain "
        "red surcoat; mud and dust burst from the impact, a sword strikes the shield rim and splinters fly. Behind them the battle is an "
        "out-of-focus wall of red and blue figures in dust. Visceral, photoreal. Sound: a roar, the crack of wood and steel.", "DEF", "V"),
    # ---- second batch (after the portrait test passed) ----
    "v_village": (141, 7301,
        "[Shot 1] Medium shot in warm early morning light down a muddy lane between timber-framed thatched cottages. A young woman "
        "in a linen dress and headscarf carries a basket of bread toward the camera, chickens scatter, thin smoke rises from the "
        "chimneys into golden haze, a slow camera push in. Peaceful, photoreal, 35mm film. Sound: birdsong, distant chickens.", "CIVIL", "V"),
    "v_woodcutter": (141, 7401,
        "[Shot 1] Medium shot in warm morning light. A bearded woodcutter in a rough wool tunic swings an axe high and splits a log on "
        "a chopping block outside a thatched cottage; the halves fall apart and wood chips fly. Smoke drifts from the chimney above "
        "him, sunlight through the haze. Calm, photoreal, 35mm film. Sound: the crack of the axe, birdsong.", "CIVIL", "V"),
    "v_lookout": (141, 7501,
        "[Shot 2] Low angle looking up at a tall timber watchtower against a hazy golden sky. A young lookout in a brown hooded tunic "
        "at the top rail turns his head sharply, stares into the distance, then cups his hands and shouts down. Wind moves his hood. "
        "Tense, photoreal, 35mm film, slight handheld movement. Sound: wind, a shout.", "CIVIL", "V"),
    "v_muster": (141, 7601,
        "[Shot 3] Low angle in a village square in warm late-morning sun. Men-at-arms in blue-and-white tabards with a pale rampant "
        "lion form ranks and raise their heater shields; behind them a tall blue banner with a white lion is lifted high and unfurls "
        "in the wind against the sky. Resolute, epic, photoreal, 35mm film, slow push in. Sound: a horn call, the clatter of shields.", "LION", "V"),
    "v_draw": (141, 7701,
        "[Shot 4] Medium close shot along a wooden palisade in warm late-morning sun. An English longbowman in a blue-and-white tabard "
        "and kettle helmet nocks an arrow and draws a tall longbow to full draw beside his ear, the bow standing taller than the frame, "
        "a line of archers drawing behind him out of focus. Tense, photoreal, 35mm film. Sound: a creaking bowstring, a shouted order.", "LION", "V"),
    "v_volley": (141, 7801,
        "[Shot 5] Shot from behind and below a line of English longbowmen in blue-and-white tabards standing on a wooden palisade. On "
        "command they loose together: the arrows leave the bows point first and fly away from the camera, up and over the field toward "
        "a distant red army, slow motion, dust in the air. Photoreal, 35mm film. Sound: the thrum of bowstrings and the whistle of arrows.", "LION", "V"),
    "v_volley_b": (141, 7802,
        "[Shot 5] Shot from behind and below a line of English longbowmen in blue-and-white tabards standing on a wooden palisade. On "
        "command they loose together: the arrows leave the bows point first and fly away from the camera, up and over the field toward "
        "a distant red army, slow motion, dust in the air. Photoreal, 35mm film. Sound: the thrum of bowstrings and the whistle of arrows.", "LION", "V"),
    "v_slam_b": (141, 7202,
        "[Shot 6] High-speed camera slow motion, tight handheld close-up in a muddy field, thick dust and hard golden backlight. A man-at-arms "
        "in a blue-and-white tabard with a pale rampant lion and a kettle helmet braces and slams his heater shield into a charging soldier in a "
        "plain red surcoat; mud and dust burst from the impact, splinters fly. Behind them an out-of-focus wall of red and blue figures "
        "in dust. Visceral, photoreal. Sound: a roar, the crack of wood and steel.", "LION", "V"),
    "v_banner": (141, 7901,
        "[Shot 7] Low angle hero shot at golden hour on a hilltop after battle. A man-at-arms in a blue-and-white tabard plants a tall "
        "blue banner with a white rampant lion into the earth and it streams in the wind against a glowing sky; soldiers behind him raise "
        "their swords and shields in triumph, dust and smoke drifting. Triumphant, epic, photoreal, 35mm film. Sound: a cheer, wind in the cloth.", "LION", "V"),
    "v_loose_side": (141, 8101,
        "[Shot 5] Side profile close shot of one English longbowman in a blue-and-white tabard and kettle helmet on a palisade, facing "
        "screen right. He holds a single tall wooden longbow at full draw, then releases: the bowstring snaps forward and one arrow "
        "shoots away to the right, point first, toward a distant field. Behind him other archers loose in a line, out of focus. "
        "Slow motion, photoreal, 35mm film. Sound: the thrum of a bowstring.", "LION", "V"),
    "v_charge_b": (141, 7102,
        "[Shot 1] High-speed camera slow motion, low angle at ground level. A line of soldiers in plain red surcoats and steel helmets "
        "charges straight toward the camera across a muddy field, mud and dust spraying from their boots, spears lowered, tall red "
        "banners rising out of the top of the frame behind them, hard golden backlight through the dust. Photoreal, cinematic, "
        "epic. Sound: a deep war cry and pounding feet.", "RED", "V"),
}

TEMPLATE = """generator:
  model_path: /home/nathanaelguitar/Downloads/FastH3-local
  engine:
    num_gpus: 1
    use_fsdp_inference: false
    parallelism:
      tp_size: 1
      sp_size: 1
    offload:
      dit: false
      dit_layerwise: false
      text_encoder: true
      vae: true
      pin_cpu_memory: true
      lazy_module_load: true
    compile:
      enabled: false
      vae_enabled: true
  pipeline:
    experimental:
      attention_backend: VIDEO_SPARSE_ATTN_H3
      VSA_sparsity: 0.9
      VSA_tile_size: 64
      inference_torch_compile: true
      vae_parallel_decode: true
      vae_parallel_decode_strategy: gather
request:
  prompt: >-
    {prompt}
  negative_prompt: ""
  sampling:
    seed: {seed}
    height: {h}
    width: {w}
    num_frames: {frames}
    fps: 24
    num_inference_steps: 5
    guidance_scale: 1.0
    batch_cfg: false
  output:
    output_path: {out}/out/{name}/
    save_video: true
    return_frames: false
"""

only = sys.argv[2].split(",") if len(sys.argv) > 2 else list(TAKES)
for name in only:
    frames, seed, body, world, orient = TAKES[name]
    world = {"RED": WORLD_RED, "CIVIL": WORLD_CIVIL, "LION": WORLD_LION}.get(world, WORLD)
    assert (frames - 5) % 17 == 0 and frames <= 345, name
    h, w = (1344, 768) if orient == "V" else (768, 1344)
    prompt = "integrated_multimodal_description: " + (VERT if orient == "V" else "") + body + GOLD + " " + world
    prompt = " ".join(prompt.split())
    with open(os.path.join(OUT, name + ".yaml"), "w") as f:
        f.write(TEMPLATE.format(prompt=prompt, seed=seed, frames=frames, name=name, h=h, w=w, out=os.path.abspath(OUT)))
    print(name, frames, seed, orient)
