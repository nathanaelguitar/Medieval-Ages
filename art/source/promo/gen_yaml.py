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

# ---- batch 2 promos (ten daily posts): new portrait shots, reusable across cuts ----
WORLD_HUNT = ("Live-action 35mm film, photorealistic, an English oak forest in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. Peasant hunters in simple wool and leather clothes carry long wooden boar spears; "
         "no armour, no banners. No text, no modern objects.")
WORLD_THREAT = ("Live-action 35mm film, photorealistic, England in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. Ordinary villagers in simple wool and linen clothes, unarmed. The enemy army "
         "wears plain red surcoats over mail and carries many tall red banners. No text, no modern objects.")
WORLD_KING = ("Live-action 35mm film, photorealistic, England in the year 1380, fine film grain, anamorphic lens, shallow depth "
         "of field. The king wears a gold crown and a royal blue surcoat with a white rampant lion over mail, a fur-trimmed cloak; "
         "his captains wear blue-and-white quartered tabards with a pale rampant lion. No text, no modern objects.")
# no enemy in shot: a world block that never mentions red, so none bleeds into the player's ranks
WORLD_BLUE = ("Live-action 35mm film, photorealistic, England in the year 1380, natural light, fine film grain, "
         "anamorphic lens, shallow depth of field. Every soldier wears the same blue-and-white quartered tabard with a pale "
         "rampant lion over mail and plate, kettle helmets and heater shields; all banners are blue with a white lion. "
         "No text, no modern objects.")
