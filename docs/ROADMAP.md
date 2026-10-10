# Roadmap

Ideas the user has asked to keep for later, not yet scheduled. Newest first.

## Levels and a difficulty curve (requested 2026-10-09, deferred)

Turn the single skirmish into a progression of levels where the enemy starts gentle and gets
harder as the player levels up.

- **Early levels:** the enemy takes its time. It builds slowly, its first attack comes late,
  attacks are small and far apart, and the player has room to learn the economy.
- **Later levels:** each level tightens the screws: earlier first attack, shorter gaps between
  waves, bigger waves, a faster and stronger enemy economy, more archers in the mix, and towers
  and walls on its side.
- **Progression:** win a level to unlock the next; remember the highest level reached between
  sessions.

Where the knobs live today (`ios/WebGame/index.html`, enemy AI around `aiThink`): the first-attack
and between-wave timer (`ai.next`, currently 150 s between waves), the wave size (`ai.wave`, which
grows by 2 up to 12), the enemy's starting resources (`res[1]`), its villager count (six at start)
and its build and train choices. A level would be a table of these values plus map tweaks
(resource richness, distance between the Town Centers).

Not now: the user wants other work finished first.