# takes whose light is not golden day (night, rain, snow, candlelight) skip the GOLD suffix
NOGOLD = {"b_night_watch", "b_rain_clash", "b_winter_march", "b_winter_march_b", "b_night_watch_b", "b_king_table", "b_siege_tower"}
TAKES.update({
    "b_mill": (141, 9101,
        "[Shot 1] Wide low-angle shot of a tall wooden post windmill standing on a gentle hill above a golden wheat field. Its four "
        "large lattice sails turn slowly and steadily in the wind. A miller in a flour-dusted tunic walks toward the camera along the "
        "path carrying a sack over his shoulder. Calm, photoreal, 35mm film, slow push in. Sound: wind, creaking wood.", "CIVIL", "V"),
    "b_millstone": (141, 9201,
        "[Shot 2] Interior of a medieval mill, dusty shafts of sunlight. A huge round grey millstone turns slowly on top of another "
        "stone; golden grain trickles from a wooden hopper into the hole at its centre and fine white flour spills from its rim into "
        "a wooden trough. Big wooden cog wheels turn behind it. Close-up, photoreal, 35mm film. Sound: grinding stone, creaking gears.", "CIVIL", "V"),
    "b_farm": (141, 9301,
        "[Shot 3] Medium shot in a golden wheat field at harvest. Peasant men in linen shirts and straw hats swing long scythes in a "
        "row, cutting the tall wheat which falls in neat swathes; a woman behind them gathers the stalks into sheaves. Thatched "
        "cottages on the horizon. Peaceful, photoreal, 35mm film, slow sideways dolly. Sound: the swish of scythes, larks.", "CIVIL", "V"),
    # b_farm's scythes come out as handle-less blades floating in the wheat; the harvest without blades:
    "b_farm_b": (141, 9302,
        "[Shot 3] Medium shot in a golden wheat field at harvest, the wheat already cut and lying in rows. Peasants in linen shirts "
        "and straw hats bind armfuls of wheat into sheaves and stand them upright in stooks; a young woman in a headscarf lifts a "
        "heavy sheaf onto her shoulder and walks slowly toward the camera. Thatched cottages and oak trees behind. Peaceful, "
        "photoreal, 35mm film, slow push in. Sound: larks, rustling straw.", "CIVIL", "V"),
    "b_market": (141, 9401,
        "[Shot 4] Medium shot of a busy medieval village market in the morning. Wooden stalls with loaves of bread, cabbages, apples "
        "and bolts of dyed cloth under striped awnings; villagers in wool and linen walk between them, a merchant lifts a basket of "
        "apples, a dog trots past. Lively, photoreal, 35mm film, slow push in. Sound: market chatter, a cart.", "CIVIL", "V"),
    "b_sheep": (141, 9501,
        "[Shot 5] Low angle on a dusty country lane between hedgerows. A large flock of white sheep streams toward and past the camera, "
        "a shepherd with a long wooden crook walks behind them and a black-and-white sheepdog runs along the side of the flock. "
        "Dust glows in the low sun. Pastoral, photoreal, 35mm film. Sound: bleating sheep, a whistle.", "CIVIL", "V"),
    "b_boar": (141, 9601,
        "[Shot 6] Low angle at ground level in an oak forest. A huge dark wild boar with tusks bursts out of the ferns and charges "
        "straight toward the camera, leaves and dirt flying; behind it two hunters run in with long spears lowered. High-speed slow "
        "motion, hard shafts of sunlight through the trees. Thrilling, photoreal, 35mm film. Sound: a squeal, crashing undergrowth.", "HUNT", "V"),
    "b_gate": (141, 9701,
        "[Shot 7] Inside a stone castle gatehouse. Two huge iron-studded oak gates swing shut toward the camera, and men-at-arms in "
        "blue-and-white tabards with a pale rampant lion heave a thick wooden beam down across them to bar the gate. Dust falls from "
        "the arch, urgent shouting. Tense, photoreal, 35mm film. Sound: a heavy boom of the gates, the thud of the beam.", "LION", "V"),
    "b_gate_hold": (141, 9801,
        "[Shot 8] Close shot inside a castle gate. Men-at-arms in blue-and-white tabards with a pale rampant lion brace their shoulders "
        "and heater shields against the barred oak gate as it shudders from a battering ram outside; dust and splinters burst from the "
        "wood with each blow. Gritty, photoreal, 35mm film, handheld. Sound: thunderous blows, gritted shouts.", "LION", "V"),
    "b_wall_archers": (141, 9901,
        "[Shot 9] Side view along the battlements of a stone castle wall. A row of English longbowmen in blue-and-white tabards and "
        "kettle helmets stand at the crenellations facing screen right and draw tall longbows to full draw, arrows pointing out over "
        "the field. Banners with a white lion flutter above them. Tense, photoreal, 35mm film. Sound: creaking bowstrings, wind.", "LION", "V"),
    "b_volley_hill": (141, 10001,
        "[Shot 10] Shot from behind a long line of English longbowmen in blue-and-white tabards standing on a grassy hill. They loose "
        "together and the arrows fly away from the camera, point first, rising high into the sky toward a distant red army in the "
        "valley below. Slow motion, dust in the air. Epic, photoreal, 35mm film. Sound: the thrum of bowstrings, whistling arrows.", "LION", "V"),
    "b_volley_hill_b": (141, 10002,
        "[Shot 10] Shot from behind a long line of English longbowmen in blue-and-white tabards standing on a grassy hill. They loose "
        "together and the arrows fly away from the camera, point first, rising high into the sky toward a distant red army in the "
        "valley below. Slow motion, dust in the air. Epic, photoreal, 35mm film. Sound: the thrum of bowstrings, whistling arrows.", "LION", "V"),
    "b_king_table": (141, 10101,
        "[Shot 11] Inside a war tent at night lit by candles and braziers. A bearded king with a gold crown stands over a large wooden "
        "table covered with a painted map and carved wooden markers; he pushes a blue marker forward across the map while his captains "
        "lean in around the table. Warm candlelight, deep shadows. Commanding, photoreal, 35mm film, slow push in. Sound: crackling fire.", "KING", "V"),
    "b_night_watch": (141, 10201,
        "[Shot 12] Night on a stone castle wall under a dark blue sky. Two guards in blue-and-white tabards with a pale rampant lion walk "
        "along the battlements carrying flaming torches; firelight flickers on the stones. Far below in the black valley the many "
        "campfires of an enemy army glow. Moody, photoreal, 35mm film. Moonlight and orange torchlight. Sound: wind, crackling torches.", "LION", "V"),
    "b_siege_tower": (141, 10301,
        "[Shot 13] Dusk, low angle at the foot of a stone castle wall. A tall wooden siege tower draped with red banners is engulfed in "
        "roaring orange flames and thick black smoke, burning timbers falling from it; embers swirl up into the darkening sky. "
        "Dramatic, photoreal, 35mm film, slow push in. Firelight against a deep blue dusk sky. Sound: roaring fire, cracking timber.", "LION", "V"),
    "b_winter_march": (141, 10401,
        "[Shot 14] A column of soldiers in blue-and-white tabards with a pale rampant lion, mail and kettle helmets marches through deep "
        "snow toward and past the camera, a tall blue banner with a white lion carried at the front; their breath steams, snow is "
        "falling. Pale cold winter light, grey sky, snowy hills. Determined, photoreal, 35mm film. Sound: wind, crunching snow.", "LION", "V"),
    # b_winter_march put red banners and red-clad men into the lion column (WORLD_LION names the enemy); without red:
    "b_winter_march_b": (141, 10402,
        "[Shot 14] A column of soldiers in blue-and-white tabards with a pale rampant lion, mail and kettle helmets marches through deep "
        "snow toward and past the camera, a tall blue banner with a white lion carried at the front; their breath steams, snow is "
        "falling. Pale cold winter light, grey sky, snowy hills. Determined, photoreal, 35mm film. Sound: wind, crunching snow.", "BLUE", "V"),
    # b_night_watch also drew red flags and red-clad men onto our own wall; the enemy as distant fires only:
    "b_night_watch_b": (141, 10202,
        "[Shot 12] Night on a stone castle wall under a dark blue sky. Two guards in blue-and-white tabards with a pale rampant lion walk "
        "along the battlements carrying flaming torches; firelight flickers on the stones. Far below in the black valley the many "
        "campfires of a besieging army glow like scattered embers. Moody, photoreal, 35mm film. Moonlight and orange torchlight. "
        "Sound: wind, crackling torches.", "BLUE", "V"),
    "b_rain_clash": (141, 10501,
        "[Shot 15] Heavy rain, a muddy battlefield under dark storm clouds. A man-at-arms in a soaked blue-and-white tabard with a pale "
        "rampant lion clashes with a soldier in a plain red surcoat, swords and shields locked, rain splashing off steel and mud "
        "spraying. High-speed slow motion, cold grey light. Brutal, photoreal, 35mm film. Sound: rain, clashing steel.", "LION", "V"),
    "b_red_horizon": (141, 10601,
        "[Shot 16] From behind a small group of villagers standing on a hilltop at the edge of their village, looking down into a wide "
        "valley. In the distance a huge army in red surcoats with dozens of tall red banners marches toward them across the fields, "
        "dust rising. The villagers stand frozen. Ominous, photoreal, 35mm film, slow push in over their shoulders. Sound: distant drums.", "THREAT", "V"),
    "b_bell": (141, 10701,
        "[Shot 17] Low angle inside a small stone bell tower. A young villager in a brown tunic hauls desperately on a thick rope and a "
        "large bronze bell swings above him, ringing the alarm; dust shakes loose from the beams. Urgent, photoreal, 35mm film, "
        "handheld. Sound: a clanging alarm bell.", "CIVIL", "V"),
    "b_victory": (141, 10901,
        "[Shot 19] Low angle hero shot at golden hour on a hilltop after a battle. A man-at-arms in a blue-and-white tabard with a pale "
        "rampant lion drives the pole of a tall blue banner with a white rampant lion into the earth and it streams in the wind against "
        "a glowing sky; behind him a line of soldiers in the same blue-and-white tabards raise their swords and shields in triumph, "
        "smoke drifting across the field. Triumphant, epic, photoreal, 35mm film. Sound: a cheer, wind in the cloth.", "BLUE", "V"),
    "b_mason": (141, 10801,
        "[Shot 18] Medium shot at a medieval building site. Masons in linen shirts guide a large squared stone block as a wooden crane "
        "with a treadwheel lowers it onto a rising castle wall; scaffolding of lashed poles, dust in the air. Industrious, photoreal, "
        "35mm film, slow push in. Sound: creaking ropes, chisels on stone.", "CIVIL", "V"),
})

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
    world = {"RED": WORLD_RED, "CIVIL": WORLD_CIVIL, "LION": WORLD_LION, "HUNT": WORLD_HUNT, "THREAT": WORLD_THREAT, "KING": WORLD_KING, "BLUE": WORLD_BLUE}.get(world, WORLD)
    assert (frames - 5) % 17 == 0 and frames <= 345, name
    h, w = (1344, 768) if orient == "V" else (768, 1344)
    prompt = "integrated_multimodal_description: " + (VERT if orient == "V" else "") + body + ("" if name in NOGOLD else GOLD) + " " + world
    prompt = " ".join(prompt.split())
    with open(os.path.join(OUT, name + ".yaml"), "w") as f:
        f.write(TEMPLATE.format(prompt=prompt, seed=seed, frames=frames, name=name, h=h, w=w, out=os.path.abspath(OUT)))
    print(name, frames, seed, orient)
